import base64
import json
import os
import threading
import time
from collections import deque
from urllib.parse import urlencode, urljoin
from urllib.request import urlopen

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from flask_sock import Sock


app = Flask(__name__)
CORS(app)
sock = Sock(app)

latest_detection = None
latest_frame_bytes = None
latest_frame_sequence = 0
selected_index = 0
selection_version = 0
message_sequence = 0
state_lock = threading.Lock()
latest_frame_condition = threading.Condition()
viewer_sockets = set()
viewer_sockets_lock = threading.Lock()
viewer_broadcast_condition = threading.Condition()
pending_viewer_message = None

HISTORY_LIMIT = 36
MJPEG_KEEPALIVE_SECONDS = 2.0
traffic_up_history = deque([0], maxlen=HISTORY_LIMIT)
traffic_down_history = deque([0], maxlen=HISTORY_LIMIT)
accident_probability_history = deque([0], maxlen=HISTORY_LIMIT)

UPBOUND_LABEL = 0
DOWNBOUND_LABEL = 1
CONGESTION_OVERLAP_THRESHOLD = 0.8
CONGESTION_CENTER_MOVEMENT_THRESHOLD = 20.0

CCTV_ITEMS = [
    "[경부선] 천안호두휴게소",
    "[경부선] 옥산휴게소",
    "[경부선] 남청주육교",
    "[경부선] 청주분기점(고정)",
    "[경부선] 가마육교",
    "[경부선] 금계",
    "[청주영덕선] 문동1",
    "[청주영덕선] 청주분기점",
    "[청주영덕선] 문동2",
    "[청주영덕선] 문의청남대휴게소2",
    "[중부선] 증평2",
    "[중부선] 오창",
    "[중부선] 서청주",
    "[경부선] 남이분기점",
    "[경부선] 속창육교",
    "[경부선] 몽단이고개",
    "[경부선] 수의",
    "[경부선] 죽암교",
    "[경부선] 옥산분기점",
    "[경부선] 강서",
]

ITS_API_KEY = os.environ.get("ITS_API_KEY", "").strip()
ITS_API_URL = "https://openapi.its.go.kr:9443/cctvInfo"
REQUEST_PARAMS = {
    "apiKey": ITS_API_KEY,
    "type": "all",
    "cctvType": "1",
    "minX": 127.25,
    "maxX": 127.60,
    "minY": 36.50,
    "maxY": 36.80,
    "getType": "json",
}

cctv_records = []
cctv_records_source = "not_loaded"
cctv_records_error = ""
previous_direction_centers_by_stream = {}


def _build_placeholder_jpeg(message="waiting for YOLO frame"):
    frame = np.full((540, 960, 3), (18, 24, 34), dtype=np.uint8)
    cv2.putText(frame, "Detection Screen", (28, 52), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (230, 236, 245), 2, cv2.LINE_AA)
    cv2.putText(frame, message, (28, 104), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (120, 182, 255), 2, cv2.LINE_AA)
    cv2.rectangle(frame, (22, 22), (938, 518), (62, 78, 104), 2)
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    return encoded.tobytes() if ok else b""


PLACEHOLDER_FRAME_BYTES = _build_placeholder_jpeg()


def _decode_frame_jpeg(value):
    if not value:
        return None
    if isinstance(value, bytes):
        return value
    if not isinstance(value, str):
        return None

    payload = value.split(",", 1)[1] if value.startswith("data:image") and "," in value else value
    try:
        return base64.b64decode(payload, validate=True)
    except Exception:
        return None


def _update_latest_frame(frame_jpeg):
    global latest_frame_bytes, latest_frame_sequence
    decoded = _decode_frame_jpeg(frame_jpeg)
    if not decoded:
        return

    with latest_frame_condition:
        latest_frame_bytes = decoded
        latest_frame_sequence += 1
        latest_frame_condition.notify_all()


def _json_field(value, default):
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def _truthy(value):
    return str(value).lower() in {"1", "true", "yes"}


def _resolve_stream_url(cctv_url):
    if not cctv_url:
        return ""
    try:
        with urlopen(cctv_url, timeout=8) as response:
            playlist_url = response.geturl()
            playlist_text = response.read().decode("utf-8", errors="replace")
    except Exception:
        return cctv_url

    for line in playlist_text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return urljoin(playlist_url, line)
    return cctv_url


def _fetch_cctv_records():
    query = urlencode(REQUEST_PARAMS)
    with urlopen(f"{ITS_API_URL}?{query}", timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    data = payload.get("response", {}).get("data", [])
    if not data:
        raise RuntimeError("CCTV 목록을 불러오지 못했습니다.")

    fetched_items = []
    for row in data:
        name = str(row.get("cctvname", "")).strip()
        cctv_url = str(row.get("cctvurl", "")).strip()
        fetched_items.append(
            {
                "name": name,
                "cctv_url": cctv_url,
                "stream_url": _resolve_stream_url(cctv_url),
            }
        )

    by_name = {item["name"]: item for item in fetched_items}
    return [by_name.get(name, {"name": name, "cctv_url": "", "stream_url": ""}) for name in CCTV_ITEMS]


def _ensure_cctv_records():
    global cctv_records, cctv_records_source, cctv_records_error
    if cctv_records:
        return
    try:
        cctv_records = _fetch_cctv_records()
        cctv_records_source = "its_api"
        cctv_records_error = ""
    except Exception as exc:
        cctv_records = [{"name": name, "cctv_url": "", "stream_url": ""} for name in CCTV_ITEMS]
        cctv_records_source = "fallback"
        cctv_records_error = f"{type(exc).__name__}: {exc}"


def _selected_record():
    _ensure_cctv_records()
    if 0 <= selected_index < len(cctv_records):
        return cctv_records[selected_index]
    return {"name": "-", "cctv_url": "", "stream_url": ""}


def _build_roi_mask(frame_shape, rois, label):
    height, width = frame_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    for roi in rois:
        if int(roi.get("label", -1)) != int(label):
            continue
        polygon = np.array(roi.get("points", []), dtype=np.int32)
        if len(polygon) >= 3:
            cv2.fillPoly(mask, [polygon], 1)
    return mask


def _calculate_roi_coverage_ratio(frame_shape, detections, rois, label):
    roi_mask = _build_roi_mask(frame_shape, rois, label)
    roi_area = int(np.count_nonzero(roi_mask))
    if roi_area <= 0:
        return 0.0

    detection_mask = np.zeros_like(roi_mask)
    for detection in detections:
        if detection.get("direction_label") != int(label):
            continue
        x1, y1, x2, y2 = [int(value) for value in detection.get("bbox", [0, 0, 0, 0])]
        x1 = max(0, min(x1, detection_mask.shape[1]))
        x2 = max(0, min(x2, detection_mask.shape[1]))
        y1 = max(0, min(y1, detection_mask.shape[0]))
        y2 = max(0, min(y2, detection_mask.shape[0]))
        if x2 <= x1 or y2 <= y1:
            continue
        detection_mask[y1:y2, x1:x2] = 1

    overlap_pixels = int(np.count_nonzero(cv2.bitwise_and(roi_mask, detection_mask)))
    return min(1.0, overlap_pixels / float(roi_area))


def _calculate_mean_center_movement(current_detections, previous_centers):
    if not current_detections or not previous_centers:
        return None

    previous_by_track_id = {
        int(track_id): tuple(center)
        for track_id, center in (previous_centers or {}).items()
        if track_id is not None and center is not None
    }
    movements = []
    for detection in current_detections:
        track_id = detection.get("track_id")
        center = detection.get("center")
        if center is None or track_id is None:
            continue
        previous_center = previous_by_track_id.get(int(track_id))
        if previous_center is None:
            continue
        movements.append(float(np.hypot(center[0] - previous_center[0], center[1] - previous_center[1])))

    if not movements:
        return None
    return float(sum(movements) / len(movements))


def _compute_congestion(detections, rois, frame_width, frame_height, selected_name):
    frame_shape = (int(frame_height or 0), int(frame_width or 0), 3)
    previous_state = previous_direction_centers_by_stream.get(selected_name, {"up": {}, "down": {}})
    congestion = {}
    current_state = {"up": {}, "down": {}}
    for direction_name, label in (("up", UPBOUND_LABEL), ("down", DOWNBOUND_LABEL)):
        direction_detections = [item for item in detections if item.get("direction_label") == int(label)]
        current_state[direction_name] = {
            int(item["track_id"]): tuple(item["center"])
            for item in direction_detections
            if item.get("track_id") is not None and item.get("center")
        }
        coverage_ratio = _calculate_roi_coverage_ratio(frame_shape, direction_detections, rois, label)
        mean_movement = _calculate_mean_center_movement(
            direction_detections,
            previous_state.get(direction_name, {}),
        )
        congestion[direction_name] = {
            "count": len(direction_detections),
            "roi_coverage_ratio": round(float(coverage_ratio), 4),
            "mean_center_movement": round(float(mean_movement), 4) if mean_movement is not None else None,
            "is_congested": bool(
                coverage_ratio >= CONGESTION_OVERLAP_THRESHOLD
                and mean_movement is not None
                and mean_movement <= CONGESTION_CENTER_MOVEMENT_THRESHOLD
            ),
        }
    previous_direction_centers_by_stream[selected_name] = current_state
    return congestion


def _calculate_accident_probability(traffic_count, traffic_up, traffic_down, congestion):
    if traffic_count <= 0:
        return 0, "-"
    up_congestion = bool(congestion.get("up", {}).get("is_congested", False))
    down_congestion = bool(congestion.get("down", {}).get("is_congested", False))
    imbalance = abs(int(traffic_up) - int(traffic_down))
    congestion_bonus = 35 * int(up_congestion) + 35 * int(down_congestion)
    probability = int(min(99, 12 + (int(traffic_count) * 8) + (imbalance * 3) + congestion_bonus))
    if up_congestion and down_congestion:
        return probability, "양방향 복잡"
    if up_congestion:
        return probability, "상행 복잡"
    if down_congestion:
        return probability, "하행 복잡"
    return probability, f"{probability}%"


def _append_metric_history(traffic_up, traffic_down, accident_probability):
    traffic_up_history.append(int(traffic_up))
    traffic_down_history.append(int(traffic_down))
    accident_probability_history.append(int(accident_probability))


def _resolve_status():
    selected = _selected_record()
    detection = latest_detection or {}
    return {
        "selected_index": int(detection.get("selected_index", selected_index) or selected_index),
        "selected_name": detection.get("selected_name") or selected["name"],
        "traffic_count": int(detection.get("traffic_count", 0) or 0),
        "traffic_up": int(detection.get("traffic_up", 0) or 0),
        "traffic_down": int(detection.get("traffic_down", 0) or 0),
        "traffic_up_history": list(traffic_up_history),
        "traffic_down_history": list(traffic_down_history),
        "accident_probability": int(detection.get("accident_probability", 0) or 0),
        "accident_probability_history": list(accident_probability_history),
        "accident_status": detection.get("accident_status", "-"),
        "congestion_up": bool(detection.get("congestion", {}).get("up", {}).get("is_congested", False)),
        "congestion_down": bool(detection.get("congestion", {}).get("down", {}).get("is_congested", False)),
        "stream_status": detection.get("stream_status") or ("연결됨" if latest_detection else "준비 중"),
        "player_url": detection.get("player_url") or detection.get("stream_url") or selected.get("stream_url", ""),
        "stream_url": detection.get("stream_url") or selected.get("stream_url", ""),
        "cctv_url": detection.get("cctv_url") or selected.get("cctv_url", ""),
        "cctv_source": cctv_records_source,
        "cctv_error": cctv_records_error,
        "cctv_count": len(cctv_records),
        "frame_available": latest_frame_bytes is not None,
        "selection_version": selection_version,
        "yolo_enabled": latest_detection is not None,
        "roi_enabled": bool(detection.get("roi_enabled", False)),
        "roi_path": detection.get("roi_path") or "-",
        "latest_detection": latest_detection,
    }


def _viewer_message():
    global message_sequence
    payload = _resolve_status()
    message_sequence += 1
    payload["type"] = "frame"
    payload["message_sequence"] = message_sequence
    return payload


def _update_latest_detection(data):
    global latest_detection
    _update_latest_frame(data.get("frame_jpeg"))
    detections = _json_field(data.get("detections"), [])
    rois = _json_field(data.get("rois"), [])
    selected_name = data.get("selected_name") or _selected_record()["name"]
    frame_width = int(data.get("frame_width", 0) or 0)
    frame_height = int(data.get("frame_height", 0) or 0)
    traffic_count = len(detections)
    traffic_up = sum(1 for item in detections if item.get("direction_label") == UPBOUND_LABEL)
    traffic_down = sum(1 for item in detections if item.get("direction_label") == DOWNBOUND_LABEL)
    congestion = _compute_congestion(detections, rois, frame_width, frame_height, selected_name)
    accident_probability, accident_status = _calculate_accident_probability(
        traffic_count,
        traffic_up,
        traffic_down,
        congestion,
    )
    latest_detection = {
        "class_name": (max(detections, key=lambda item: float(item.get("confidence", 0) or 0), default={"class_name": "none"})).get("class_name", "none"),
        "confidence": float((max(detections, key=lambda item: float(item.get("confidence", 0) or 0), default={"confidence": 0.0})).get("confidence", 0) or 0),
        "bbox": (max(detections, key=lambda item: float(item.get("confidence", 0) or 0), default={"bbox": [0, 0, 0, 0]})).get("bbox", [0, 0, 0, 0]),
        "detections": detections,
        "rois": rois,
        "frame_id": int(data.get("frame_id", 0) or 0),
        "frame_width": frame_width,
        "frame_height": frame_height,
        "traffic_count": traffic_count,
        "traffic_up": traffic_up,
        "traffic_down": traffic_down,
        "congestion": congestion,
        "accident_probability": accident_probability,
        "accident_status": accident_status,
        "selected_name": selected_name,
        "selected_index": int(data.get("selected_index", selected_index) or selected_index),
        "cctv_url": data.get("cctv_url", ""),
        "stream_url": data.get("stream_url", ""),
        "player_url": data.get("player_url", ""),
        "stream_status": data.get("stream_status"),
        "roi_enabled": _truthy(data.get("roi_enabled", False)) if isinstance(data.get("roi_enabled"), str) else bool(data.get("roi_enabled", False)),
        "roi_path": data.get("roi_path"),
        "timestamp": data.get("timestamp") or str(time.time()),
    }
    _append_metric_history(traffic_up, traffic_down, accident_probability)
    return latest_detection


def _broadcast_to_viewers(message):
    serialized = json.dumps(message, ensure_ascii=False)
    dead_sockets = []
    with viewer_sockets_lock:
        sockets = list(viewer_sockets)
    for ws in sockets:
        try:
            ws.send(serialized)
        except Exception:
            dead_sockets.append(ws)
    if dead_sockets:
        with viewer_sockets_lock:
            for ws in dead_sockets:
                viewer_sockets.discard(ws)


def _queue_viewer_broadcast(message):
    global pending_viewer_message
    with viewer_broadcast_condition:
        pending_viewer_message = message
        viewer_broadcast_condition.notify()


def _viewer_broadcast_worker():
    global pending_viewer_message
    while True:
        with viewer_broadcast_condition:
            while pending_viewer_message is None:
                viewer_broadcast_condition.wait()
            message = pending_viewer_message
            pending_viewer_message = None
        _broadcast_to_viewers(message)


@app.route("/")
def index():
    return jsonify({"status": "ok", "message": "detection backend running"})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/detection", methods=["POST"])
def receive_detection():
    data = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    if not data:
        return jsonify({"status": "error", "message": "JSON body is required"}), 400
    with state_lock:
        detection = _update_latest_detection(data)
        viewer_message = _viewer_message()
    _queue_viewer_broadcast(viewer_message)
    return jsonify({"status": "ok", "data": detection})


def _receive_sender_websocket(ws):
    while True:
        raw_message = ws.receive()
        if raw_message is None:
            break
        data = json.loads(raw_message)
        with state_lock:
            _update_latest_detection(data)
            viewer_message = _viewer_message()
        _queue_viewer_broadcast(viewer_message)


@sock.route("/ws/sender")
def ws_sender(ws):
    _receive_sender_websocket(ws)


@sock.route("/ws/viewer")
def ws_viewer(ws):
    with viewer_sockets_lock:
        viewer_sockets.add(ws)
    try:
        with state_lock:
            ws.send(json.dumps(_viewer_message(), ensure_ascii=False))
        while True:
            try:
                message = ws.receive(timeout=30)
                if message is None:
                    break
            except TimeoutError:
                ws.send(json.dumps({"type": "ping"}))
            except Exception:
                break
    finally:
        with viewer_sockets_lock:
            viewer_sockets.discard(ws)


@app.route("/api/status")
def api_status():
    return jsonify(_resolve_status())


@app.route("/api/latest")
def api_latest():
    return jsonify({"data": latest_detection})


@app.route("/video_feed")
def video_feed():
    def mjpeg_stream():
        last_sent_sequence = -1
        while True:
            with latest_frame_condition:
                if latest_frame_sequence == last_sent_sequence:
                    latest_frame_condition.wait(timeout=MJPEG_KEEPALIVE_SECONDS)
                frame = latest_frame_bytes or PLACEHOLDER_FRAME_BYTES
                last_sent_sequence = latest_frame_sequence

            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

    return Response(mjpeg_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/cctvs")
def api_cctvs():
    _ensure_cctv_records()
    return jsonify({"items": [
        {
            "index": index,
            "name": item["name"],
            "selected": index == selected_index,
        }
        for index, item in enumerate(cctv_records)
    ]})


@app.route("/api/control")
def api_control():
    selected = _selected_record()
    return jsonify(
        {
            "selected_index": selected_index,
            "selected_name": selected["name"],
            "cctv_url": selected.get("cctv_url", ""),
            "stream_url": selected.get("stream_url", ""),
            "selection_version": selection_version,
        }
    )


@app.route("/api/select/<int:index>", methods=["POST"])
def api_select(index):
    global selected_index, selection_version
    _ensure_cctv_records()
    if index < 0 or index >= len(cctv_records):
        return jsonify({"ok": False, "error": "Invalid CCTV index"}), 400
    selected_index = index
    selection_version += 1
    return jsonify({"ok": True, "status": _resolve_status()})


threading.Thread(target=_viewer_broadcast_worker, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

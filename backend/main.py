import html
import os
from collections import deque
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, request
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

# This Railway demo keeps state in memory.
# If Railway restarts the service, these values are reset.
latest_detection = None
selected_index = 0

HISTORY_LIMIT = 36
traffic_up_history = deque([0], maxlen=HISTORY_LIMIT)
traffic_down_history = deque([0], maxlen=HISTORY_LIMIT)
accident_probability_history = deque([0], maxlen=HISTORY_LIMIT)

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


def _calculate_metrics(detection):
    if not detection:
        return {
            "traffic_count": 0,
            "traffic_up": 0,
            "traffic_down": 0,
            "accident_probability": 0,
            "accident_status": "-",
        }

    confidence = float(detection.get("confidence", 0) or 0)
    traffic_count = max(1, round(confidence * 10))
    traffic_up = round(traffic_count * 0.55)
    traffic_down = max(0, traffic_count - traffic_up)
    imbalance = abs(traffic_up - traffic_down)
    accident_probability = min(99, round(12 + traffic_count * 8 + imbalance * 3))

    return {
        "traffic_count": traffic_count,
        "traffic_up": traffic_up,
        "traffic_down": traffic_down,
        "accident_probability": accident_probability,
        "accident_status": f"{accident_probability}%",
    }


def _append_metric_history(metrics):
    traffic_up_history.append(metrics["traffic_up"])
    traffic_down_history.append(metrics["traffic_down"])
    accident_probability_history.append(metrics["accident_probability"])


def _get_cctv_items():
    return [
        {
            "index": index,
            "name": name,
            "selected": index == selected_index,
        }
        for index, name in enumerate(CCTV_ITEMS)
    ]


def _get_status():
    metrics = _calculate_metrics(latest_detection)
    return {
        "selected_index": selected_index,
        "selected_name": CCTV_ITEMS[selected_index],
        "traffic_count": metrics["traffic_count"],
        "traffic_up": metrics["traffic_up"],
        "traffic_down": metrics["traffic_down"],
        "traffic_up_history": list(traffic_up_history),
        "traffic_down_history": list(traffic_down_history),
        "accident_probability": metrics["accident_probability"],
        "accident_probability_history": list(accident_probability_history),
        "accident_status": metrics["accident_status"],
        "stream_status": "연결됨" if latest_detection else "준비 중",
        "player_url": "/video_feed",
        "cctv_count": len(CCTV_ITEMS),
        "yolo_enabled": latest_detection is not None,
        "roi_enabled": False,
        "roi_path": "Railway remote demo backend",
        "latest_detection": latest_detection,
    }


def _build_svg_frame():
    metrics = _calculate_metrics(latest_detection)
    if latest_detection:
        class_name = html.escape(str(latest_detection.get("class_name", "-")))
        confidence = float(latest_detection.get("confidence", 0) or 0)
        bbox = html.escape(str(latest_detection.get("bbox", "-")))
        timestamp = html.escape(str(latest_detection.get("timestamp", "-")))
        label = f"{class_name} {confidence:.2f}"
    else:
        class_name = "-"
        bbox = "-"
        timestamp = "waiting for detection data"
        label = "No detection data"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
  <defs>
    <pattern id="grid" width="42" height="42" patternUnits="userSpaceOnUse">
      <path d="M 42 0 L 0 0 0 42" fill="none" stroke="rgba(93,163,255,0.16)" stroke-width="1"/>
    </pattern>
  </defs>
  <rect width="960" height="540" fill="#121822"/>
  <rect width="960" height="540" fill="url(#grid)"/>
  <rect x="22" y="22" width="916" height="496" fill="none" stroke="#3e4e68" stroke-width="2"/>
  <text x="28" y="54" fill="#eef3f8" font-family="Arial, sans-serif" font-size="28" font-weight="700">Detection Screen</text>
  <text x="28" y="104" fill="#78b6ff" font-family="Arial, sans-serif" font-size="24" font-weight="700">{label}</text>
  <rect x="220" y="150" width="330" height="220" fill="none" stroke="#5dff9b" stroke-width="4"/>
  <rect x="220" y="116" width="180" height="34" rx="6" fill="#5dff9b"/>
  <text x="232" y="139" fill="#0b1a12" font-family="Arial, sans-serif" font-size="18" font-weight="700">{label}</text>
  <rect x="28" y="404" width="610" height="84" rx="12" fill="rgba(18,24,34,0.82)" stroke="rgba(94,110,138,0.7)"/>
  <text x="48" y="434" fill="#eef3f8" font-family="Arial, sans-serif" font-size="20" font-weight="700">{class_name}</text>
  <text x="48" y="460" fill="#a5b0c4" font-family="Arial, sans-serif" font-size="16">bbox: {bbox}</text>
  <text x="48" y="482" fill="#a5b0c4" font-family="Arial, sans-serif" font-size="16">{timestamp}</text>
  <text x="740" y="434" fill="#a5b0c4" font-family="Arial, sans-serif" font-size="16">traffic</text>
  <text x="740" y="476" fill="#eef3f8" font-family="Arial, sans-serif" font-size="44" font-weight="700">{metrics["traffic_count"]}</text>
</svg>"""


@app.route("/", methods=["GET"])
def index():
    return jsonify(
        {
            "message": "Jetson Nano object detection demo backend is running",
            "routes": [
                "/health",
                "/api/detection",
                "/api/latest",
                "/api/status",
                "/api/cctvs",
                "/api/select/<index>",
                "/video_feed",
            ],
        }
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/detection", methods=["POST"])
def receive_detection():
    global latest_detection

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "JSON body is required"}), 400

    required_fields = ["class_name", "confidence", "bbox"]
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Missing required field(s)",
                    "missing_fields": missing_fields,
                }
            ),
            400,
        )

    latest_detection = {
        "class_name": data["class_name"],
        "confidence": data["confidence"],
        "bbox": data["bbox"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _append_metric_history(_calculate_metrics(latest_detection))

    return jsonify({"status": "ok", "data": latest_detection})


@app.route("/api/latest", methods=["GET"])
def get_latest_detection():
    return jsonify({"data": latest_detection})


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(_get_status())


@app.route("/api/cctvs", methods=["GET"])
def api_cctvs():
    return jsonify({"items": _get_cctv_items()})


@app.route("/api/select/<int:index>", methods=["POST"])
def api_select(index):
    global selected_index

    if index < 0 or index >= len(CCTV_ITEMS):
        return jsonify({"ok": False, "error": "Invalid CCTV index"}), 400

    selected_index = index
    return jsonify({"ok": True, "status": _get_status()})


@app.route("/video_feed", methods=["GET"])
def video_feed():
    # The original capstone server returns an MJPEG stream generated by OpenCV.
    # This remote demo returns a lightweight SVG frame so Vercel can display
    # the same route without requiring YOLO/OpenCV on Railway.
    return Response(_build_svg_frame(), mimetype="image/svg+xml")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

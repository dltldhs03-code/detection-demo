import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from utils.analysis import (
    analyze_directional_congestion,
    apply_roi_mask_to_frame,
    collect_detections,
)
from utils.app_config import (
    CCTV_INDEX,
    DETECTION_BACKEND_URL,
    DETECTION_CONTROL_ENABLED,
    DETECTION_CONTROL_INTERVAL_SECONDS,
    DETECTION_CONTROL_TIMEOUT_SECONDS,
    DETECTION_LOG_SEND,
    DETECTION_MAX_IN_FLIGHT,
    DETECTION_PLAYER_URL,
    DETECTION_SEND_INTERVAL_SECONDS,
    DETECTION_TRANSPORT,
    DETECTION_WS_HTTP_FALLBACK,
    DETECTION_WS_URL,
    DIRECT_CCTV_NAME,
    DIRECT_CCTV_URL,
    DOWNBOUND_LABEL,
    FRAME_WAIT_TIMEOUT_SECONDS,
    REMOTE_CCTV_NAMES,
    UPBOUND_LABEL,
)
from utils.pruned_yolo_cctv import PrunedYOLODetector
from utils.remote import (
    DetectionWebSocketSender,
    WebSocketReconnectWaiting,
    build_detection_payload,
    derive_backend_url_from_ws_url,
    derive_ws_url_from_backend_url,
    encode_frame_to_base64_jpeg,
    get_detection_session,
    post_detection_to_backend,
)
from utils.renderer import draw_tracking_results
from utils.roi import build_roi_path, load_roi_data
from utils.stream import (
    connect_capture_with_retry,
    fetch_cctv_dataframe,
    read_frame_with_timeout,
    select_cctv,
)


class PrunedCCTVPipeline:
    """CCTV 수신, detection 실행, 분석 모듈 조합을 담당하는 메인 파이프라인."""

    def __init__(
        self,
        cctv_index=None,
        cctv_url="",
        cctv_name="",
        roi_path=None,
        use_roi=False,
    ):
        self.detector = PrunedYOLODetector()
        self.cctv_df = fetch_cctv_dataframe()
        self.cctv_items = self.cctv_df["cctvname"].astype(str).fillna("").tolist()
        self.remote_cctv_index_by_name = {
            name: index for index, name in enumerate(REMOTE_CCTV_NAMES)
        }

        self.cctv_index = CCTV_INDEX if cctv_index is None else cctv_index
        self.direct_cctv_url = cctv_url or DIRECT_CCTV_URL
        self.direct_cctv_name = cctv_name or DIRECT_CCTV_NAME
        self.use_roi = bool(use_roi)
        self._custom_roi_path = roi_path
        self.roi_path = roi_path
        self.rois = []

        self.capture = None
        self.current_stream_url = None
        self.current_cctv_name = "-"
        self.current_cctv_url = ""
        self.current_index = 0
        self.remote_backend_url = DETECTION_BACKEND_URL or derive_backend_url_from_ws_url(DETECTION_WS_URL)
        self.remote_transport = DETECTION_TRANSPORT
        self.remote_ws_url = DETECTION_WS_URL or derive_ws_url_from_backend_url(self.remote_backend_url)
        self.remote_control_enabled = (
            DETECTION_CONTROL_ENABLED
            and bool(self.remote_backend_url)
            and not bool(self.direct_cctv_url)
        )
        self.remote_control_interval = DETECTION_CONTROL_INTERVAL_SECONDS
        self._last_remote_control_check_at = 0.0
        self._seen_remote_selection_version = None
        self._remote_control_in_flight = False
        self._pending_remote_control = None
        self._remote_control_lock = threading.Lock()
        self._remote_control_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="detection-control",
        )
        self._websocket_sender = (
            DetectionWebSocketSender(self.remote_ws_url)
            if self.remote_transport == "websocket" and self.remote_ws_url
            else None
        )
        self.remote_send_interval = DETECTION_SEND_INTERVAL_SECONDS
        self.remote_max_in_flight = 1 if self.remote_transport == "websocket" else DETECTION_MAX_IN_FLIGHT
        self._last_remote_send_at = 0.0
        self._remote_send_in_flight = 0
        self._pending_remote_payload = None
        self._remote_send_lock = threading.Lock()
        self._remote_send_executor = ThreadPoolExecutor(
            max_workers=DETECTION_MAX_IN_FLIGHT,
            thread_name_prefix="detection-send",
        )
        self._frame_sequence = 0
        self._previous_direction_centers = {
            "up": [],
            "down": [],
        }

    def get_cctv_items(self):
        return [
            {
                "index": index,
                "name": name,
                "selected": index == self.current_index,
            }
            for index, name in enumerate(self.cctv_items)
        ]

    def open(self):
        if self.direct_cctv_url:
            self.current_cctv_name = self.direct_cctv_name or "직접 지정 CCTV"
            self.current_cctv_url = self.direct_cctv_url
            self.current_index = 0
        else:
            cctv_name, cctv_url, selected_index = select_cctv(self.cctv_df, self.cctv_index)
            self.current_cctv_name = str(cctv_name)
            self.current_cctv_url = str(cctv_url)
            self.current_index = int(selected_index)

        self._update_roi_path()
        self._reset_direction_history()
        self.detector.reset_tracking()
        self._open_capture()
        return self.current_cctv_name

    def select_cctv(self, index):
        if index < 0 or index >= len(self.cctv_df):
            raise IndexError("CCTV 인덱스 범위를 벗어났습니다.")

        previous_index = self.current_index
        previous_name = self.current_cctv_name
        previous_url = self.current_cctv_url
        previous_roi_path = self.roi_path
        previous_rois = list(self.rois)
        previous_stream_url = self.current_stream_url
        previous_capture = self.capture

        row = self.cctv_df.iloc[index]
        self.current_index = int(index)
        self.current_cctv_name = str(row["cctvname"])
        self.current_cctv_url = str(row["cctvurl"])
        self._update_roi_path()
        self.capture = None
        self._reset_direction_history()
        self.detector.reset_tracking()

        try:
            self._open_capture()
        except Exception:
            self.current_index = previous_index
            self.current_cctv_name = previous_name
            self.current_cctv_url = previous_url
            self.roi_path = previous_roi_path
            self.rois = previous_rois
            self.current_stream_url = previous_stream_url
            self.capture = previous_capture
            raise

        if previous_capture is not None:
            previous_capture.release()

    def reload_rois(self):
        if self.roi_path and self.use_roi:
            self.rois = load_roi_data(self.roi_path)
        else:
            self.rois = []

    def _update_roi_path(self):
        if self._custom_roi_path:
            self.roi_path = self._custom_roi_path
        else:
            self.roi_path = build_roi_path(self.current_index)
        self.reload_rois()

    def _open_capture(self):
        if not self.current_cctv_url:
            raise RuntimeError("현재 CCTV URL이 비어 있습니다.")

        if self.capture is not None:
            self.capture.release()
            self.capture = None

        self.current_stream_url, self.capture = connect_capture_with_retry(self.current_cctv_url)

    def _reset_direction_history(self):
        self._previous_direction_centers = {
            "up": {},
            "down": {},
        }

    def _get_remote_display_index(self):
        return self.remote_cctv_index_by_name.get(self.current_cctv_name, self.current_index)

    def _find_raw_cctv_index_by_name(self, selected_name):
        if not selected_name:
            return None

        for index, name in enumerate(self.cctv_items):
            if str(name) == str(selected_name):
                return index

        return None

    def _schedule_remote_control_if_needed(self):
        if not self.remote_control_enabled:
            return

        now = time.time()
        if now - self._last_remote_control_check_at < self.remote_control_interval:
            return
        self._last_remote_control_check_at = now

        with self._remote_control_lock:
            if self._remote_control_in_flight:
                return
            self._remote_control_in_flight = True

        future = self._remote_control_executor.submit(self._fetch_remote_control)
        future.add_done_callback(self._remote_control_done)

    def _fetch_remote_control(self):
        try:
            response = get_detection_session().get(
                f"{self.remote_backend_url}/api/control",
                timeout=DETECTION_CONTROL_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            if DETECTION_LOG_SEND:
                print(f"remote control fetch failed: {exc}")
            return None

    def _remote_control_done(self, future):
        try:
            control = future.result()
        except Exception as exc:
            control = None
            if DETECTION_LOG_SEND:
                print(f"remote control fetch failed: {exc}")

        with self._remote_control_lock:
            if control is not None:
                self._pending_remote_control = control
            self._remote_control_in_flight = False

    def _apply_remote_control_if_available(self):
        with self._remote_control_lock:
            control = self._pending_remote_control
            self._pending_remote_control = None

        if control is None:
            return

        version = control.get("selection_version")
        if self._seen_remote_selection_version is None:
            self._seen_remote_selection_version = version
            if not version:
                return
        elif version == self._seen_remote_selection_version:
            return

        self._seen_remote_selection_version = version
        target_index = self._find_raw_cctv_index_by_name(control.get("selected_name"))
        if target_index is None:
            try:
                fallback_index = int(control.get("selected_index"))
            except (TypeError, ValueError):
                return
            if 0 <= fallback_index < len(self.cctv_df):
                target_index = fallback_index

        if target_index is None or target_index == self.current_index:
            return

        try:
            print(
                "remote CCTV selection:",
                f"{self.current_cctv_name} -> {self.cctv_items[target_index]}",
            )
            self.select_cctv(target_index)
        except Exception as exc:
            print(f"remote CCTV selection failed: {exc}")

    def _build_remote_payload(self, frame, detections, rois, frame_id, timestamp):
        frame_height, frame_width = frame.shape[:2]
        return {
            "backend_url": self.remote_backend_url,
            "detections": [dict(item) for item in detections],
            "rois": [
                {
                    "points": [[int(x), int(y)] for x, y in points],
                    "label": int(label),
                }
                for points, label in rois
            ],
            "frame_id": int(frame_id),
            "frame_width": int(frame_width),
            "frame_height": int(frame_height),
            "timestamp": str(timestamp),
            "selected_name": self.current_cctv_name,
            "selected_index": int(self._get_remote_display_index()),
            "cctv_url": self.current_cctv_url,
            "stream_url": self.current_stream_url,
            "player_url": DETECTION_PLAYER_URL or self.current_stream_url or self.current_cctv_url,
            "stream_status": "연결됨",
            "roi_enabled": bool(rois),
            "roi_path": self.roi_path,
            "frame": frame,
        }

    def _submit_remote_payload_locked(self, payload):
        self._remote_send_in_flight += 1
        self._last_remote_send_at = time.time()
        future = self._remote_send_executor.submit(
            self._send_detection_worker,
            **payload,
        )
        future.add_done_callback(self._remote_send_done)

    def _send_detection_if_needed(self, frame, detections, rois, frame_id, timestamp):
        if self.remote_transport == "websocket":
            if not self._websocket_sender:
                return
        elif not self.remote_backend_url:
            return

        now = time.time()
        if now - self._last_remote_send_at < self.remote_send_interval:
            return

        payload = self._build_remote_payload(frame, detections, rois, frame_id, timestamp)
        with self._remote_send_lock:
            if self._remote_send_in_flight >= self.remote_max_in_flight:
                self._pending_remote_payload = payload
                return
            self._submit_remote_payload_locked(payload)

    def _remote_send_done(self, _future):
        with self._remote_send_lock:
            self._remote_send_in_flight = max(0, self._remote_send_in_flight - 1)
            if (
                self._pending_remote_payload is not None
                and self._remote_send_in_flight < self.remote_max_in_flight
            ):
                payload = self._pending_remote_payload
                self._pending_remote_payload = None
                self._submit_remote_payload_locked(payload)

    def _send_detection_worker(self, **payload):
        try:
            started_at = time.time()
            transport = self.remote_transport
            frame_jpeg = encode_frame_to_base64_jpeg(payload.get("frame"))
            if self.remote_transport == "websocket":
                _data, websocket_data, payload_size = build_detection_payload(
                    detections=payload["detections"],
                    rois=payload["rois"],
                    frame_id=payload["frame_id"],
                    frame_width=payload["frame_width"],
                    frame_height=payload["frame_height"],
                    timestamp=payload["timestamp"],
                    selected_name=payload["selected_name"],
                    selected_index=payload["selected_index"],
                    cctv_url=payload["cctv_url"],
                    stream_url=payload["stream_url"],
                    player_url=payload["player_url"],
                    stream_status=payload["stream_status"],
                    roi_enabled=payload["roi_enabled"],
                    roi_path=payload["roi_path"],
                    frame_jpeg=frame_jpeg,
                )
                try:
                    self._websocket_sender.send(websocket_data)
                    encoded_size = payload_size
                except WebSocketReconnectWaiting:
                    return
                except Exception as ws_exc:
                    if not DETECTION_WS_HTTP_FALLBACK or not self.remote_backend_url:
                        raise

                    encoded_size = post_detection_to_backend(
                        **payload,
                        frame_jpeg=frame_jpeg,
                        session=get_detection_session(),
                    )
                    transport = "http-fallback"
                    if DETECTION_LOG_SEND:
                        print(f"websocket send failed, used HTTP fallback: {ws_exc}")
            else:
                encoded_size = post_detection_to_backend(
                    **payload,
                    frame_jpeg=frame_jpeg,
                    session=get_detection_session(),
                )
            if DETECTION_LOG_SEND:
                elapsed = time.time() - started_at
                print(
                    "remote detection sent:",
                    f"{elapsed:.2f}s",
                    f"{encoded_size / 1024:.1f}KB",
                    f"transport={transport}",
                )
        except requests.RequestException as exc:
            print(f"remote detection send failed: {exc}")
        except Exception as exc:
            print(f"remote detection send failed: {exc}")

    def process_next_frame(self):
        self._schedule_remote_control_if_needed()
        self._apply_remote_control_if_available()

        if self.capture is None or not self.capture.isOpened():
            self._open_capture()

        ok, frame = read_frame_with_timeout(self.capture, FRAME_WAIT_TIMEOUT_SECONDS)
        if not ok:
            if self.capture is not None:
                self.capture.release()
            time.sleep(1)
            self._open_capture()
            ok, frame = read_frame_with_timeout(self.capture, FRAME_WAIT_TIMEOUT_SECONDS)
            if not ok:
                raise RuntimeError("프레임 수신 실패")

        rois = self.rois if self.use_roi else []
        inference_frame = apply_roi_mask_to_frame(frame, rois) if rois else frame
        self._frame_sequence += 1
        frame_id = self._frame_sequence
        frame_timestamp = datetime.now(timezone.utc).isoformat()
        results = self.detector.predict(inference_frame)
        detections = collect_detections(results[0], rois=rois)
        congestion, current_direction_centers = analyze_directional_congestion(
            frame.shape,
            detections,
            rois,
            self._previous_direction_centers,
        )
        self._previous_direction_centers = current_direction_centers
        annotated_frame = draw_tracking_results(frame, detections, rois=rois)
        traffic_count = len(detections)
        traffic_up = int(congestion["up"]["count"])
        traffic_down = int(congestion["down"]["count"])
        self._send_detection_if_needed(annotated_frame, detections, rois, frame_id, frame_timestamp)

        return {
            "frame": annotated_frame,
            "frame_id": frame_id,
            "timestamp": frame_timestamp,
            "traffic_count": traffic_count,
            "traffic_up": traffic_up,
            "traffic_down": traffic_down,
            "detections": detections,
            "congestion": congestion,
            "rois": [
                {
                    "points": [[int(x), int(y)] for x, y in points],
                    "label": int(label),
                }
                for points, label in rois
            ],
            "frame_width": int(frame.shape[1]),
            "frame_height": int(frame.shape[0]),
            "selected_name": self.current_cctv_name,
            "selected_index": self.current_index,
            "stream_url": self.current_stream_url,
            "stream_status": "연결됨",
            "yolo_enabled": True,
            "roi_enabled": bool(rois),
            "roi_path": self.roi_path,
        }

    def release(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        if self._websocket_sender is not None:
            self._websocket_sender.close()
        self._remote_control_executor.shutdown(wait=False, cancel_futures=True)
        self._remote_send_executor.shutdown(wait=False, cancel_futures=True)

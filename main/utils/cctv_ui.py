"""Flask 기반 CCTV 탐지 웹 UI."""

import atexit
from collections import deque
from pathlib import Path
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template
from werkzeug.serving import WSGIRequestHandler

from utils.pipeline import PrunedCCTVPipeline

STREAM_LOOP_DELAY_SECONDS = 0.03
ALLOWED_CCTV_NAMES = [
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


class QuietRequestHandler(WSGIRequestHandler):
    def log_request(self, code="-", size="-"):
        if self.path.startswith("/api/status") or self.path.startswith("/video_feed"):
            return
        super().log_request(code, size)


class VideoService:
    def __init__(self, pipeline: PrunedCCTVPipeline):
        self.pipeline = pipeline
        self.lock = threading.Lock()
        self.traffic_count = 0
        self.traffic_up = 0
        self.traffic_down = 0
        self.accident_probability = 0
        self.accident_status = "-"
        self.congestion_up = False
        self.congestion_down = False
        self.stream_status = "준비 중"
        self.selected_index = 0
        self.selected_name = "-"
        self.traffic_history_limit = 36
        self.traffic_up_history = deque([0], maxlen=self.traffic_history_limit)
        self.traffic_down_history = deque([0], maxlen=self.traffic_history_limit)
        self.last_frame = self._build_placeholder("loading...")
        self.last_jpeg = self._encode_jpeg(self.last_frame)
        self.stop_event = threading.Event()
        self.roi_path = pipeline.roi_path
        self.visible_cctv_items = self._build_visible_cctv_items()

        self.pipeline.open()
        self.selected_index = self._to_visible_index(self.pipeline.current_index)
        self.selected_name = self.pipeline.current_cctv_name
        self.stream_status = "연결됨"

        self.reader_thread = threading.Thread(target=self._frame_loop, daemon=True)
        self.reader_thread.start()

    def _build_placeholder(self, message):
        frame = np.full((540, 960, 3), (18, 24, 34), dtype=np.uint8)
        cv2.putText(frame, "Detection Screen", (28, 52), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (230, 236, 245), 2, cv2.LINE_AA)
        cv2.putText(frame, message, (28, 104), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (120, 182, 255), 2, cv2.LINE_AA)
        cv2.rectangle(frame, (22, 22), (938, 518), (62, 78, 104), 2)
        return frame

    def _encode_jpeg(self, frame):
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            return None
        return encoded.tobytes()

    def _set_frame_locked(self, frame, traffic_count=None, traffic_up=None, traffic_down=None, congestion=None, status=None):
        self.last_frame = frame
        encoded = self._encode_jpeg(frame)
        if encoded is not None:
            self.last_jpeg = encoded
        if traffic_count is not None:
            self.traffic_count = traffic_count
            self._update_traffic_metrics_locked(
                traffic_count,
                traffic_up=traffic_up,
                traffic_down=traffic_down,
                congestion=congestion,
            )
        if status is not None:
            self.stream_status = status

    def _build_visible_cctv_items(self):
        visible_items = []
        for visible_index, allowed_name in enumerate(ALLOWED_CCTV_NAMES):
            for raw_index, name in enumerate(self.pipeline.cctv_items):
                if str(name) != allowed_name:
                    continue
                visible_items.append(
                    {
                        "index": visible_index,
                        "raw_index": raw_index,
                        "name": name,
                    }
                )
                break
        return visible_items

    def _to_visible_index(self, raw_index):
        for item in self.visible_cctv_items:
            if item["raw_index"] == raw_index:
                return item["index"]
        return 0

    def _to_raw_index(self, visible_index):
        for item in self.visible_cctv_items:
            if item["index"] == visible_index:
                return item["raw_index"]
        raise IndexError("UI에서 허용되지 않은 CCTV 인덱스입니다.")

    def _update_traffic_metrics_locked(self, traffic_count, traffic_up=None, traffic_down=None, congestion=None):
        congestion = congestion or {}
        up_congestion = bool(congestion.get("up", {}).get("is_congested", False))
        down_congestion = bool(congestion.get("down", {}).get("is_congested", False))
        self.congestion_up = up_congestion
        self.congestion_down = down_congestion

        if traffic_count <= 0:
            self.traffic_up = 0
            self.traffic_down = 0
            self.accident_probability = 0
        else:
            self.traffic_up = int(traffic_up or 0)
            self.traffic_down = int(traffic_down or 0)
            imbalance = abs(self.traffic_up - self.traffic_down)
            congestion_bonus = 35 * int(up_congestion) + 35 * int(down_congestion)
            self.accident_probability = int(
                min(99, 12 + (traffic_count * 8) + (imbalance * 3) + congestion_bonus)
            )

        if up_congestion and down_congestion:
            self.accident_status = "양방향 복잡"
        elif up_congestion:
            self.accident_status = "상행 복잡"
        elif down_congestion:
            self.accident_status = "하행 복잡"
        else:
            self.accident_status = f"{self.accident_probability}%"

        self.traffic_up_history.append(self.traffic_up)
        self.traffic_down_history.append(self.traffic_down)

    def _frame_loop(self):
        while not self.stop_event.is_set():
            try:
                output = self.pipeline.process_next_frame()
                with self.lock:
                    self.selected_index = self._to_visible_index(output["selected_index"])
                    self.selected_name = output["selected_name"]
                    self._set_frame_locked(
                        output["frame"],
                        traffic_count=output["traffic_count"],
                        traffic_up=output.get("traffic_up"),
                        traffic_down=output.get("traffic_down"),
                        congestion=output.get("congestion"),
                        status=output["stream_status"],
                    )
                    self.roi_path = output.get("roi_path", self.pipeline.roi_path)
            except Exception as exc:
                with self.lock:
                    self.accident_status = "stream error"
                    self._set_frame_locked(
                        self._build_placeholder("stream error"),
                        traffic_count=0,
                        status=str(exc)[:60],
                    )
            time.sleep(STREAM_LOOP_DELAY_SECONDS)

    def select_index(self, index):
        with self.lock:
            raw_index = self._to_raw_index(index)
            self.pipeline.select_cctv(raw_index)
            self.selected_index = index
            self.selected_name = self.pipeline.current_cctv_name
            self.roi_path = self.pipeline.roi_path
            self.traffic_count = 0
            self.traffic_up = 0
            self.traffic_down = 0
            self.accident_probability = 0
            self.accident_status = "-"
            self.congestion_up = False
            self.congestion_down = False
            self.traffic_up_history = deque([0], maxlen=self.traffic_history_limit)
            self.traffic_down_history = deque([0], maxlen=self.traffic_history_limit)
            self.stream_status = "연결됨"

    def get_status(self):
        with self.lock:
            return {
                "selected_index": self.selected_index,
                "selected_name": self.selected_name,
                "traffic_count": self.traffic_count,
                "traffic_up": self.traffic_up,
                "traffic_down": self.traffic_down,
                "traffic_up_history": list(self.traffic_up_history),
                "traffic_down_history": list(self.traffic_down_history),
                "accident_probability": self.accident_probability,
                "accident_status": self.accident_status,
                "congestion_up": self.congestion_up,
                "congestion_down": self.congestion_down,
                "stream_status": self.stream_status,
                "player_url": "/video_feed",
                "cctv_count": len(self.visible_cctv_items),
                "yolo_enabled": True,
                "roi_enabled": bool(self.pipeline.rois),
                "roi_path": self.roi_path,
            }

    def get_cctv_items(self):
        return [
            {
                "index": item["index"],
                "name": item["name"],
                "selected": item["index"] == self.selected_index,
            }
            for item in self.visible_cctv_items
        ]

    def get_jpeg_bytes(self):
        with self.lock:
            return self.last_jpeg

    def release(self):
        self.stop_event.set()
        if hasattr(self, "reader_thread") and self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1.0)
        self.pipeline.release()


def create_app(pipeline: PrunedCCTVPipeline):
    base_dir = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
    )
    service = VideoService(pipeline)
    atexit.register(service.release)

    @app.route("/")
    def index():
        return render_template("index.html", cctvs=service.get_cctv_items(), status=service.get_status())

    @app.route("/api/status")
    def api_status():
        return jsonify(service.get_status())

    @app.route("/api/cctvs")
    def api_cctvs():
        return jsonify({"items": service.get_cctv_items()})

    @app.route("/api/select/<int:index>", methods=["POST"])
    def api_select(index):
        try:
            service.select_index(index)
        except (RuntimeError, IndexError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "status": service.get_status()})

    @app.route("/video_feed")
    def video_feed():
        def mjpeg_stream():
            while True:
                jpg = service.get_jpeg_bytes()
                if jpg is None:
                    time.sleep(0.1)
                    continue
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                time.sleep(0.03)

        return Response(mjpeg_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")

    app.config["VIDEO_SERVICE"] = service
    return app


def main():
    raise SystemExit("웹 UI 실행은 `python3 main.py --use-roi`를 사용해주세요.")


if __name__ == "__main__":
    main()

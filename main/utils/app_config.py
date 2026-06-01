import os
import sys
from pathlib import Path

import torch


# ultralytics가 홈 디렉터리에 설정 파일을 만들지 못하는 환경 대응
os.environ.setdefault("YOLO_CONFIG_DIR", "/tmp/Ultralytics")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

UTILS_DIR = Path(__file__).resolve().parent
MAIN_DIR = UTILS_DIR.parent
PROJECT_ROOT = MAIN_DIR.parent


def resolve_local_path(*parts):
    """`main/` 내부 우선, 없으면 프로젝트 루트에서 파일을 찾습니다."""
    local_path = MAIN_DIR.joinpath(*parts)
    if local_path.exists():
        return local_path

    root_path = PROJECT_ROOT.joinpath(*parts)
    if root_path.exists():
        return root_path

    return local_path


VENDORED_ULTRALYTICS_ROOT = resolve_local_path("yolov12", "yolov12")
if VENDORED_ULTRALYTICS_ROOT.exists():
    sys.path.insert(0, str(VENDORED_ULTRALYTICS_ROOT))

API_KEY = os.environ.get("ITS_API_KEY", "").strip()
API_URL = "https://openapi.its.go.kr:9443/cctvInfo"
WEIGHTS_PATH = resolve_local_path("pruned.pt")
YAML_PATH = resolve_local_path("pruned.yaml")
DIRECT_CCTV_URL = ""
DIRECT_CCTV_NAME = ""

TARGET_NAME = "청주"
CCTV_INDEX = 2
VEHICLE_CLASSES = [0]
CONFIDENCE_THRESHOLD = 0.4
ROI_BBOX_OVERLAP_THRESHOLD = 0.3
TRACKER_CONFIG = os.environ.get("TRACKER_CONFIG", "bytetrack.yaml").strip() or "bytetrack.yaml"
UPBOUND_LABEL = 0
DOWNBOUND_LABEL = 1
CONGESTION_OVERLAP_THRESHOLD = 0.8
CONGESTION_CENTER_MOVEMENT_THRESHOLD = 20.0
INFERENCE_DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
LIST_LIMIT = 20
FRAME_WAIT_TIMEOUT_SECONDS = 10
FRAME_WAIT_INTERVAL_SECONDS = 0.2
STREAM_CONNECT_RETRY_COUNT = 2
STREAM_CONNECT_RETRY_DELAY_SECONDS = 0.5
DETECTION_BACKEND_URL = os.environ.get("DETECTION_BACKEND_URL", "").rstrip("/")
DETECTION_PLAYER_URL = os.environ.get("DETECTION_PLAYER_URL", "").strip()
DETECTION_TRANSPORT = os.environ.get("DETECTION_TRANSPORT", "http").strip().lower()
DETECTION_WS_URL = os.environ.get("DETECTION_WS_URL", "").strip()
DETECTION_WS_PATH = os.environ.get("DETECTION_WS_PATH", "/ws/sender").strip() or "/ws/sender"
DETECTION_SEND_INTERVAL_SECONDS = float(os.environ.get("DETECTION_SEND_INTERVAL", "0.12"))
DETECTION_CONTROL_ENABLED = os.environ.get("DETECTION_CONTROL_ENABLED", "1").lower() in {
    "1",
    "true",
    "yes",
}
DETECTION_CONTROL_INTERVAL_SECONDS = float(os.environ.get("DETECTION_CONTROL_INTERVAL", "0.5"))
DETECTION_CONTROL_TIMEOUT_SECONDS = float(os.environ.get("DETECTION_CONTROL_TIMEOUT", "0.7"))
DETECTION_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("DETECTION_REQUEST_TIMEOUT", "3"))
DETECTION_JPEG_QUALITY = int(os.environ.get("DETECTION_JPEG_QUALITY", "45"))
DETECTION_FRAME_WIDTH = int(os.environ.get("DETECTION_FRAME_WIDTH", "0"))
DETECTION_MAX_IN_FLIGHT = max(1, int(os.environ.get("DETECTION_MAX_IN_FLIGHT", "1")))
DETECTION_WS_RECONNECT_MIN_SECONDS = float(os.environ.get("DETECTION_WS_RECONNECT_MIN", "1"))
DETECTION_WS_RECONNECT_MAX_SECONDS = float(os.environ.get("DETECTION_WS_RECONNECT_MAX", "10"))
DETECTION_WS_HTTP_FALLBACK = os.environ.get("DETECTION_WS_HTTP_FALLBACK", "0").lower() in {
    "1",
    "true",
    "yes",
}
DETECTION_LOG_SEND = os.environ.get("DETECTION_LOG_SEND", "").lower() in {"1", "true", "yes"}

REQUEST_PARAMS = {
    "apiKey": API_KEY,
    "type": "all",
    "cctvType": "1",
    "minX": 127.25,
    "maxX": 127.60,
    "minY": 36.50,
    "maxY": 36.80,
    "getType": "json",
}

REMOTE_CCTV_NAMES = [
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

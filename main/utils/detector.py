import torch
from ultralytics import YOLO

from utils.app_config import (
    CONFIDENCE_THRESHOLD,
    DETECTION_BACKEND_URL,
    DETECTION_CONTROL_ENABLED,
    DETECTION_FRAME_WIDTH,
    DETECTION_JPEG_QUALITY,
    DETECTION_LOG_SEND,
    DETECTION_MAX_IN_FLIGHT,
    DETECTION_REQUEST_TIMEOUT_SECONDS,
    DETECTION_SEND_INTERVAL_SECONDS,
    DETECTION_TRANSPORT,
    DETECTION_WS_URL,
    INFERENCE_DEVICE,
    TRACKER_CONFIG,
    VEHICLE_CLASSES,
    WEIGHTS_PATH,
    YAML_PATH,
)
from utils.remote import derive_ws_url_from_backend_url


def load_model():
    if not YAML_PATH.exists():
        raise FileNotFoundError(f"모델 설정 파일을 찾지 못했습니다: {YAML_PATH}")
    if not WEIGHTS_PATH.exists():
        raise FileNotFoundError(f"모델 가중치 파일을 찾지 못했습니다: {WEIGHTS_PATH}")

    original_torch_load = torch.load

    def patched_torch_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_torch_load(*args, **kwargs)

    try:
        torch.load = patched_torch_load
        model = YOLO(str(YAML_PATH), task="detect").load(str(WEIGHTS_PATH))
    finally:
        torch.load = original_torch_load

    if INFERENCE_DEVICE != "cpu":
        model.to(INFERENCE_DEVICE)

    print("YOLO model yaml:", YAML_PATH)
    print("YOLO model weights:", WEIGHTS_PATH)
    print("detection classes:", VEHICLE_CLASSES)
    print("inference device:", INFERENCE_DEVICE)
    print(
        "remote send settings:",
        f"transport={DETECTION_TRANSPORT}",
        f"ws_url={DETECTION_WS_URL or derive_ws_url_from_backend_url(DETECTION_BACKEND_URL) or '-'}",
        f"interval={DETECTION_SEND_INTERVAL_SECONDS}s",
        f"control={'on' if DETECTION_CONTROL_ENABLED else 'off'}",
        f"target_fps={1 / DETECTION_SEND_INTERVAL_SECONDS:.1f}",
        f"timeout={DETECTION_REQUEST_TIMEOUT_SECONDS}s",
        f"width={DETECTION_FRAME_WIDTH if DETECTION_FRAME_WIDTH > 0 else 'original'}",
        f"jpeg_quality={DETECTION_JPEG_QUALITY}",
        f"max_in_flight={DETECTION_MAX_IN_FLIGHT}",
    )
    print("tracker config:", TRACKER_CONFIG)
    return model


def run_inference(model, frame):
    """Ultralytics tracker를 사용해 detection과 tracking ID를 함께 생성합니다."""
    return model.track(
        frame,
        classes=VEHICLE_CLASSES,
        conf=CONFIDENCE_THRESHOLD,
        device=INFERENCE_DEVICE,
        persist=True,
        tracker=TRACKER_CONFIG,
        verbose=False,
    )


def reset_tracker_state(model):
    predictor = getattr(model, "predictor", None)
    if predictor is None:
        return

    trackers = getattr(predictor, "trackers", None) or []
    for tracker in trackers:
        if hasattr(tracker, "reset"):
            tracker.reset()

    if hasattr(predictor, "_feats"):
        predictor._feats = None

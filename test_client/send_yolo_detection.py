import argparse
import json
import time

import cv2
import requests
from ultralytics import YOLO


DEFAULT_BACKEND_URL = "https://detection-demo-production.up.railway.app"


def parse_source(value):
    if value.isdigit():
        return int(value)
    return value


def pick_best_detection(result):
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return {
            "class_name": "none",
            "confidence": 0.0,
            "bbox": [0, 0, 0, 0],
        }

    best_index = int(boxes.conf.argmax().item())
    xyxy = boxes.xyxy[best_index].int().cpu().tolist()
    class_id = int(boxes.cls[best_index].item())
    confidence = float(boxes.conf[best_index].item())
    names = result.names or {}

    return {
        "class_name": str(names.get(class_id, class_id)),
        "confidence": round(confidence, 4),
        "bbox": xyxy,
    }


def send_detection(backend_url, detection, annotated_frame):
    ok, encoded = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        raise RuntimeError("Failed to encode frame as JPEG")

    files = {
        "frame": ("frame.jpg", encoded.tobytes(), "image/jpeg"),
    }
    data = {
        "class_name": detection["class_name"],
        "confidence": str(detection["confidence"]),
        "bbox": json.dumps(detection["bbox"]),
    }

    response = requests.post(
        f"{backend_url}/api/detection",
        data=data,
        files=files,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def main():
    parser = argparse.ArgumentParser(
        description="Run YOLO on this laptop and send annotated frames to Railway.",
    )
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--source", default="0", help="Camera index, video file, or stream URL")
    parser.add_argument("--device", default=None, help="Example: cpu, 0, cuda:0")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between uploads")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.35)
    args = parser.parse_args()

    backend_url = args.backend_url.rstrip("/")
    model = YOLO(args.model)
    source = parse_source(args.source)
    capture = cv2.VideoCapture(source)

    if not capture.isOpened():
        raise RuntimeError(f"Failed to open source: {args.source}")

    print("Sending YOLO detections to:", backend_url)
    print("Press Ctrl+C to stop.")

    last_sent_at = 0.0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                time.sleep(0.2)
                continue

            now = time.time()
            if now - last_sent_at < args.interval:
                continue

            results = model.predict(
                frame,
                imgsz=args.imgsz,
                conf=args.conf,
                device=args.device,
                verbose=False,
            )
            result = results[0]
            detection = pick_best_detection(result)
            annotated_frame = result.plot()
            server_response = send_detection(backend_url, detection, annotated_frame)

            print("sent:", detection, "server:", server_response.get("status"))
            last_sent_at = now
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        capture.release()


if __name__ == "__main__":
    main()

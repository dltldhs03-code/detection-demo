import html
import json
import os
import base64
import threading
from collections import deque
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urljoin
from urllib.request import urlopen

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from flask_sock import Sock


app = Flask(__name__)
CORS(app)
sock = Sock(app)

# This Railway demo keeps state in memory.
# If Railway restarts the service, these values are reset.
latest_detection = None
latest_frame_bytes = None
latest_frame_mime = "image/jpeg"
latest_frame_base64 = ""
latest_frame_sequence = 0
selected_index = 0
selection_version = 0
state_lock = threading.Lock()
viewer_sockets = set()
viewer_sockets_lock = threading.Lock()
viewer_broadcast_condition = threading.Condition()
pending_viewer_message = None
frame_condition = threading.Condition()

HISTORY_LIMIT = 36
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

ITS_API_KEY = "f742615880e442b4a0e549771bbef99d"
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

STATIC_CCTV_RECORDS = [
    {"name": "[경부선] 천안호두휴게소", "cctv_url": "http://cctvsec.ktict.co.kr/120/iyt5f0iWzZUAEom6Bu/3dOte5b02QQcoqrbPROBbsAiFh+nz0Jk5dsU9xqIC0ctRBU8P6LbbJEVdzAfE0OYTJ7Ji6Weax06T0JD4PZOgIx8=", "stream_url": "http://cctvsec.ktict.co.kr/120/iyt5f0iWzZUAEom6Bu/3dOte5b02QQcoqrbPROBbsAiFh+nz0Jk5dsU9xqIC0ctRBU8P6LbbJEVdzAfE0OYTJ7Ji6Weax06T0JD4PZOgIx8="},
    {"name": "[경부선] 옥산휴게소", "cctv_url": "http://cctvsec.ktict.co.kr/121/3qLDgHP5JKiFW+5qGqsmODGy/yObDZgbR0RICpPs+6kUZ4WTh1GuYZFwG9rPnbm7QWrIhMCG7ilSLpdGyRdgKM2oz6ItQanIvn03eURPLU4=", "stream_url": "http://cctvsec.ktict.co.kr/121/3qLDgHP5JKiFW+5qGqsmODGy/yObDZgbR0RICpPs+6kUZ4WTh1GuYZFwG9rPnbm7QWrIhMCG7ilSLpdGyRdgKM2oz6ItQanIvn03eURPLU4="},
    {"name": "[경부선] 남청주육교", "cctv_url": "http://cctvsec.ktict.co.kr/310/S1n/NEg0kGqXoV9XcGjZy7o+QvVlz/X9/fCFd0Mj3hhygsWMPSOsNDRGCu9zO2Wnw939zIoRCLLfEB62cFmaEtkwF4FTLLRlk0o39iUH7/8=", "stream_url": "http://cctvsec.ktict.co.kr/310/S1n/NEg0kGqXoV9XcGjZy7o+QvVlz/X9/fCFd0Mj3hhygsWMPSOsNDRGCu9zO2Wnw939zIoRCLLfEB62cFmaEtkwF4FTLLRlk0o39iUH7/8="},
    {"name": "[경부선] 청주분기점(고정)", "cctv_url": "http://cctvsec.ktict.co.kr/311/3Q8ZOSfaL8LYN2pnttCv923Iz14D0m/HWz/zyY2HIzfUESa9xpWU/x+1IEBoZ4nhNcXateaKLMrUkxYwzmy60tybhIV5zs6FGi/zIYRwnss=", "stream_url": "http://cctvsec.ktict.co.kr/311/3Q8ZOSfaL8LYN2pnttCv923Iz14D0m/HWz/zyY2HIzfUESa9xpWU/x+1IEBoZ4nhNcXateaKLMrUkxYwzmy60tybhIV5zs6FGi/zIYRwnss="},
    {"name": "[경부선] 가마육교", "cctv_url": "http://cctvsec.ktict.co.kr/312/+hs6k7Ze+TQeBYmTvWYi63kyMEwkTIrvaRusq7usuwgk2CaJuBxUidV5BwbZdx0bUgBnwWz+0Z3Xc9rawyvNAjwc6QQkvF+IfpT4ZLbBvWU=", "stream_url": "http://cctvsec.ktict.co.kr/312/+hs6k7Ze+TQeBYmTvWYi63kyMEwkTIrvaRusq7usuwgk2CaJuBxUidV5BwbZdx0bUgBnwWz+0Z3Xc9rawyvNAjwc6QQkvF+IfpT4ZLbBvWU="},
    {"name": "[경부선] 금계", "cctv_url": "http://cctvsec.ktict.co.kr/313/2Ag3W45ctZGKlrS+4aI87WecsvsKubZiz45yCkrYmwWi2V3xyCdqfUaqWdQ32PRpgiQJ3Lfjlkr9kg5bHWZb1PrMzNwGx/Ie86j4jON3gg4=", "stream_url": "http://cctvsec.ktict.co.kr/313/2Ag3W45ctZGKlrS+4aI87WecsvsKubZiz45yCkrYmwWi2V3xyCdqfUaqWdQ32PRpgiQJ3Lfjlkr9kg5bHWZb1PrMzNwGx/Ie86j4jON3gg4="},
    {"name": "[청주영덕선] 문동1", "cctv_url": "http://cctvsec.ktict.co.kr/751/7HtK7txa+9qA20SPI4XnQYN8YJYCokuvn+ils5QpAyClxpSaHHL1W/nL4oZN3Q0yrj46LXkRww+xoiCz2Ke+0mT4iRu0Tib3NmR1Dd0mh70=", "stream_url": "http://cctvsec.ktict.co.kr/751/7HtK7txa+9qA20SPI4XnQYN8YJYCokuvn+ils5QpAyClxpSaHHL1W/nL4oZN3Q0yrj46LXkRww+xoiCz2Ke+0mT4iRu0Tib3NmR1Dd0mh70="},
    {"name": "[청주영덕선] 청주분기점", "cctv_url": "http://cctvsec.ktict.co.kr/2253/ZhJPe98qcMXjW2tx4Btv+sw0RWsYqT/i/y+TTNN8RjqAhGQqgaBC4+GW5pPzjt6LJvzFDOajS2ereDtgF8saaWcp29NhXYdK7/t7OHK0gYY=", "stream_url": "http://cctvsec.ktict.co.kr/2253/ZhJPe98qcMXjW2tx4Btv+sw0RWsYqT/i/y+TTNN8RjqAhGQqgaBC4+GW5pPzjt6LJvzFDOajS2ereDtgF8saaWcp29NhXYdK7/t7OHK0gYY="},
    {"name": "[청주영덕선] 문동2", "cctv_url": "http://cctvsec.ktict.co.kr/2254/ji9rFW37SW3CkXSswIC2jJdgi5HNuQ4Xld9NfBJMo6PwylbTHxKItvEaBnEbWfBJGCeS1ZWgWuLH7K6lbyIU88yM50RDpIi0I+E7z0Ggj/0=", "stream_url": "http://cctvsec.ktict.co.kr/2254/ji9rFW37SW3CkXSswIC2jJdgi5HNuQ4Xld9NfBJMo6PwylbTHxKItvEaBnEbWfBJGCeS1ZWgWuLH7K6lbyIU88yM50RDpIi0I+E7z0Ggj/0="},
    {"name": "[청주영덕선] 문의청남대휴게소2", "cctv_url": "http://cctvsec.ktict.co.kr/2255/np7OdQhpSvr7FHjnjiy9Du8FQKaywlJOKqO1DwUirnLPcUVRRtgjuxZtxPb2O8CgqTe1+7YpSInKw4APc2S6e1hr6DZLOhYtiC2cynXrnSs=", "stream_url": "http://cctvsec.ktict.co.kr/2255/np7OdQhpSvr7FHjnjiy9Du8FQKaywlJOKqO1DwUirnLPcUVRRtgjuxZtxPb2O8CgqTe1+7YpSInKw4APc2S6e1hr6DZLOhYtiC2cynXrnSs="},
    {"name": "[중부선] 증평2", "cctv_url": "http://cctvsec.ktict.co.kr/2303/kweiHRznXl/5NeH7upViqU/V/YqW3/SLsUrfl0KXVygBHQkxu/gEIBHaKA7Jr7MCBPXjr2WVMzIoZ9R0LgULyabDxY7PtW2XxaC2CL63C9k=", "stream_url": "http://cctvsec.ktict.co.kr/2303/kweiHRznXl/5NeH7upViqU/V/YqW3/SLsUrfl0KXVygBHQkxu/gEIBHaKA7Jr7MCBPXjr2WVMzIoZ9R0LgULyabDxY7PtW2XxaC2CL63C9k="},
    {"name": "[중부선] 오창", "cctv_url": "", "stream_url": ""},
    {"name": "[중부선] 서청주", "cctv_url": "http://cctvsec.ktict.co.kr/2305/lebRQVPP6UkAj3BBbkzFWIPLvOkdD4OYVcxMCKX4nkgHZgCH2l3ui6ckE31fA4VUqLtT3jcCJ4fyo0qAhHE8uaNTt6kUlBXwgy+zkxUmsos=", "stream_url": "http://cctvsec.ktict.co.kr/2305/lebRQVPP6UkAj3BBbkzFWIPLvOkdD4OYVcxMCKX4nkgHZgCH2l3ui6ckE31fA4VUqLtT3jcCJ4fyo0qAhHE8uaNTt6kUlBXwgy+zkxUmsos="},
    {"name": "[경부선] 남이분기점", "cctv_url": "http://cctvsec.ktict.co.kr/2306/0phM00zQh9LTB3jY8TvxBQ7iXDvoFburflc7JdDgdRz4M588biiDVHiilWFtiSB7a5FS9OAcZVXgTpibSNGxYabN00G8VBGtBstXZFZhLUE=", "stream_url": "http://cctvsec.ktict.co.kr/2306/0phM00zQh9LTB3jY8TvxBQ7iXDvoFburflc7JdDgdRz4M588biiDVHiilWFtiSB7a5FS9OAcZVXgTpibSNGxYabN00G8VBGtBstXZFZhLUE="},
    {"name": "[경부선] 속창육교", "cctv_url": "http://cctvsec.ktict.co.kr/2415/fbFA4wmrtgdAm/A+CjB79nGGjPKaDkligUuwfQE0BO3IIQmirgHCUxsktUYwGiwM5mjWXxI+X0YGja7NzoO7ixeoBu3Ds+hJoixsHuuh0LQ=", "stream_url": "http://cctvsec.ktict.co.kr/2415/fbFA4wmrtgdAm/A+CjB79nGGjPKaDkligUuwfQE0BO3IIQmirgHCUxsktUYwGiwM5mjWXxI+X0YGja7NzoO7ixeoBu3Ds+hJoixsHuuh0LQ="},
    {"name": "[경부선] 몽단이고개", "cctv_url": "http://cctvsec.ktict.co.kr/2424/WUYyNi4R6FVMVCoZ/dX+3XOBiqRjpvukIXvlP5yz1Yo2j9QJG3UFYPrgmuVRbZiwgtxscXmPJCHzLxgrUfbCD1umd35p7t7w0Pjmk+nvYbI=", "stream_url": "http://cctvsec.ktict.co.kr/2424/WUYyNi4R6FVMVCoZ/dX+3XOBiqRjpvukIXvlP5yz1Yo2j9QJG3UFYPrgmuVRbZiwgtxscXmPJCHzLxgrUfbCD1umd35p7t7w0Pjmk+nvYbI="},
    {"name": "[경부선] 수의", "cctv_url": "http://cctvsec.ktict.co.kr/2449/Tu5z2Vh3ZvLV31l9Go+HuaEFStd1HwbtQYW5x1l+tek74Dy+htYPq8M5UxTC3qDGMjXxBEzZ8Frk2aJ7/h60SzXt8qtMpNEe7Q8r5srNXoE=", "stream_url": "http://cctvsec.ktict.co.kr/2449/Tu5z2Vh3ZvLV31l9Go+HuaEFStd1HwbtQYW5x1l+tek74Dy+htYPq8M5UxTC3qDGMjXxBEzZ8Frk2aJ7/h60SzXt8qtMpNEe7Q8r5srNXoE="},
    {"name": "[경부선] 죽암교", "cctv_url": "http://cctvsec.ktict.co.kr/2451/Pc6qy7eLL4ABxLJn2bX1www8UoR6h0nAJtsquTi6TgRdJIzl43ZQMOlcWnyW9YrlW63bp8P1G7edj9ftLHXOcH+46shEliXtB2IlLn7hemk=", "stream_url": "http://cctvsec.ktict.co.kr/2451/Pc6qy7eLL4ABxLJn2bX1www8UoR6h0nAJtsquTi6TgRdJIzl43ZQMOlcWnyW9YrlW63bp8P1G7edj9ftLHXOcH+46shEliXtB2IlLn7hemk="},
    {"name": "[경부선] 옥산분기점", "cctv_url": "http://cctvsec.ktict.co.kr/2456/GfdjKwRUHCYwgLhu1h4tg2o9+m0r14bSk8qQuv+Grqj10fjiiPimQL6cf9lHebkdxpEJ9+Eodto36a1r1iuWiz1x9/qwMM7HKs13GJX3/YI=", "stream_url": "http://cctvsec.ktict.co.kr/2456/GfdjKwRUHCYwgLhu1h4tg2o9+m0r14bSk8qQuv+Grqj10fjiiPimQL6cf9lHebkdxpEJ9+Eodto36a1r1iuWiz1x9/qwMM7HKs13GJX3/YI="},
    {"name": "[경부선] 강서", "cctv_url": "http://cctvsec.ktict.co.kr/2460/Frjx7lMHEU/cTpAqhZTL8sAJSSYYuc2h1sQV2sJZwmTBW2LYbareFBOefUT2DURjKtkAAO8VF7hvs5hSn7AOTK5bTltZS3oOiVNVA0f7Q5w=", "stream_url": "http://cctvsec.ktict.co.kr/2460/Frjx7lMHEU/cTpAqhZTL8sAJSSYYuc2h1sQV2sJZwmTBW2LYbareFBOefUT2DURjKtkAAO8VF7hvs5hSn7AOTK5bTltZS3oOiVNVA0f7Q5w="},
]

cctv_records = []
cctv_records_source = "not_loaded"
cctv_records_error = ""
previous_direction_centers_by_stream = {}


def _json_field(value, default):
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return json.loads(value)
    return value


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_bbox(value):
    bbox = _json_field(value, [0, 0, 0, 0])
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return [0, 0, 0, 0]
    return [_safe_float(item) for item in bbox[:4]]


def _normalize_detection(item):
    detection = dict(item or {})
    detection["class_name"] = str(detection.get("class_name", detection.get("name", "none")))
    detection["confidence"] = _safe_float(detection.get("confidence"), 0.0)
    detection["bbox"] = _normalize_bbox(detection.get("bbox", [0, 0, 0, 0]))

    if detection.get("direction_label") is not None:
        detection["direction_label"] = _safe_int(detection.get("direction_label"), -1)
    if detection.get("track_id") is not None:
        detection["track_id"] = _safe_int(detection.get("track_id"), None)

    center = detection.get("center")
    if center is None:
        x1, y1, x2, y2 = detection["bbox"]
        center = [(x1 + x2) / 2.0, (y1 + y2) / 2.0]
    if not isinstance(center, (list, tuple)) or len(center) < 2:
        center = [0.0, 0.0]
    detection["center"] = [_safe_float(center[0]), _safe_float(center[1])] if len(center) >= 2 else [0.0, 0.0]
    return detection


def _normalize_rois(value):
    rois = _json_field(value, [])
    normalized = []
    for roi in rois or []:
        if isinstance(roi, dict):
            points = roi.get("points", [])
            label = roi.get("label", -1)
        elif isinstance(roi, (list, tuple)) and len(roi) >= 2:
            points, label = roi[0], roi[1]
        else:
            continue
        normalized.append(
            {
                "points": [[_safe_int(x), _safe_int(y)] for x, y in points],
                "label": _safe_int(label, -1),
            }
        )
    return normalized


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
    if not rois or frame_shape[0] <= 0 or frame_shape[1] <= 0:
        return 0.0

    roi_mask = _build_roi_mask(frame_shape, rois, label)
    roi_area = int(np.count_nonzero(roi_mask))
    if roi_area <= 0:
        return 0.0

    detection_mask = np.zeros_like(roi_mask)
    for detection in detections:
        if detection.get("direction_label") != int(label):
            continue
        x1, y1, x2, y2 = [_safe_int(value) for value in detection.get("bbox", [0, 0, 0, 0])]
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
    current_state = {"up": {}, "down": {}}
    congestion = {}

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


def _calculate_metrics(detection):
    if not detection:
        return {
            "traffic_count": 0,
            "traffic_up": 0,
            "traffic_down": 0,
            "accident_probability": 0,
            "accident_status": "-",
        }

    traffic_count = _safe_int(
        detection.get("traffic_count")
        or detection.get("detection_count")
        or len(detection.get("detections") or []),
        0,
    )
    if traffic_count <= 0:
        traffic_count = max(1, round(_safe_float(detection.get("confidence"), 0.0) * 10))

    traffic_up = _safe_int(detection.get("traffic_up"), -1)
    traffic_down = _safe_int(detection.get("traffic_down"), -1)
    if traffic_up < 0 or traffic_down < 0:
        detections = detection.get("detections") or []
        traffic_up = sum(1 for item in detections if item.get("direction_label") == UPBOUND_LABEL)
        traffic_down = sum(1 for item in detections if item.get("direction_label") == DOWNBOUND_LABEL)
    if traffic_up == 0 and traffic_down == 0 and traffic_count > 0:
        traffic_up = round(traffic_count * 0.55)
        traffic_down = max(0, traffic_count - traffic_up)

    accident_probability = _safe_int(detection.get("accident_probability"), -1)
    accident_status = detection.get("accident_status")
    if accident_probability < 0 or not accident_status:
        accident_probability, accident_status = _calculate_accident_probability(
            traffic_count,
            traffic_up,
            traffic_down,
            detection.get("congestion") or {},
        )

    return {
        "traffic_count": traffic_count,
        "traffic_up": traffic_up,
        "traffic_down": traffic_down,
        "accident_probability": accident_probability,
        "accident_status": accident_status,
    }


def _append_metric_history(metrics):
    traffic_up_history.append(metrics["traffic_up"])
    traffic_down_history.append(metrics["traffic_down"])
    accident_probability_history.append(metrics["accident_probability"])


def _get_cctv_items():
    _ensure_cctv_records()
    return [
        {
            "index": index,
            "name": item["name"],
            "selected": index == selected_index,
            "cctv_url": item.get("cctv_url", ""),
            "stream_url": item.get("stream_url", ""),
            "player_url": "",
        }
        for index, item in enumerate(cctv_records)
    ]


def _get_control_state():
    _ensure_cctv_records()
    selected_cctv = cctv_records[selected_index]
    return {
        "selected_index": selected_index,
        "selected_name": selected_cctv["name"],
        "cctv_url": selected_cctv.get("cctv_url", ""),
        "stream_url": selected_cctv.get("stream_url", ""),
        "selection_version": selection_version,
        "cctv_source": cctv_records_source,
        "cctv_error": cctv_records_error,
    }


def _get_status():
    _ensure_cctv_records()
    detection = latest_detection or {}
    metrics = _calculate_metrics(latest_detection)
    selected_cctv = cctv_records[selected_index]
    frame_url = _latest_frame_url()
    remote_selected_name = detection.get("selected_name")
    remote_selected_index = detection.get("selected_index")
    remote_stream_status = detection.get("stream_status")
    remote_roi_path = detection.get("roi_path")
    congestion = detection.get("congestion") or {}
    return {
        "selected_index": remote_selected_index if remote_selected_index is not None else selected_index,
        "selected_name": remote_selected_name or selected_cctv["name"],
        "traffic_count": metrics["traffic_count"],
        "traffic_up": metrics["traffic_up"],
        "traffic_down": metrics["traffic_down"],
        "traffic_up_history": list(traffic_up_history),
        "traffic_down_history": list(traffic_down_history),
        "accident_probability": metrics["accident_probability"],
        "accident_probability_history": list(accident_probability_history),
        "accident_status": metrics["accident_status"],
        "congestion_up": bool(congestion.get("up", {}).get("is_congested", False)),
        "congestion_down": bool(congestion.get("down", {}).get("is_congested", False)),
        "stream_status": remote_stream_status or ("연결됨" if latest_detection else "준비 중"),
        "player_url": _latest_frame_url() or "/video_feed",
        "cctv_url": detection.get("cctv_url") or selected_cctv.get("cctv_url", ""),
        "stream_url": detection.get("stream_url") or selected_cctv.get("stream_url", ""),
        "cctv_source": cctv_records_source,
        "cctv_error": cctv_records_error,
        "cctv_count": len(cctv_records),
        "control_selected_index": selected_index,
        "control_selected_name": selected_cctv["name"],
        "selection_version": selection_version,
        "yolo_enabled": latest_detection is not None,
        "roi_enabled": bool(detection.get("roi_enabled", False)),
        "roi_path": remote_roi_path or "Railway remote demo backend",
        "latest_detection": latest_detection,
        "frame_url": frame_url,
    }


def _get_hot_selected_name(detection):
    remote_selected_name = (detection or {}).get("selected_name")
    if remote_selected_name:
        return remote_selected_name

    remote_selected_index = (detection or {}).get("selected_index")
    try:
        index = int(remote_selected_index if remote_selected_index is not None else selected_index)
        records = cctv_records or STATIC_CCTV_RECORDS
        if 0 <= index < len(records):
            return records[index]["name"]
    except Exception:
        pass

    return "-"


def _get_viewer_message(include_image=True):
    # Keep the WebSocket hot path independent from slow external CCTV API fetches.
    detection = latest_detection or {}
    metrics = _calculate_metrics(detection)
    frame_url = _latest_frame_url()
    congestion = detection.get("congestion") or {}
    return {
        "type": "frame",
        "selected_index": detection.get("selected_index", selected_index),
        "selected_name": _get_hot_selected_name(detection),
        "traffic_count": metrics["traffic_count"],
        "traffic_up": metrics["traffic_up"],
        "traffic_down": metrics["traffic_down"],
        "traffic_up_history": list(traffic_up_history),
        "traffic_down_history": list(traffic_down_history),
        "accident_probability": metrics["accident_probability"],
        "accident_probability_history": list(accident_probability_history),
        "accident_status": metrics["accident_status"],
        "congestion_up": bool(congestion.get("up", {}).get("is_congested", False)),
        "congestion_down": bool(congestion.get("down", {}).get("is_congested", False)),
        "stream_status": detection.get("stream_status") or ("연결됨" if latest_detection else "준비 중"),
        "player_url": frame_url or "/video_feed",
        "cctv_url": detection.get("cctv_url", ""),
        "stream_url": detection.get("stream_url", ""),
        "cctv_source": cctv_records_source,
        "cctv_error": cctv_records_error,
        "cctv_count": len(cctv_records) or len(STATIC_CCTV_RECORDS),
        "control_selected_index": selected_index,
        "selection_version": selection_version,
        "yolo_enabled": latest_detection is not None,
        "roi_enabled": bool(detection.get("roi_enabled")),
        "roi_path": detection.get("roi_path") or "Railway remote demo backend",
        "latest_detection": latest_detection,
        "frame_url": frame_url,
        "image_mime": latest_frame_mime,
        "image_base64": latest_frame_base64 if include_image else "",
        "frame_sequence": latest_frame_sequence,
        "timestamp": detection.get("timestamp"),
    }


def _latest_frame_url():
    if latest_frame_bytes is None or latest_detection is None:
        return ""

    timestamp = quote(str(latest_detection.get("timestamp", "")), safe="")
    return f"/api/latest-frame?ts={timestamp}"


def _decode_base64_image(value):
    if not value:
        return None

    if "," in value and value.strip().startswith("data:"):
        value = value.split(",", 1)[1]

    return base64.b64decode(value)


def _strip_data_url(value):
    if value and "," in value and value.strip().startswith("data:"):
        return value.split(",", 1)[1]
    return value or ""


def _encode_base64_image(frame_bytes):
    if not frame_bytes:
        return ""
    return base64.b64encode(frame_bytes).decode("ascii")


def _parse_detection_payload():
    frame_bytes = None
    frame_mime = "image/jpeg"

    if request.is_json:
        data = request.get_json(silent=True)
        if data and data.get("image_base64"):
            frame_bytes = _decode_base64_image(data.get("image_base64"))
            frame_mime = data.get("image_mime", "image/jpeg")
        return data, frame_bytes, frame_mime

    data = request.form.to_dict()
    frame = request.files.get("frame")
    if frame:
        frame_bytes = frame.read()
        frame_mime = frame.mimetype or "image/jpeg"

    return data, frame_bytes, frame_mime


def _parse_bbox(value):
    return _normalize_bbox(value)


def _parse_detections(value):
    detections = _json_field(value, [])
    return [_normalize_detection(item) for item in detections or []]


def _truthy(value):
    return str(value).lower() in {"1", "true", "yes"}


def _infer_frame_size(frame_bytes):
    if not frame_bytes:
        return 0, 0
    try:
        image = cv2.imdecode(np.frombuffer(frame_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return 0, 0
        height, width = image.shape[:2]
        return int(width), int(height)
    except Exception:
        return 0, 0


def _fallback_congestion(traffic_up, traffic_down):
    return {
        "up": {
            "count": int(traffic_up),
            "roi_coverage_ratio": 0.0,
            "mean_center_movement": None,
            "is_congested": False,
        },
        "down": {
            "count": int(traffic_down),
            "roi_coverage_ratio": 0.0,
            "mean_center_movement": None,
            "is_congested": False,
        },
    }


def _update_latest_detection(data, frame_bytes=None, frame_mime="image/jpeg"):
    global latest_detection, latest_frame_bytes, latest_frame_mime, latest_frame_base64
    global latest_frame_sequence

    detections = _parse_detections(data.get("detections"))
    has_single_detection = all(field in data for field in ["class_name", "confidence", "bbox"])
    if not detections and not has_single_detection:
        raise ValueError("Send either detections or class_name/confidence/bbox")

    if not detections:
        detections = [
            {
                "class_name": data["class_name"],
                "confidence": _safe_float(data["confidence"]),
                "bbox": _parse_bbox(data["bbox"]),
            }
        ]
        detections = [_normalize_detection(item) for item in detections]

    best_detection = max(
        detections,
        key=lambda item: _safe_float(item.get("confidence"), 0.0),
        default={"class_name": "none", "confidence": 0.0, "bbox": [0, 0, 0, 0]},
    )
    rois = _normalize_rois(data.get("rois"))
    frame_width = _safe_int(data.get("frame_width"), 0)
    frame_height = _safe_int(data.get("frame_height"), 0)
    if (frame_width <= 0 or frame_height <= 0) and frame_bytes:
        frame_width, frame_height = _infer_frame_size(frame_bytes)

    selected_name = data.get("selected_name") or _get_hot_selected_name(data)
    traffic_count = _safe_int(data.get("traffic_count"), len(detections))
    traffic_up = _safe_int(data.get("traffic_up"), -1)
    traffic_down = _safe_int(data.get("traffic_down"), -1)
    if traffic_up < 0 or traffic_down < 0:
        traffic_up = sum(1 for item in detections if item.get("direction_label") == UPBOUND_LABEL)
        traffic_down = sum(1 for item in detections if item.get("direction_label") == DOWNBOUND_LABEL)
    if traffic_up == 0 and traffic_down == 0 and traffic_count > 0:
        traffic_up = round(traffic_count * 0.55)
        traffic_down = max(0, traffic_count - traffic_up)

    incoming_congestion = _json_field(data.get("congestion"), None)
    if incoming_congestion:
        congestion = incoming_congestion
    elif rois and frame_width > 0 and frame_height > 0:
        congestion = _compute_congestion(detections, rois, frame_width, frame_height, selected_name)
    else:
        congestion = _fallback_congestion(traffic_up, traffic_down)
    accident_probability, accident_status = _calculate_accident_probability(
        traffic_count,
        traffic_up,
        traffic_down,
        congestion,
    )
    timestamp = data.get("timestamp") or datetime.now(timezone.utc).isoformat()

    latest_detection = {
        "class_name": best_detection.get("class_name", "none"),
        "confidence": _safe_float(best_detection.get("confidence"), 0.0),
        "bbox": best_detection.get("bbox", [0, 0, 0, 0]),
        "detections": detections,
        "rois": rois,
        "detection_count": len(detections),
        "frame_id": _safe_int(data.get("frame_id"), latest_frame_sequence + 1),
        "frame_width": frame_width,
        "frame_height": frame_height,
        "traffic_count": traffic_count,
        "traffic_up": traffic_up,
        "traffic_down": traffic_down,
        "congestion": congestion,
        "accident_probability": accident_probability,
        "accident_status": accident_status,
        "selected_name": selected_name,
        "selected_index": data.get("selected_index"),
        "cctv_url": data.get("cctv_url", ""),
        "stream_url": data.get("stream_url", ""),
        "player_url": data.get("player_url", ""),
        "stream_status": data.get("stream_status"),
        "roi_enabled": _truthy(data.get("roi_enabled", "")) or bool(rois),
        "roi_path": data.get("roi_path"),
        "timestamp": timestamp,
    }

    image_base64 = _strip_data_url(data.get("image_base64"))

    if frame_bytes:
        latest_frame_bytes = frame_bytes
        latest_frame_mime = frame_mime or "image/jpeg"
        latest_frame_base64 = image_base64 or _encode_base64_image(frame_bytes)
    elif image_base64:
        latest_frame_base64 = image_base64
        latest_frame_mime = data.get("image_mime", "image/jpeg")
        latest_frame_bytes = _decode_base64_image(latest_frame_base64)

    latest_detection["frame_url"] = _latest_frame_url()
    latest_frame_sequence += 1
    _append_metric_history(_calculate_metrics(latest_detection))
    with frame_condition:
        frame_condition.notify_all()
    return latest_detection


def _broadcast_to_viewers(message):
    dead_sockets = []
    serialized = json.dumps(message, ensure_ascii=False)

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


def _fallback_cctv_records():
    return [dict(item) for item in STATIC_CCTV_RECORDS]


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
    ordered_items = []
    for name in CCTV_ITEMS:
        ordered_items.append(
            by_name.get(
                name,
                {
                    "name": name,
                    "cctv_url": "",
                    "stream_url": "",
                },
            )
        )

    if not any(item.get("cctv_url") for item in ordered_items):
        # Keep the UI usable even if names from the public API changed slightly.
        return fetched_items[: len(CCTV_ITEMS)]

    return ordered_items


def _ensure_cctv_records():
    global cctv_records, cctv_records_error, cctv_records_source

    if cctv_records:
        return

    try:
        cctv_records = _fetch_cctv_records()
        cctv_records_source = "its_api"
        cctv_records_error = ""
    except Exception as exc:
        cctv_records = _fallback_cctv_records()
        cctv_records_source = "fallback"
        cctv_records_error = f"{type(exc).__name__}: {exc}"


def _build_svg_frame():
    metrics = _calculate_metrics(latest_detection)
    _ensure_cctv_records()
    cctv_name = html.escape(cctv_records[selected_index]["name"])
    road_label = html.escape(f"CCTV {selected_index + 1:03d}")
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
    <linearGradient id="road" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0%" stop-color="#1f2c3d"/>
      <stop offset="100%" stop-color="#0b111a"/>
    </linearGradient>
  </defs>
  <rect width="960" height="540" fill="#121822"/>
  <rect width="960" height="540" fill="url(#grid)"/>
  <polygon points="190,540 405,130 555,130 770,540" fill="url(#road)" stroke="#2d3b52" stroke-width="3"/>
  <line x1="480" y1="150" x2="480" y2="520" stroke="#d7dee8" stroke-width="8" stroke-dasharray="34 28" opacity="0.72"/>
  <line x1="345" y1="178" x2="245" y2="540" stroke="#f1c84b" stroke-width="4" opacity="0.86"/>
  <line x1="615" y1="178" x2="715" y2="540" stroke="#f1c84b" stroke-width="4" opacity="0.86"/>
  <rect x="630" y="72" width="238" height="86" rx="14" fill="rgba(18,24,34,0.78)" stroke="rgba(94,110,138,0.8)"/>
  <text x="650" y="106" fill="#8ebeff" font-family="Arial, sans-serif" font-size="18" font-weight="700">{road_label}</text>
  <text x="650" y="134" fill="#eef3f8" font-family="Arial, sans-serif" font-size="18" font-weight="700">{cctv_name}</text>
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
                "/api/control",
                "/api/select/<index>",
                "/video_feed",
                "/ws/sender",
                "/ws/detection",
                "/ws/viewer",
            ],
        }
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/detection", methods=["POST"])
def receive_detection():
    data, frame_bytes, frame_mime = _parse_detection_payload()
    if not data:
        return jsonify({"status": "error", "message": "JSON body is required"}), 400

    try:
        with state_lock:
            detection = _update_latest_detection(data, frame_bytes, frame_mime)
            viewer_message = _get_viewer_message(include_image=False)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    _queue_viewer_broadcast(viewer_message)

    return jsonify({"status": "ok", "data": detection})


def _receive_sender_websocket(ws):
    while True:
        try:
            raw_message = ws.receive()
            if raw_message is None:
                break

            data = json.loads(raw_message)
            frame_bytes = None
            frame_mime = data.get("image_mime", "image/jpeg")
            if data.get("image_base64"):
                frame_bytes = _decode_base64_image(data.get("image_base64"))

            with state_lock:
                _update_latest_detection(data, frame_bytes, frame_mime)
                viewer_message = _get_viewer_message(include_image=False)

            _queue_viewer_broadcast(viewer_message)
        except json.JSONDecodeError:
            try:
                ws.send(json.dumps({"status": "error", "message": "Invalid JSON"}))
            except Exception:
                break
        except Exception as exc:
            try:
                ws.send(json.dumps({"status": "error", "message": str(exc)}))
            except Exception:
                break


@sock.route("/ws/sender")
def ws_sender(ws):
    _receive_sender_websocket(ws)


@sock.route("/ws/detection")
def ws_detection(ws):
    _receive_sender_websocket(ws)


@sock.route("/ws/viewer")
def ws_viewer(ws):
    with viewer_sockets_lock:
        viewer_sockets.add(ws)

    try:
        with state_lock:
            ws.send(json.dumps(_get_viewer_message(include_image=True), ensure_ascii=False))

        while True:
            try:
                message = ws.receive(timeout=30)
                if message is None:
                    break
            except TimeoutError:
                try:
                    ws.send(json.dumps({"type": "ping"}))
                except Exception:
                    break
            except Exception:
                break
    finally:
        with viewer_sockets_lock:
            viewer_sockets.discard(ws)


@app.route("/api/latest", methods=["GET"])
def get_latest_detection():
    if latest_detection:
        latest_detection["frame_url"] = _latest_frame_url()
    return jsonify({"data": latest_detection})


@app.route("/api/latest-frame", methods=["GET"])
def get_latest_frame():
    if latest_frame_bytes is None:
        return Response(_build_svg_frame(), mimetype="image/svg+xml")

    response = Response(latest_frame_bytes, mimetype=latest_frame_mime)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify(_get_status())


@app.route("/api/cctvs", methods=["GET"])
def api_cctvs():
    _ensure_cctv_records()
    return jsonify(
        {
            "items": _get_cctv_items(),
            "source": cctv_records_source,
            "error": cctv_records_error,
        }
    )


@app.route("/api/control", methods=["GET"])
def api_control():
    return jsonify(_get_control_state())


@app.route("/api/reload-cctvs", methods=["POST"])
def api_reload_cctvs():
    global cctv_records, cctv_records_error, cctv_records_source, selected_index, selection_version

    cctv_records = []
    cctv_records_source = "not_loaded"
    cctv_records_error = ""
    selected_index = 0
    selection_version += 1
    _ensure_cctv_records()
    return jsonify(
        {
            "ok": cctv_records_source == "its_api",
            "source": cctv_records_source,
            "error": cctv_records_error,
            "items": _get_cctv_items(),
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
    return jsonify({"ok": True, "status": _get_status()})


@app.route("/video_feed", methods=["GET"])
def video_feed():
    def stream_latest_frames():
        last_sequence = -1

        while True:
            with frame_condition:
                frame_condition.wait_for(
                    lambda: latest_frame_sequence > last_sequence,
                    timeout=10,
                )

            with state_lock:
                frame_bytes = latest_frame_bytes
                frame_mime = latest_frame_mime
                sequence = latest_frame_sequence

            if frame_bytes is None:
                continue

            last_sequence = sequence
            yield (
                b"--frame\r\n"
                + f"Content-Type: {frame_mime}\r\n".encode("ascii")
                + b"Cache-Control: no-store\r\n\r\n"
                + frame_bytes
                + b"\r\n"
            )

    response = Response(
        stream_latest_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


threading.Thread(target=_viewer_broadcast_worker, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

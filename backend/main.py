import html
import json
import os
import base64
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import quote, urlencode, urljoin
from urllib.request import urlopen

from flask import Flask, Response, jsonify, request
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

# This Railway demo keeps state in memory.
# If Railway restarts the service, these values are reset.
latest_detection = None
latest_frame_bytes = None
latest_frame_mime = "image/jpeg"
latest_frame_version = 0
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
    traffic_count = int(
        detection.get("traffic_count")
        or detection.get("detection_count")
        or max(1, round(confidence * 10))
    )
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


def _get_status():
    _ensure_cctv_records()
    metrics = _calculate_metrics(latest_detection)
    selected_cctv = cctv_records[selected_index]
    frame_url = _latest_frame_url()
    remote_selected_name = (latest_detection or {}).get("selected_name")
    remote_selected_index = (latest_detection or {}).get("selected_index")
    remote_stream_status = (latest_detection or {}).get("stream_status")
    remote_roi_path = (latest_detection or {}).get("roi_path")
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
        "stream_status": remote_stream_status or ("연결됨" if latest_detection else "준비 중"),
        "player_url": _latest_frame_url() or "/video_feed",
        "frame_stream_url": "/api/frame-stream",
        "cctv_url": selected_cctv.get("cctv_url", ""),
        "stream_url": selected_cctv.get("stream_url", ""),
        "cctv_source": cctv_records_source,
        "cctv_error": cctv_records_error,
        "cctv_count": len(cctv_records),
        "yolo_enabled": latest_detection is not None,
        "roi_enabled": False,
        "roi_path": remote_roi_path or "Railway remote demo backend",
        "latest_detection": latest_detection,
        "frame_url": frame_url,
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
    if isinstance(value, str):
        return json.loads(value)
    return value


def _parse_detections(value):
    if not value:
        return []
    if isinstance(value, str):
        return json.loads(value)
    return value


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
                "/api/select/<index>",
                "/api/frame-stream",
                "/video_feed",
            ],
        }
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/detection", methods=["POST"])
def receive_detection():
    global latest_detection, latest_frame_bytes, latest_frame_mime, latest_frame_version

    data, frame_bytes, frame_mime = _parse_detection_payload()
    if not data:
        return jsonify({"status": "error", "message": "JSON body is required"}), 400

    detections = _parse_detections(data.get("detections"))
    has_single_detection = all(field in data for field in ["class_name", "confidence", "bbox"])
    if not detections and not has_single_detection:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Send either detections or class_name/confidence/bbox",
                }
            ),
            400,
        )

    if not detections:
        detections = [
            {
                "class_name": data["class_name"],
                "confidence": float(data["confidence"]),
                "bbox": _parse_bbox(data["bbox"]),
            }
        ]

    best_detection = max(
        detections,
        key=lambda item: float(item.get("confidence", 0) or 0),
        default={"class_name": "none", "confidence": 0.0, "bbox": [0, 0, 0, 0]},
    )
    traffic_count = int(data.get("traffic_count") or len(detections))
    latest_detection = {
        "class_name": best_detection.get("class_name", "none"),
        "confidence": float(best_detection.get("confidence", 0) or 0),
        "bbox": best_detection.get("bbox", [0, 0, 0, 0]),
        "detections": detections,
        "detection_count": len(detections),
        "traffic_count": traffic_count,
        "selected_name": data.get("selected_name"),
        "selected_index": data.get("selected_index"),
        "stream_status": data.get("stream_status"),
        "roi_enabled": str(data.get("roi_enabled", "")).lower() in {"1", "true", "yes"},
        "roi_path": data.get("roi_path"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if frame_bytes:
        latest_frame_bytes = frame_bytes
        latest_frame_mime = frame_mime
    else:
        latest_frame_bytes = None
        latest_frame_mime = "image/jpeg"
    latest_frame_version += 1

    latest_detection["frame_url"] = _latest_frame_url()
    _append_metric_history(_calculate_metrics(latest_detection))

    return jsonify({"status": "ok", "data": latest_detection})


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


@app.route("/api/frame-stream", methods=["GET"])
def frame_stream():
    def generate():
        last_sent_version = -1

        while True:
            frame_bytes = latest_frame_bytes
            frame_mime = latest_frame_mime
            frame_version = latest_frame_version

            if frame_bytes is None:
                frame_bytes = _build_svg_frame().encode("utf-8")
                frame_mime = "image/svg+xml"

            if frame_version != last_sent_version:
                yield (
                    b"--frame\r\n"
                    + f"Content-Type: {frame_mime}\r\n".encode("utf-8")
                    + b"Cache-Control: no-store\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
                last_sent_version = frame_version

            time.sleep(0.05)

    response = Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Accel-Buffering"] = "no"
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


@app.route("/api/reload-cctvs", methods=["POST"])
def api_reload_cctvs():
    global cctv_records, cctv_records_error, cctv_records_source, selected_index

    cctv_records = []
    cctv_records_source = "not_loaded"
    cctv_records_error = ""
    selected_index = 0
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
    global selected_index

    _ensure_cctv_records()
    if index < 0 or index >= len(cctv_records):
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

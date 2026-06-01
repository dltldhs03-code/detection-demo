import json
import time
from urllib.parse import urljoin
from urllib.request import urlopen

import cv2
import pandas as pd
import requests

from utils.app_config import (
    API_URL,
    CCTV_INDEX,
    DIRECT_CCTV_NAME,
    DIRECT_CCTV_URL,
    FRAME_WAIT_INTERVAL_SECONDS,
    LIST_LIMIT,
    REQUEST_PARAMS,
    STREAM_CONNECT_RETRY_COUNT,
    STREAM_CONNECT_RETRY_DELAY_SECONDS,
    TARGET_NAME,
)


def fetch_cctv_dataframe():
    query = "&".join(f"{key}={value}" for key, value in REQUEST_PARAMS.items())
    url = f"{API_URL}?{query}"
    response = urlopen(url)
    payload = json.loads(response.read().decode("utf-8"))

    data = payload.get("response", {}).get("data", [])
    if not data:
        raise RuntimeError("CCTV 목록을 불러오지 못했습니다.")

    cctv_df = pd.json_normalize(data)
    if "cctvname" not in cctv_df.columns:
        raise RuntimeError("CCTV 목록 응답에 cctvname 컬럼이 없습니다.")

    return cctv_df.reset_index(drop=True)


def select_cctv(cctv_df, preferred_index=CCTV_INDEX, target_name=TARGET_NAME):
    print("조회된 CCTV 목록:")
    for index, row in cctv_df.head(LIST_LIMIT).iterrows():
        print(f"[{index}] {row['cctvname']}")

    if preferred_index is not None:
        if preferred_index < 0 or preferred_index >= len(cctv_df):
            raise RuntimeError(f"CCTV_INDEX 범위가 잘못되었습니다: {preferred_index}")

        row = cctv_df.iloc[preferred_index]
        return row["cctvname"], row["cctvurl"], int(preferred_index)

    matched = cctv_df[cctv_df["cctvname"].astype(str).str.contains(target_name, na=False)]
    if matched.empty:
        names = cctv_df["cctvname"].astype(str).dropna().tolist()
        sample_names = ", ".join(names[:10]) if names else "없음"
        raise RuntimeError(
            f"이름으로 CCTV를 찾지 못했습니다: {target_name}\n"
            f"현재 조회된 CCTV 예시: {sample_names}"
        )

    row = matched.iloc[0]
    return row["cctvname"], row["cctvurl"], int(row.name)


def resolve_stream_url(cctv_url):
    try:
        response = requests.get(cctv_url, allow_redirects=True, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"CCTV 스트림 URL 요청 실패: {exc}") from exc

    playlist_url = response.url
    playlist_text = response.text

    for line in playlist_text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return urljoin(playlist_url, line)

    return cctv_url


def open_capture(url):
    capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if capture.isOpened():
        return capture

    capture.release()
    capture = cv2.VideoCapture(url)
    if capture.isOpened():
        return capture

    capture.release()
    return None


def connect_capture(stream_url, cctv_url):
    capture = open_capture(stream_url)
    if capture is not None:
        return capture

    print("실제 스트림 URL 연결 실패, 원본 cctvurl로 다시 시도합니다.")
    return open_capture(cctv_url)


def connect_capture_with_retry(cctv_url, retry_count=STREAM_CONNECT_RETRY_COUNT):
    last_error = None

    for attempt in range(retry_count + 1):
        try:
            stream_url = resolve_stream_url(cctv_url)
            capture = connect_capture(stream_url, cctv_url)
            if capture is not None:
                return stream_url, capture
            last_error = RuntimeError("OpenCV에서 CCTV 스트림을 열지 못했습니다.")
        except RuntimeError as exc:
            last_error = exc

        if attempt < retry_count:
            time.sleep(STREAM_CONNECT_RETRY_DELAY_SECONDS)

    if last_error is None:
        last_error = RuntimeError("알 수 없는 CCTV 연결 오류")
    raise last_error


def read_frame_with_timeout(capture, timeout_seconds):
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        ok, frame = capture.read()
        if ok:
            return True, frame

        time.sleep(FRAME_WAIT_INTERVAL_SECONDS)

    return False, None

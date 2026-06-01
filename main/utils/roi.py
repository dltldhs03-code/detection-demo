import json
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np


Point = Tuple[int, int]
ROIData = Tuple[List[Point], int]
MAIN_DIR = Path(__file__).resolve().parent.parent


def build_roi_path(index: int, roi_dir: str = "roi") -> str:
    """CCTV 인덱스에 대응하는 ROI JSON 경로를 생성합니다."""
    roi_path = Path(roi_dir)
    if not roi_path.is_absolute():
        roi_path = MAIN_DIR / roi_path
    return str(roi_path / f"roi_data_{int(index)}.json")


def load_roi_data(save_path: str) -> List[ROIData]:
    """저장된 ROI JSON 파일을 읽어 다각형 목록으로 반환합니다."""
    save_file = Path(save_path)
    if not save_file.exists():
        return []

    with save_file.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    loaded_rois: List[ROIData] = []
    for item in payload:
        if not isinstance(item, list) or len(item) != 2:
            continue

        points_data, label = item
        if not isinstance(points_data, list):
            continue

        points: List[Point] = []
        for point in points_data:
            if not isinstance(point, list) or len(point) != 2:
                continue
            points.append((int(point[0]), int(point[1])))

        if len(points) >= 3:
            loaded_rois.append((points, int(label)))

    return loaded_rois


def point_in_rois(point: Point, rois: Iterable[ROIData], label: Optional[int] = None) -> bool:
    """주어진 점이 ROI 내부에 있는지 확인합니다."""
    x, y = point
    for points, roi_label in rois:
        if label is not None and roi_label != label:
            continue

        polygon = np.array(points, dtype=np.int32)
        if cv2.pointPolygonTest(polygon, (float(x), float(y)), False) >= 0:
            return True

    return False


class ROISelector:
    """프레임 위에서 다중 ROI를 정의하고 시각화하는 도우미 클래스."""

    def __init__(
        self,
        window_name: str = "frame",
        save_path: Optional[str] = None,
        default_label: int = 0,
    ) -> None:
        # ROI를 그릴 OpenCV 창 이름과 저장 경로를 초기화합니다.
        self.window_name = window_name
        self.save_path = save_path or self._default_save_path()
        self.current_label = default_label

        self.current_points: List[Point] = []
        self.rois: List[ROIData] = []

        self._latest_frame: Optional[np.ndarray] = None
        self._mouse_callback_registered = False

        self.label_colors = {
            0: (0, 255, 0),
            1: (0, 165, 255),
        }

        self.load()

    def mouse_callback(self, event: int, x: int, y: int, flags: int, param: object) -> None:
        """마우스 좌클릭으로 현재 다각형의 점을 추가합니다."""
        del flags, param

        if event == cv2.EVENT_LBUTTONDOWN:
            self.current_points.append((int(x), int(y)))

    def handle_key(self, key: int) -> None:
        """키 입력을 처리해 라벨 변경, ROI 확정, 초기화, 저장을 수행합니다."""
        if key < 0:
            return

        if key == ord("0"):
            self.current_label = 0
        elif key == ord("1"):
            self.current_label = 1
        elif key == ord("c"):
            self.current_points.clear()
        elif key == ord("n"):
            self._finalize_current_roi()
        elif key == ord("s"):
            self.save()

    def draw(self, frame: np.ndarray) -> np.ndarray:
        """현재 점과 확정된 ROI를 프레임 위에 시각화합니다."""
        output = frame.copy()
        overlay = output.copy()

        for points, label in self.rois:
            if len(points) < 3:
                continue

            polygon = np.array(points, dtype=np.int32)
            color = self.label_colors.get(label, (255, 255, 0))

            cv2.fillPoly(overlay, [polygon], color)
            cv2.polylines(output, [polygon], True, color, 2)

            center_x, center_y = self._compute_center(points)
            cv2.putText(
                output,
                f"Label {label}",
                (center_x, center_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        # 반투명 ROI 영역을 원본 위에 합성합니다.
        output = cv2.addWeighted(overlay, 0.3, output, 0.7, 0)

        if self.current_points:
            current_polygon = np.array(self.current_points, dtype=np.int32)
            color = self.label_colors.get(self.current_label, (255, 255, 0))

            for point in self.current_points:
                cv2.circle(output, point, 4, (0, 0, 255), -1)

            if len(self.current_points) >= 2:
                cv2.polylines(output, [current_polygon], False, color, 2)

        cv2.putText(
            output,
            f"Current Label: {self.current_label}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        return output

    def save(self) -> None:
        """확정된 ROI 목록을 JSON 파일 형식으로 저장합니다."""
        serializable_data = [
            [[[int(x), int(y)] for x, y in points], int(label)]
            for points, label in self.rois
        ]

        with open(self.save_path, "w", encoding="utf-8") as file:
            json.dump(serializable_data, file, ensure_ascii=False, indent=2)

        print(f"ROI data saved to {self.save_path}")

    def load(self) -> None:
        """저장된 ROI JSON 파일이 있으면 메모리로 불러옵니다."""
        self.rois = load_roi_data(self.save_path)
        print(f"Loaded {len(self.rois)} ROI(s) from {self.save_path}")

    def update(self, frame: np.ndarray) -> np.ndarray:
        """외부에서 전달된 프레임을 받아 ROI가 그려진 프레임을 반환합니다."""
        self._latest_frame = frame
        self._ensure_mouse_callback()
        return self.draw(frame)

    def _finalize_current_roi(self) -> None:
        """현재 점 목록을 하나의 ROI로 확정합니다."""
        if len(self.current_points) < 3:
            print("ROI를 확정하려면 최소 3개의 점이 필요합니다.")
            return

        roi_points = [(int(x), int(y)) for x, y in self.current_points]
        self.rois.append((roi_points, int(self.current_label)))
        self.current_points.clear()

    def _compute_center(self, points: Sequence[Point]) -> Point:
        """다각형 점들의 평균으로 중심 좌표를 계산합니다."""
        points_array = np.array(points, dtype=np.float32)
        center = np.mean(points_array, axis=0)
        return int(center[0]), int(center[1])

    def _ensure_mouse_callback(self) -> None:
        """OpenCV 창에 마우스 콜백을 연결합니다."""
        if self._mouse_callback_registered:
            return

        try:
            cv2.setMouseCallback(self.window_name, self.mouse_callback)
            self._mouse_callback_registered = True
        except cv2.error:
            # 창이 아직 생성되지 않았다면 다음 update 호출에서 다시 시도합니다.
            self._mouse_callback_registered = False

    def _default_save_path(self) -> str:
        """live_opencv.py의 CCTV_INDEX를 반영한 기본 저장 경로를 생성합니다."""
        try:
            from utils.app_config import CCTV_INDEX

            return build_roi_path(int(CCTV_INDEX))
        except (ImportError, TypeError, ValueError):
            return str(MAIN_DIR / "roi" / "roi_data.json")


def _open_live_capture():
    """live_opencv.py의 설정을 재사용해 ROI 설정용 스트림을 엽니다."""
    from live_opencv import (
        DIRECT_CCTV_NAME,
        DIRECT_CCTV_URL,
        FRAME_WAIT_TIMEOUT_SECONDS,
        fetch_cctv_dataframe,
        open_capture,
        read_frame_with_timeout,
        resolve_stream_url,
        select_cctv,
    )

    if DIRECT_CCTV_URL:
        cctv_name = DIRECT_CCTV_NAME or "직접 지정 CCTV"
        cctv_url = DIRECT_CCTV_URL
    else:
        cctv_df = fetch_cctv_dataframe()
        cctv_name, cctv_url = select_cctv(cctv_df)

    print("선택 CCTV:", cctv_name)
    print("cctvurl:", cctv_url)

    stream_url = resolve_stream_url(cctv_url)
    print("stream url:", stream_url)

    capture = open_capture(stream_url)
    if capture is None:
        print("실제 스트림 URL 연결 실패, 원본 cctvurl로 다시 시도합니다.")
        capture = open_capture(cctv_url)

    if capture is None:
        raise RuntimeError("OpenCV에서 CCTV 스트림을 열지 못했습니다.")

    return capture, FRAME_WAIT_TIMEOUT_SECONDS


def main() -> None:
    raise SystemExit("로컬 ROI 확인 실행은 사용하지 않습니다. 전체 시스템은 `python3 main.py --use-roi`를 사용해주세요.")


if __name__ == "__main__":
    main()

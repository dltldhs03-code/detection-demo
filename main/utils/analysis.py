import cv2
import numpy as np

from utils.app_config import (
    CONGESTION_CENTER_MOVEMENT_THRESHOLD,
    CONGESTION_OVERLAP_THRESHOLD,
    DOWNBOUND_LABEL,
    ROI_BBOX_OVERLAP_THRESHOLD,
    UPBOUND_LABEL,
)
from utils.roi import point_in_rois


def filter_result_by_rois(result, rois):
    boxes = result.boxes
    if boxes is None or len(boxes) == 0 or not rois:
        return []

    filtered = []
    xyxy_list = boxes.xyxy.int().cpu().tolist()
    cls_list = boxes.cls.int().cpu().tolist()
    conf_list = boxes.conf.cpu().tolist()
    id_list = (
        boxes.id.int().cpu().tolist()
        if getattr(boxes, "id", None) is not None
        else [None] * len(xyxy_list)
    )

    for xyxy, cls_id, conf, track_id in zip(xyxy_list, cls_list, conf_list, id_list):
        x1, y1, x2, y2 = xyxy
        center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
        overlap_ratio = get_bbox_roi_overlap_ratio((x1, y1, x2, y2), rois)
        direction_label = get_point_roi_label(center, rois)
        if overlap_ratio >= ROI_BBOX_OVERLAP_THRESHOLD and direction_label is not None:
            filtered.append(
                {
                    "xyxy": (x1, y1, x2, y2),
                    "cls_id": int(cls_id),
                    "conf": float(conf),
                    "center": center,
                    "track_id": int(track_id) if track_id is not None else None,
                    "roi_overlap_ratio": overlap_ratio,
                    "direction_label": direction_label,
                }
            )

    return filtered


def get_bbox_roi_overlap_ratio(xyxy, rois):
    """bbox 면적 중 ROI 내부에 포함되는 비율을 계산합니다."""
    x1, y1, x2, y2 = [int(value) for value in xyxy]
    width = max(0, x2 - x1)
    height = max(0, y2 - y1)
    if width <= 0 or height <= 0 or not rois:
        return 0.0

    bbox_area = width * height
    if bbox_area <= 0:
        return 0.0

    roi_mask = np.zeros((height, width), dtype=np.uint8)
    for points, _label in rois:
        shifted_points = np.array(
            [[int(px - x1), int(py - y1)] for px, py in points],
            dtype=np.int32,
        )
        cv2.fillPoly(roi_mask, [shifted_points], 1)

    overlap_pixels = int(np.count_nonzero(roi_mask))
    return min(1.0, overlap_pixels / float(bbox_area))


def get_point_roi_label(point, rois):
    for _points, label in rois:
        if point_in_rois(point, rois, label=label):
            return int(label)
    return None


def apply_roi_mask_to_frame(frame, rois):
    if frame is None or not rois:
        return frame

    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    for points, _label in rois:
        polygon = np.array(points, dtype=np.int32)
        cv2.fillPoly(mask, [polygon], 255)

    return cv2.bitwise_and(frame, frame, mask=mask)


def build_roi_mask(frame_shape, rois, label):
    height, width = frame_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)

    for points, roi_label in rois:
        if int(roi_label) != int(label):
            continue
        polygon = np.array(points, dtype=np.int32)
        cv2.fillPoly(mask, [polygon], 1)

    return mask


def calculate_roi_coverage_ratio(frame_shape, detections, rois, label):
    if not rois:
        return 0.0

    roi_mask = build_roi_mask(frame_shape, rois, label)
    roi_area = int(np.count_nonzero(roi_mask))
    if roi_area <= 0:
        return 0.0

    detection_mask = np.zeros_like(roi_mask)
    for detection in detections:
        if detection.get("direction_label") != int(label):
            continue

        x1, y1, x2, y2 = [int(value) for value in detection["bbox"]]
        x1 = max(0, min(x1, detection_mask.shape[1]))
        x2 = max(0, min(x2, detection_mask.shape[1]))
        y1 = max(0, min(y1, detection_mask.shape[0]))
        y2 = max(0, min(y2, detection_mask.shape[0]))
        if x2 <= x1 or y2 <= y1:
            continue
        detection_mask[y1:y2, x1:x2] = 1

    overlap_pixels = int(np.count_nonzero(cv2.bitwise_and(roi_mask, detection_mask)))
    return min(1.0, overlap_pixels / float(roi_area))


def calculate_mean_center_movement(current_detections, previous_centers):
    if not current_detections or not previous_centers:
        return None

    previous_by_track_id = {
        int(track_id): tuple(center)
        for track_id, center in (previous_centers or {}).items()
        if track_id is not None and center is not None
    }
    tracked_movements = []
    fallback_detections = []

    for detection in current_detections:
        track_id = detection.get("track_id")
        center = detection.get("center")
        if center is None:
            continue
        if track_id is None or int(track_id) not in previous_by_track_id:
            fallback_detections.append(detection)
            continue

        previous_center = previous_by_track_id[int(track_id)]
        tracked_movements.append(
            float(np.hypot(center[0] - previous_center[0], center[1] - previous_center[1]))
        )

    if tracked_movements:
        return float(sum(tracked_movements) / len(tracked_movements))

    unmatched_previous = list(previous_by_track_id.values())
    movements = []

    for detection in fallback_detections:
        center = detection.get("center")
        if center is None or not unmatched_previous:
            continue

        best_index = min(
            range(len(unmatched_previous)),
            key=lambda index: float(
                np.hypot(
                    center[0] - unmatched_previous[index][0],
                    center[1] - unmatched_previous[index][1],
                )
            ),
        )
        previous_center = unmatched_previous.pop(best_index)
        movement = float(np.hypot(center[0] - previous_center[0], center[1] - previous_center[1]))
        movements.append(movement)

    if not movements:
        return None

    return float(sum(movements) / len(movements))


def analyze_directional_congestion(frame_shape, detections, rois, previous_direction_centers):
    labels = {
        "up": UPBOUND_LABEL,
        "down": DOWNBOUND_LABEL,
    }
    analysis = {}
    current_direction_centers = {key: {} for key in labels}

    for direction_name, label in labels.items():
        direction_detections = [
            item
            for item in detections
            if item.get("direction_label") == int(label)
        ]
        current_centers = {
            int(item["track_id"]): tuple(item["center"])
            for item in direction_detections
            if item.get("center") and item.get("track_id") is not None
        }
        current_direction_centers[direction_name] = current_centers
        coverage_ratio = calculate_roi_coverage_ratio(frame_shape, direction_detections, rois, label)
        mean_center_movement = calculate_mean_center_movement(
            direction_detections,
            previous_direction_centers.get(direction_name, []),
        )
        is_congested = (
            coverage_ratio >= CONGESTION_OVERLAP_THRESHOLD
            and mean_center_movement is not None
            and mean_center_movement <= CONGESTION_CENTER_MOVEMENT_THRESHOLD
        )
        analysis[direction_name] = {
            "count": len(direction_detections),
            "roi_coverage_ratio": round(float(coverage_ratio), 4),
            "mean_center_movement": (
                round(float(mean_center_movement), 4)
                if mean_center_movement is not None
                else None
            ),
            "is_congested": bool(is_congested),
        }

    return analysis, current_direction_centers


def collect_detections(result, rois=None):
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return []

    roi_filtered_boxes = None
    if rois:
        roi_filtered_boxes = filter_result_by_rois(result, rois)

    if roi_filtered_boxes is not None:
        iterable_boxes = roi_filtered_boxes
    else:
        xyxy_list = boxes.xyxy.int().cpu().tolist()
        cls_list = boxes.cls.int().cpu().tolist()
        conf_list = boxes.conf.cpu().tolist()
        id_list = (
            boxes.id.int().cpu().tolist()
            if getattr(boxes, "id", None) is not None
            else [None] * len(xyxy_list)
        )
        iterable_boxes = [
            {
                "xyxy": tuple(xyxy),
                "cls_id": int(cls_id),
                "conf": float(conf),
                "track_id": int(track_id) if track_id is not None else None,
            }
            for xyxy, cls_id, conf, track_id in zip(xyxy_list, cls_list, conf_list, id_list)
        ]

    names = result.names or {}
    detections = []
    for item in iterable_boxes:
        cls_id = int(item["cls_id"])
        detection = {
            "class_name": str(names.get(cls_id, cls_id)),
            "class_id": cls_id,
            "confidence": round(float(item["conf"]), 4),
            "bbox": [int(value) for value in item["xyxy"]],
            "center": [int(value) for value in item.get("center", (0, 0))],
        }
        if item.get("track_id") is not None:
            detection["track_id"] = int(item["track_id"])
        if "roi_overlap_ratio" in item:
            detection["roi_overlap_ratio"] = round(float(item["roi_overlap_ratio"]), 4)
        if item.get("direction_label") is not None:
            detection["direction_label"] = int(item["direction_label"])
        detections.append(detection)

    return detections

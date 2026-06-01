import cv2

from utils.app_config import DOWNBOUND_LABEL, UPBOUND_LABEL


def draw_tracking_results(frame, detections, rois=None):
    annotated = frame.copy()

    for item in detections:
        x1, y1, x2, y2 = item["bbox"]
        direction_label = item.get("direction_label")
        if direction_label == UPBOUND_LABEL:
            color = (0, 255, 0)
        elif direction_label == DOWNBOUND_LABEL:
            color = (0, 165, 255)
        else:
            color = (0, 0, 255)

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 1)

    return annotated

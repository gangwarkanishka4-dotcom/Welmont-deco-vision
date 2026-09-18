"""Step 1b: grab a handful of live snapshots straight from the running RTSP
cameras (instead of recorded footage) for immediate labeling priority.

Same crop/feature schema as 1_collect_features.py so 2_label_tool.py and
3_train_model.py pick these rows up completely unchanged — this just uses a
short-lived RTSP connection per camera instead of an .mp4 file as the frame
source. Each camera connection is opened, a handful of frames are grabbed,
and it's closed immediately — this does not hold a standing connection
alongside the live pipeline's own worker connection.
"""
from __future__ import annotations

import csv
import math
import os
import time
from pathlib import Path

import cv2

POSE_MODEL_PATH = "yolov8n-pose.pt"
DETECTION_CONFIDENCE = 0.4
KEYPOINT_CONFIDENCE_MIN = 0.3

MIN_CROP_WIDTH = 40
MIN_CROP_HEIGHT = 80
FRAMES_PER_CAMERA = 5
FRAME_GAP_SECONDS = 0.5

KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER = 5, 6
KP_LEFT_EAR, KP_RIGHT_EAR = 3, 4
KP_LEFT_HIP, KP_RIGHT_HIP = 11, 12
KP_LEFT_KNEE, KP_RIGHT_KNEE = 13, 14
KP_LEFT_ANKLE, KP_RIGHT_ANKLE = 15, 16

FEATURE_COLUMNS = [
    "shoulder_width", "head_width", "head_width_source", "build_ratio",
    "leg_extended", "leg_to_upper_ratio", "box_height", "detector_confidence",
]

CAMERAS = [
    {"name": "BasementClass1", "port": 556},
    {"name": "BasementClass2", "port": 553},
    {"name": "BasementClass3", "port": 552},
    {"name": "BasementClass4", "port": 551},
    {"name": "BasementClass5", "port": 560},
    {"name": "BasementClass6", "port": 554},
    {"name": "BasementClass7", "port": 565},
    {"name": "BasementClass8", "port": 561},
    {"name": "BasementClass9", "port": 564},
]
# Real camera credentials — never hardcoded, matches scripts/seed_welmont.py's
# convention. Set these in the root .env (already gitignored) before running.
RTSP_HOST = os.environ.get("WELMONT_RTSP_HOST", "")
RTSP_USERNAME = os.environ.get("WELMONT_RTSP_USERNAME", "")
RTSP_PASSWORD = os.environ.get("WELMONT_RTSP_PASSWORD", "")
RTSP_PATH = os.environ.get("WELMONT_RTSP_PATH", "/Streaming/Channels/101")


def _rtsp_url(port: int) -> str:
    from urllib.parse import quote

    return f"rtsp://{RTSP_USERNAME}:{quote(RTSP_PASSWORD, safe='')}@{RTSP_HOST}:{port}{RTSP_PATH}"


def _kp(keypoints_xy, keypoints_conf, index: int) -> tuple[float, float] | None:
    if keypoints_conf[index] < KEYPOINT_CONFIDENCE_MIN:
        return None
    return float(keypoints_xy[index][0]), float(keypoints_xy[index][1])


def _midpoint(a, b):
    if a and b:
        return (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    return a or b


def _dist(a, b) -> float:
    if not a or not b:
        return 0.0
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _leg_is_extended(hip, knee, ankle) -> bool:
    if knee is None:
        return True
    direct = _dist(hip, ankle)
    via_knee = _dist(hip, knee) + _dist(knee, ankle)
    if via_knee <= 1e-3:
        return True
    return (direct / via_knee) > 0.9


def extract_features(box_xyxy, box_conf, keypoints_xy, keypoints_conf) -> dict:
    x1, y1, x2, y2 = box_xyxy
    box_height = float(y2 - y1)

    left_shoulder = _kp(keypoints_xy, keypoints_conf, KP_LEFT_SHOULDER)
    right_shoulder = _kp(keypoints_xy, keypoints_conf, KP_RIGHT_SHOULDER)
    shoulder = _midpoint(left_shoulder, right_shoulder)
    shoulder_width = _dist(left_shoulder, right_shoulder)

    left_ear = _kp(keypoints_xy, keypoints_conf, KP_LEFT_EAR)
    right_ear = _kp(keypoints_xy, keypoints_conf, KP_RIGHT_EAR)
    if left_ear and right_ear:
        head_width = _dist(left_ear, right_ear)
        head_width_source = "ears"
    else:
        head_width = max(0.0, shoulder[1] - y1) if shoulder else 0.0
        head_width_source = "box_top"

    build_ratio = (shoulder_width / head_width) if (shoulder_width > 1e-3 and head_width > 1e-3) else None

    hip = _midpoint(_kp(keypoints_xy, keypoints_conf, KP_LEFT_HIP), _kp(keypoints_xy, keypoints_conf, KP_RIGHT_HIP))
    knee = _midpoint(_kp(keypoints_xy, keypoints_conf, KP_LEFT_KNEE), _kp(keypoints_xy, keypoints_conf, KP_RIGHT_KNEE))
    ankle = _midpoint(_kp(keypoints_xy, keypoints_conf, KP_LEFT_ANKLE), _kp(keypoints_xy, keypoints_conf, KP_RIGHT_ANKLE))

    leg_extended = None
    leg_to_upper_ratio = None
    if hip and ankle:
        leg_extended = _leg_is_extended(hip, knee, ankle)
        if leg_extended and shoulder:
            head_len = max(0.0, shoulder[1] - y1)
            torso_len = _dist(shoulder, hip)
            leg_len = _dist(hip, ankle)
            upper_body = torso_len + head_len
            if upper_body > 1e-3:
                leg_to_upper_ratio = leg_len / upper_body

    return {
        "shoulder_width": round(shoulder_width, 2),
        "head_width": round(head_width, 2),
        "head_width_source": head_width_source,
        "build_ratio": round(build_ratio, 3) if build_ratio is not None else "",
        "leg_extended": leg_extended if leg_extended is not None else "",
        "leg_to_upper_ratio": round(leg_to_upper_ratio, 3) if leg_to_upper_ratio is not None else "",
        "box_height": round(box_height, 1),
        "detector_confidence": round(float(box_conf), 3),
    }


def _save_crop(frame, box_xyxy, out_path: Path) -> bool:
    x1, y1, x2, y2 = (max(0, int(v)) for v in box_xyxy)
    crop = frame[y1:y2, x1:x2]
    if crop.shape[0] < MIN_CROP_HEIGHT or crop.shape[1] < MIN_CROP_WIDTH:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), crop)
    return True


def process_camera(model, name: str, port: int, rows: list[dict], crops_dir: Path) -> int:
    url = _rtsp_url(port)
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        print(f"  {name}: could not open stream")
        cap.release()
        return 0

    collected = 0
    ts = int(time.time())
    for frame_num in range(FRAMES_PER_CAMERA):
        ok, frame = cap.read()
        if not ok:
            break

        results = model.predict(frame, conf=DETECTION_CONFIDENCE, verbose=False)
        if results and results[0].keypoints is not None and results[0].boxes is not None:
            boxes = results[0].boxes.xyxy.tolist()
            confs = results[0].boxes.conf.tolist()
            all_kps = results[0].keypoints.data.tolist()

            for i, box in enumerate(boxes):
                kps = all_kps[i]
                kp_xy = [(p[0], p[1]) for p in kps]
                kp_conf = [p[2] for p in kps]

                crop_path = crops_dir / f"LIVE-{name}-{ts}_f{frame_num}_{i}.jpg"
                if not _save_crop(frame, box, crop_path):
                    continue

                features = extract_features(box, confs[i], kp_xy, kp_conf)
                rows.append({"crop_path": str(crop_path), **features, "label": ""})
                collected += 1

        time.sleep(FRAME_GAP_SECONDS)

    cap.release()
    return collected


def main() -> None:
    from ultralytics import YOLO

    out_dir = Path("data")
    crops_dir = out_dir / "crops"
    features_csv = out_dir / "features.csv"

    print(f"Loading pose model {POSE_MODEL_PATH} ...")
    model = YOLO(POSE_MODEL_PATH)

    rows: list[dict] = []
    started = time.time()
    for cam in CAMERAS:
        n = process_camera(model, cam["name"], cam["port"], rows, crops_dir)
        print(f"  {cam['name']} (port {cam['port']}): {n} crop(s)")
    elapsed = time.time() - started

    file_exists = features_csv.exists()
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(features_csv, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["crop_path", *FEATURE_COLUMNS, "label"])
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone in {elapsed:.1f}s. {len(rows)} row(s) added to {features_csv}")
    print(f"Crops saved to {crops_dir}/")
    print(f"Next: python 2_label_tool.py --dir {out_dir}")


if __name__ == "__main__":
    main()

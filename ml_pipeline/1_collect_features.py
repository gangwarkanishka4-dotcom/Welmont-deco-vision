"""Step 1: collect adult/child feature vectors + crop images from real
classroom footage, for a lightweight scikit-learn classifier (not a CNN —
see README.md in this folder for why).

Fully self-contained: only needs ultralytics/opencv/pandas installed and a
single YOLO-Pose model (auto-downloaded by ultralytics on first run if not
already present locally) — no dependency on the rest of this repo's backend
package, so this whole folder can be copied to another machine as-is.

Uses a single YOLO-Pose model for BOTH person detection and keypoints in one
pass (that's what a pose model already gives you), rather than running a
separate detector.

Features extracted per detected person (matching the exact definitions
validated against this deployment's real footage in the main backend's
heuristic classifier — train/serve parity matters, these must stay in sync
with 3_train_model.py's expected column order and integration_snippet.py's
inference-time feature computation):

  shoulder_width       — distance between left/right shoulder keypoints
  head_width           — ear-to-ear distance (works even facing away from
                          the camera, unlike nose/eyes); falls back to the
                          detection box's own top-edge-to-shoulder-line
                          distance when ears aren't confidently visible
  head_width_source    — "ears" or "box_top", so 3_train_model.py can see
                          whether this row's head_width is the more
                          reliable ear-based measurement
  build_ratio          — shoulder_width / head_width. A 3-3.5y toddler's
                          head is nearly as wide as their shoulders; an
                          adult's shoulders are far broader than their head
  leg_extended         — whether the knee reads as straight (standing)
                          rather than bent (sitting/crouching) — a bent
                          knee foreshortens hip-to-ankle distance and says
                          nothing real about leg length
  leg_to_upper_ratio   — hip-to-ankle / (shoulder-to-hip + head_len), only
                          meaningful when leg_extended is True
  box_height           — the detection's own pixel height (px)
  detector_confidence  — the detector's own confidence for this box

Run against each clip you have, one at a time, all pointed at the same
--out directory — features.csv accumulates across runs instead of being
overwritten, so:

    python 1_collect_features.py --source story_time.mp4 --out data/
    python 1_collect_features.py --source desk_work.mp4 --out data/

both add their rows to the same data/features.csv.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import cv2

# ============================================================================
# CONFIG (tuning knobs that rarely need to change run-to-run; --source/--out
# are CLI arguments instead, since those change every run)
# ============================================================================

POSE_MODEL_PATH = "yolov8n-pose.pt"  # auto-downloaded by ultralytics if not found locally
DETECTION_CONFIDENCE = 0.4
KEYPOINT_CONFIDENCE_MIN = 0.3

MIN_CROP_WIDTH = 40
MIN_CROP_HEIGHT = 80
SAMPLE_INTERVAL_SECONDS = 1.0  # don't extract a near-duplicate crop every single frame

# COCO-17 keypoint indices (Ultralytics' order).
KP_NOSE = 0
KP_LEFT_EYE, KP_RIGHT_EYE = 1, 2
KP_LEFT_EAR, KP_RIGHT_EAR = 3, 4
KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER = 5, 6
KP_LEFT_HIP, KP_RIGHT_HIP = 11, 12
KP_LEFT_KNEE, KP_RIGHT_KNEE = 13, 14
KP_LEFT_ANKLE, KP_RIGHT_ANKLE = 15, 16

FEATURE_COLUMNS = [
    "shoulder_width", "head_width", "head_width_source", "build_ratio",
    "leg_extended", "leg_to_upper_ratio", "box_height", "detector_confidence",
]

# ============================================================================
# Geometry helpers (kept dependency-free — no imports from the main backend)
# ============================================================================


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
    """True if the leg reads as roughly straight (standing) rather than bent
    (sitting cross-legged, crouching, kneeling). Without a confident knee
    keypoint there's no way to check, so this gives the benefit of the doubt
    rather than discarding the leg ratio outright."""
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


def process_video(model, path: Path, rows: list[dict], crops_dir: Path) -> int:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print(f"  could not open {path.name}")
        return 0

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_interval = max(1, round(fps * SAMPLE_INTERVAL_SECONDS))

    collected = 0
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % frame_interval == 0:
            results = model.predict(frame, conf=DETECTION_CONFIDENCE, verbose=False)
            if results and results[0].keypoints is not None and results[0].boxes is not None:
                boxes = results[0].boxes.xyxy.tolist()
                confs = results[0].boxes.conf.tolist()
                all_kps = results[0].keypoints.data.tolist()  # [N, 17, 3]

                for i, box in enumerate(boxes):
                    kps = all_kps[i]
                    kp_xy = [(p[0], p[1]) for p in kps]
                    kp_conf = [p[2] for p in kps]

                    crop_path = crops_dir / f"{path.stem}_f{frame_idx}_{i}.jpg"
                    if not _save_crop(frame, box, crop_path):
                        continue

                    features = extract_features(box, confs[i], kp_xy, kp_conf)
                    rows.append({"crop_path": str(crop_path), **features, "label": ""})
                    collected += 1
        frame_idx += 1

    cap.release()
    return collected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect adult/child feature vectors + crops from footage.")
    parser.add_argument(
        "--source", required=True,
        help="A single video file, or a directory of .mp4 files to process all of them.",
    )
    parser.add_argument(
        "--out", default="data",
        help="Output directory (default: data/). Crops go to <out>/crops/, features to <out>/features.csv. "
        "Run this script again with the same --out against a different --source to keep adding to the same dataset.",
    )
    return parser.parse_args()


def main() -> None:
    from ultralytics import YOLO

    args = parse_args()
    out_dir = Path(args.out)
    crops_dir = out_dir / "crops"
    features_csv = out_dir / "features.csv"

    source_path = Path(args.source)
    if source_path.is_dir():
        videos = sorted(source_path.glob("*.mp4"))
    elif source_path.is_file():
        videos = [source_path]
    else:
        print(f"--source does not exist: {source_path.resolve()}")
        return

    if not videos:
        print(f"No .mp4 files found at {source_path.resolve()}")
        return

    print(f"Loading pose model {POSE_MODEL_PATH} ...")
    model = YOLO(POSE_MODEL_PATH)

    print(f"Processing {len(videos)} video(s)...")
    rows: list[dict] = []
    import time

    started = time.time()
    for video in videos:
        n = process_video(model, video, rows, crops_dir)
        print(f"  {video.name}: {n} crop(s)")
    elapsed = time.time() - started

    # Append to an existing features.csv rather than overwrite it, so running
    # this against several clips (story-time, desk work, ...) builds up one
    # combined dataset instead of each run clobbering the last.
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

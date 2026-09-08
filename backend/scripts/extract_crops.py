"""Extracts person crops from real recorded footage (storage/clips/*.mp4 and
storage/snapshots/*.jpg) for building a labeled adult/child training set.

This is step 1 of training a real MLAgeClassifier model (see README
"Training a custom adult/child model") — the heuristic classifier has been
tuned repeatedly against this camera's specific lens/mounting and still
misses real adults in some conditions; a model trained on this exact
camera's own footage should generalize far better than more heuristic
tuning can.

Sampling is deliberately sparse within a clip (one frame every
SAMPLE_INTERVAL_SECONDS) — a person standing still for 10 seconds shouldn't
produce 250 near-identical crops that all need labeling for no added value.

Run from backend/:
    python -m scripts.extract_crops

Output: training_data/unlabeled/<source>_<frame>_<detection>.jpg
Then:   python -m scripts.label_crops   (see that script)
"""
from __future__ import annotations

from pathlib import Path

import cv2

from app.config import Settings
from app.cv.detector.yolo_detector import YOLODetector

MIN_CROP_WIDTH = 40
MIN_CROP_HEIGHT = 80
SAMPLE_INTERVAL_SECONDS = 1.0
CLIPS_DIR = Path("../storage/clips")
SNAPSHOTS_DIR = Path("../storage/snapshots")
OUTPUT_DIR = Path("../training_data/unlabeled")


def _save_crop(frame, box: tuple[float, float, float, float], out_path: Path) -> bool:
    x1, y1, x2, y2 = (max(0, int(v)) for v in box)
    crop = frame[y1:y2, x1:x2]
    if crop.shape[0] < MIN_CROP_HEIGHT or crop.shape[1] < MIN_CROP_WIDTH:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), crop)
    return True


def process_snapshot(detector: YOLODetector, path: Path) -> int:
    frame = cv2.imread(str(path))
    if frame is None:
        return 0
    detections = detector.detect(frame)
    saved = 0
    for i, det in enumerate(detections):
        out_path = OUTPUT_DIR / f"{path.stem}_snap_{i}.jpg"
        if _save_crop(frame, det.as_xyxy(), out_path):
            saved += 1
    return saved


def process_clip(detector: YOLODetector, path: Path) -> int:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        print(f"  could not open {path.name}")
        return 0

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_interval = max(1, round(fps * SAMPLE_INTERVAL_SECONDS))

    saved = 0
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % frame_interval == 0:
            detections = detector.detect(frame)
            for i, det in enumerate(detections):
                out_path = OUTPUT_DIR / f"{path.stem}_f{frame_idx}_{i}.jpg"
                if _save_crop(frame, det.as_xyxy(), out_path):
                    saved += 1
        frame_idx += 1

    cap.release()
    return saved


def main() -> None:
    settings = Settings()
    detector = YOLODetector(
        model_path=settings.person_model,
        device=settings.device,
        conf_threshold=settings.detector_conf_threshold,
        iou_threshold=settings.detector_iou_threshold,
        class_ids=settings.detector_class_ids,
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total = 0
    clips = sorted(CLIPS_DIR.glob("*.mp4"))
    print(f"Processing {len(clips)} clip(s) from {CLIPS_DIR}...")
    for path in clips:
        saved = process_clip(detector, path)
        total += saved
        print(f"  {path.name}: {saved} crop(s)")

    snapshots = sorted(SNAPSHOTS_DIR.glob("*.jpg"))
    print(f"Processing {len(snapshots)} snapshot(s) from {SNAPSHOTS_DIR}...")
    for path in snapshots:
        saved = process_snapshot(detector, path)
        total += saved

    print(f"\nDone. {total} crop(s) written to {OUTPUT_DIR}")
    print("Next: python -m scripts.label_crops")


if __name__ == "__main__":
    main()

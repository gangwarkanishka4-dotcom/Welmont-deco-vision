"""Visually test the appearance-based model (data/adult_child_appearance_model.onnx,
from 4_train_appearance_model.py) against a video — same idea as
test_model.py, but for the image classifier instead of the pose-feature
one. No pose keypoints needed at all here: just the detection box crop,
resized and fed straight to the CNN.

Same tracking + temporal-smoothing + sticky-commit behavior as
test_model.py, so the two are a fair side-by-side comparison — run both on
the same clip and compare the two output videos directly.

Run:
    python test_appearance_model.py --source some_clip.mp4 --dir data/
"""
from __future__ import annotations

import argparse
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

IMG_SIZE = 160  # must match 4_train_appearance_model.py's IMG_SIZE
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

DETECTION_CONFIDENCE = 0.4

# Same temporal-smoothing constants as test_model.py / the main backend's
# RollingClassificationHistory, for a fair comparison.
CLASSIFICATION_WINDOW = 15
ADULT_CONFIDENCE_THRESHOLD = 0.75
CHILD_CONFIDENCE_THRESHOLD = 0.75
IOU_MATCH_THRESHOLD = 0.3
MAX_MISSED_FRAMES = 10


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class Track:
    def __init__(self, track_id: int, box) -> None:
        self.id = track_id
        self.box = box
        self.history: deque[float] = deque(maxlen=CLASSIFICATION_WINDOW)
        self.committed_label: str | None = None
        self.missed = 0

    def update(self, box, adult_probability: float) -> None:
        self.box = box
        self.missed = 0
        self.history.append(adult_probability)
        smoothed = sum(self.history) / len(self.history)
        if smoothed >= ADULT_CONFIDENCE_THRESHOLD:
            self.committed_label = "adult"
        elif (1.0 - smoothed) >= CHILD_CONFIDENCE_THRESHOLD:
            self.committed_label = "child"


def _match_tracks(tracks: list[Track], boxes: list) -> tuple[dict[int, int], list[int]]:
    pairs = []
    for ti, track in enumerate(tracks):
        for di, box in enumerate(boxes):
            score = _iou(track.box, box)
            if score >= IOU_MATCH_THRESHOLD:
                pairs.append((score, ti, di))
    pairs.sort(reverse=True)

    matched_tracks: set[int] = set()
    matched_detections: dict[int, int] = {}
    for _score, ti, di in pairs:
        if ti in matched_tracks or di in matched_detections:
            continue
        matched_tracks.add(ti)
        matched_detections[di] = ti

    unmatched = [di for di in range(len(boxes)) if di not in matched_detections]
    return matched_detections, unmatched


def preprocess(crop: np.ndarray) -> np.ndarray:
    resized = cv2.resize(crop, (IMG_SIZE, IMG_SIZE))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    normalized = (rgb - IMAGENET_MEAN) / IMAGENET_STD
    return normalized.transpose(2, 0, 1)[None, ...].astype(np.float32)  # NCHW


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the appearance model against a video and save annotated output.")
    parser.add_argument("--source", required=True, help="Video file to test against.")
    parser.add_argument("--dir", default="data", help="Dataset directory containing the appearance model.")
    parser.add_argument("--out", default=None, help="Output video path (default: <dir>/test_appearance_output_<source>.mp4)")
    return parser.parse_args()


def main() -> None:
    from ultralytics import YOLO

    args = parse_args()
    data_dir = Path(args.dir)
    model_path = data_dir / "adult_child_appearance_model.onnx"
    source_path = Path(args.source)
    out_path = Path(args.out) if args.out else data_dir / f"test_appearance_output_{source_path.stem}.mp4"

    if not model_path.exists():
        print(f"{model_path} not found — run 4_train_appearance_model.py first.")
        return
    if not source_path.exists():
        print(f"--source does not exist: {source_path.resolve()}")
        return

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    # A pose model still gives us person boxes for free (ignore the keypoints) —
    # reuses the weights already downloaded by the other scripts, no separate
    # detector model needed since this classifier doesn't touch pose at all.
    pose_model_path = "yolov8n-pose.pt" if Path("yolov8n-pose.pt").exists() else "../models/yolov8n-pose.pt"
    print(f"Loading detector {pose_model_path} ...")
    detector = YOLO(pose_model_path)

    cap = cv2.VideoCapture(str(source_path))
    if not cap.isOpened():
        print(f"Could not open {source_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))

    tracks: list[Track] = []
    next_track_id = 0
    frame_idx = 0
    started = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        boxes: list = []
        probabilities: list[float] = []
        results = detector.predict(frame, conf=DETECTION_CONFIDENCE, verbose=False)
        if results and results[0].boxes is not None:
            raw_boxes = results[0].boxes.xyxy.tolist()
            for box in raw_boxes:
                x1, y1, x2, y2 = (int(v) for v in box)
                crop = frame[max(0, y1):y2, max(0, x1):x2]
                if crop.size == 0:
                    continue
                tensor = preprocess(crop)
                output = session.run(None, {input_name: tensor})[0]
                adult_probability = float(output.reshape(-1)[1])
                boxes.append(box)
                probabilities.append(adult_probability)

        matched, unmatched = _match_tracks(tracks, boxes)
        for di, ti in matched.items():
            tracks[ti].update(boxes[di], probabilities[di])
        for di in unmatched:
            new_track = Track(next_track_id, boxes[di])
            next_track_id += 1
            new_track.update(boxes[di], probabilities[di])
            tracks.append(new_track)

        matched_track_indices = set(matched.values())
        still_alive: list[Track] = []
        for ti, track in enumerate(tracks):
            if ti not in matched_track_indices:
                track.missed += 1
            if track.missed <= MAX_MISSED_FRAMES:
                still_alive.append(track)
        tracks = still_alive

        for track in tracks:
            if track.missed > 0:
                continue
            x1, y1, x2, y2 = (int(v) for v in track.box)
            if track.committed_label == "adult":
                color, text = (0, 140, 255), "ADULT"
            elif track.committed_label == "child":
                color, text = (0, 200, 0), "CHILD"
            else:
                color, text = (160, 160, 160), "..."
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"#{track.id} {text}", (x1, max(0, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        writer.write(frame)
        frame_idx += 1

    cap.release()
    writer.release()
    elapsed = time.time() - started

    ever_seen = next_track_id
    committed_adult = sum(1 for t in tracks if t.committed_label == "adult")
    committed_child = sum(1 for t in tracks if t.committed_label == "child")
    print(f"\nProcessed {frame_idx} frame(s) in {elapsed:.1f}s. {ever_seen} distinct track(s) seen.")
    print(f"Still active at end of clip: adult={committed_adult} child={committed_child} "
          f"undecided={len(tracks) - committed_adult - committed_child}")
    print(f"\nAnnotated video saved to {out_path}")
    print("Orange box = committed ADULT, green box = committed CHILD, gray '...' = still deciding.")
    print("Same clip through test_model.py (geometry model) makes a direct side-by-side comparison.")


if __name__ == "__main__":
    main()

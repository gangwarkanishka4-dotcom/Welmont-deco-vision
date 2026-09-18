"""Visually test the trained model (data/adult_child_model.joblib) against a
video: runs the same pose detection + feature extraction as
1_collect_features.py, predicts adult/child per person with the trained
model, and writes an annotated copy of the video so you can watch whether
the predictions actually look right — a sanity check the classification_report
numbers in 3_train_model.py's output can't give you on their own.

Per-frame predictions naturally wobble near the model's 0.5 decision
boundary — the same person can score 0.52 one frame and 0.48 the next,
flipping the displayed label for no real reason. To avoid that flicker,
this tracks each person across frames (simple IOU matching — good enough
for a single camera, no need for full ByteTrack here), averages their
score over a rolling window, and only *commits* to ADULT or CHILD once the
smoothed score is confidently past the threshold — then keeps that label
sticky until the evidence flips decisively the other way. Gray "..." boxes
are tracks that haven't accumulated enough confident evidence yet.

This is separate from the numbered pipeline (1/2/3) since it's not something
you run once — it's a tool you come back to after every retrain to eyeball
results on footage the model didn't see during training.

Run:
    python test_model.py --source some_clip.mp4 --dir data/
"""
from __future__ import annotations

import argparse
import math
import time
from collections import deque
from pathlib import Path

import cv2
import joblib
import pandas as pd

# Must match NUMERIC_FEATURE_COLUMNS in 3_train_model.py, same order — the
# model only knows how to score a feature vector built exactly this way.
NUMERIC_FEATURE_COLUMNS = [
    "shoulder_width", "head_width", "build_ratio", "leg_to_upper_ratio", "box_height", "detector_confidence",
]

KP_LEFT_EAR, KP_RIGHT_EAR = 3, 4
KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER = 5, 6
KP_LEFT_HIP, KP_RIGHT_HIP = 11, 12
KP_LEFT_KNEE, KP_RIGHT_KNEE = 13, 14
KP_LEFT_ANKLE, KP_RIGHT_ANKLE = 15, 16

DETECTION_CONFIDENCE = 0.4
KEYPOINT_CONFIDENCE_MIN = 0.3

# Temporal smoothing — same idea as the main backend's RollingClassificationHistory:
# average the last CLASSIFICATION_WINDOW raw scores per tracked person, and only
# switch the displayed label once that average is confidently past one of the
# two thresholds. Between the thresholds, keep whatever was last committed.
CLASSIFICATION_WINDOW = 15
ADULT_CONFIDENCE_THRESHOLD = 0.75  # smoothed adult-probability >= this -> commit ADULT
CHILD_CONFIDENCE_THRESHOLD = 0.75  # smoothed child-probability >= this -> commit CHILD
IOU_MATCH_THRESHOLD = 0.3  # frame-to-frame box overlap needed to treat it as the same person
MAX_MISSED_FRAMES = 10  # drop a track if it isn't matched for this many consecutive frames


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
        self.committed_label: str | None = None  # None | "adult" | "child" — sticky once set
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
        # else: evidence isn't decisive enough to change anything — stay as-is.


def _match_tracks(tracks: list[Track], boxes: list) -> tuple[dict[int, int], list[int]]:
    """Greedy IOU matching. Returns {detection_index: track_index} and the
    list of detection indices left unmatched (to become new tracks)."""
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


def _kp(keypoints_xy, keypoints_conf, index: int):
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


def extract_feature_vector(box_xyxy, box_conf, keypoints_xy, keypoints_conf) -> list[float]:
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
    else:
        head_width = max(0.0, shoulder[1] - y1) if shoulder else 0.0

    build_ratio = (shoulder_width / head_width) if (shoulder_width > 1e-3 and head_width > 1e-3) else 0.0

    hip = _midpoint(_kp(keypoints_xy, keypoints_conf, KP_LEFT_HIP), _kp(keypoints_xy, keypoints_conf, KP_RIGHT_HIP))
    knee = _midpoint(_kp(keypoints_xy, keypoints_conf, KP_LEFT_KNEE), _kp(keypoints_xy, keypoints_conf, KP_RIGHT_KNEE))
    ankle = _midpoint(_kp(keypoints_xy, keypoints_conf, KP_LEFT_ANKLE), _kp(keypoints_xy, keypoints_conf, KP_RIGHT_ANKLE))

    leg_to_upper_ratio = 0.0
    if hip and ankle and _leg_is_extended(hip, knee, ankle) and shoulder:
        head_len = max(0.0, shoulder[1] - y1)
        torso_len = _dist(shoulder, hip)
        leg_len = _dist(hip, ankle)
        upper_body = torso_len + head_len
        if upper_body > 1e-3:
            leg_to_upper_ratio = leg_len / upper_body

    return [shoulder_width, head_width, build_ratio, leg_to_upper_ratio, box_height, float(box_conf)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the trained model against a video and save annotated output.")
    parser.add_argument("--source", required=True, help="Video file to test against.")
    parser.add_argument("--dir", default="data", help="Dataset directory containing adult_child_model.joblib")
    parser.add_argument("--out", default=None, help="Output video path (default: <dir>/test_output_<source>.mp4)")
    return parser.parse_args()


def main() -> None:
    from ultralytics import YOLO

    args = parse_args()
    data_dir = Path(args.dir)
    model_path = data_dir / "adult_child_model.joblib"
    source_path = Path(args.source)
    out_path = Path(args.out) if args.out else data_dir / f"test_output_{source_path.stem}.mp4"

    if not model_path.exists():
        print(f"{model_path} not found — run 3_train_model.py first.")
        return
    if not source_path.exists():
        print(f"--source does not exist: {source_path.resolve()}")
        return

    bundle = joblib.load(model_path)
    clf = bundle["model"]
    feature_columns = bundle["feature_columns"]

    pose_model_path = "yolov8n-pose.pt" if Path("yolov8n-pose.pt").exists() else "../models/yolov8n-pose.pt"
    print(f"Loading pose model {pose_model_path} ...")
    pose_model = YOLO(pose_model_path)

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
        results = pose_model.predict(frame, conf=DETECTION_CONFIDENCE, verbose=False)
        if results and results[0].keypoints is not None and results[0].boxes is not None:
            raw_boxes = results[0].boxes.xyxy.tolist()
            confs = results[0].boxes.conf.tolist()
            all_kps = results[0].keypoints.data.tolist()

            for i, box in enumerate(raw_boxes):
                kps = all_kps[i]
                kp_xy = [(p[0], p[1]) for p in kps]
                kp_conf = [p[2] for p in kps]
                features = extract_feature_vector(box, confs[i], kp_xy, kp_conf)
                feature_row = pd.DataFrame([features], columns=NUMERIC_FEATURE_COLUMNS)[feature_columns]
                boxes.append(box)
                probabilities.append(float(clf.predict_proba(feature_row)[0][1]))

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
                continue  # not seen this frame — nothing to draw
            x1, y1, x2, y2 = (int(v) for v in track.box)
            if track.committed_label == "adult":
                color, text = (0, 140, 255), "ADULT"  # BGR orange
            elif track.committed_label == "child":
                color, text = (0, 200, 0), "CHILD"  # BGR green
            else:
                color, text = (160, 160, 160), "..."  # still deciding — gray
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
    print(f"\nAnnotated video saved to {out_path} — open it and watch whether the boxes/labels look right.")
    print("Orange box = committed ADULT, green box = committed CHILD, gray '...' = still deciding.")
    print(f"A label only commits after {CLASSIFICATION_WINDOW}-frame smoothing crosses "
          f"{ADULT_CONFIDENCE_THRESHOLD:.0%} confidence, then stays sticky.")


if __name__ == "__main__":
    main()

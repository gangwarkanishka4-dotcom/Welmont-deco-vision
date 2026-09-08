"""Door line-crossing supervision monitor.

Watches a camera pointed at a classroom door/gate, tracks each person across
frames with YOLOv8-Pose's built-in ByteTrack (model.track(persist=True)),
and counts adults currently inside the room by watching which direction each
tracked person's centroid crosses a configurable virtual line at the
doorway. Classroom status is derived purely from that adult count, with a
short debounce before flipping to "unsupervised" so a momentary tracking
glitch right at the threshold doesn't cause a false alarm.

This classroom's children are a known, narrow band — 3-3.5 years old,
94-99cm tall (see CONFIG) — not a general child population, which is what
lets the adult/child thresholds be tight and confident rather than hedged
against a wide age range. Classification works from any angle (front, back,
side-on): it deliberately never depends on the nose/eyes/ears being visible,
using the detection box's own top edge as the head reference instead, and
is smoothed per tracked person over a rolling vote buffer rather than
trusting any single frame.

Run:
    uvicorn door_monitor:app --host 0.0.0.0 --port 8000
(or `python door_monitor.py`, which does the same via __main__ below)

Then:
    GET  http://localhost:8000/status/{classroom_id}
    WS   ws://localhost:8000/ws
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
logger = logging.getLogger("door_monitor")

# ============================================================================
# CONFIG — everything you're likely to need to change lives here.
# ============================================================================

# One entry per classroom. `door_line` is two (x, y) pixel points spanning
# the doorway edge to edge, in the camera's native frame resolution — e.g.
# for a 1280x720 stream with the door filling the frame horizontally at
# roughly waist height, (0, 380) to (1280, 380) is a full-width horizontal
# line. For a door the camera sees edge-on (person walks left-right through
# a narrow gap), a vertical line like (640, 0) to (640, 720) is more natural.
# Pick whichever axis actually crosses the direction people walk.
CLASSROOMS = [
    {
        "classroom_id": "class-1",
        "name": "Classroom 1",
        # TODO: put your real camera's RTSP URL here, e.g.
        # "rtsp://admin:yourpassword@192.168.1.50:554/Streaming/Channels/101"
        "rtsp_url": "rtsp://<username>:<password>@<camera-ip>:554/<stream-path>",
        # TODO: adjust to your camera's actual frame size and door position.
        # Placeholder below spans the full width of a 1280x720 frame at
        # y=380 (a horizontal line — a person walks through it vertically).
        "door_line": ((0, 380), (1280, 380)),
        # Which side of the line is "inside" the room. The line has two
        # sides, signed + or - by _side_of_line() below; flip this if entries
        # and exits come out reversed once you test against the real camera.
        "inside_is_positive_side": True,
    },
    # Add more classrooms here, one dict per camera.
]

# This classroom's children are a KNOWN, NARROW band — exactly 3-3.5 years
# old, 94-99cm tall — not a general "child" population. That narrowness is
# the whole point: it gives a wide, reliable separation margin from any
# adult, which is what lets the thresholds below be tight and confident
# instead of the wide error bars a general age range would force.
CHILD_HEIGHT_CM_MIN = 94.0
CHILD_HEIGHT_CM_MAX = 99.0
CHILD_HEIGHT_CM_MID = (CHILD_HEIGHT_CM_MIN + CHILD_HEIGHT_CM_MAX) / 2.0  # 96.5cm

# Bounding-box height signal. There's no camera calibration step here (see
# Welmont's ROI/calibration UI for what a real one looks like) — converting
# real cm to pixels needs the camera's distance/geometry, which this script
# doesn't have. Instead, the rolling reference tracks a LOW percentile of
# recent box heights in this classroom, which — since this door's traffic is
# overwhelmingly the known 94-99cm children, with adults a minority — should
# closely and robustly track "94-99cm in pixels right now" without being
# pulled upward by the occasional taller adult passing through. A typical
# adult (~155-175cm) against that band gives a real ratio of ~1.57-1.86x;
# ADULT_HEIGHT_RATIO_MIN is set toward the low end of that (matching the
# brief's "1.4x+") so a shorter adult still clears it confidently.
HEIGHT_REFERENCE_WINDOW = 150  # how many recent detections feed the rolling child-height reference
HEIGHT_REFERENCE_PERCENTILE = 30  # low percentile => robust to a taller adult occasionally in the mix
ADULT_HEIGHT_RATIO_MIN = 1.4  # sigmoid midpoint: person_height / rolling_child_reference
HEIGHT_RATIO_STEEPNESS = 6.0

# Skeleton signal: head_length (bbox TOP EDGE -> shoulder-midpoint) /
# total_length (bbox top -> ankle-midpoint) — deliberately NOT the nose/eyes,
# since this must work from any angle (front, back, side) and a preschooler
# is rarely posed facing the camera. The box's own top edge is produced by
# the detector for every detection regardless of which way someone's facing.
#
# Real proportions: an adult's head+neck-to-shoulder-line span is roughly
# 20-24cm against a ~155-175cm height -> ratio ~0.12-0.14. A 3-3.5y toddler's
# is proportionally much bigger (bigger head, much shorter body) against the
# known 94-99cm band -> ratio ~0.20-0.23. HEAD_TOTAL_RATIO_MIDPOINT sits
# between those two known, narrow clusters, biased slightly toward the adult
# side per the brief (minimize adults missed/misclassified as children) —
# the wide margin the known bands provide means this bias doesn't risk
# misreading real children, it just resolves genuine borderline frames
# toward ADULT rather than CHILD.
HEAD_TOTAL_RATIO_MIDPOINT = 0.16
HEAD_TOTAL_RATIO_STEEPNESS = 14.0  # steep: the known, narrow bands make this a confident, non-fuzzy cutoff

# Pose is weighted higher than height — it's orientation-robust (works
# front/back/side-on), the height signal only works when the full body up to
# the ankles is actually visible and undistorted by perspective.
POSE_SIGNAL_WEIGHT = 0.65
HEIGHT_SIGNAL_WEIGHT = 0.35
ADULT_SCORE_THRESHOLD = 0.5  # per-frame vote: >= this this frame => "adult" vote

# Per-track temporal smoothing: majority vote over the last N frames' votes,
# not a single frame's snapshot — absorbs one-off pose/keypoint noise. On a
# genuine tie, resolve to ADULT (see brief: bias toward not missing adults).
SMOOTHING_WINDOW = 10

# How long adult_count must stay at 0 before the room flips to
# "unsupervised" — absorbs a brief tracking glitch right at the line.
DEBOUNCE_SECONDS = 7.0

# How long a track can go unseen before its per-track buffers are dropped —
# plain memory hygiene, not part of the classification logic.
TRACK_FORGET_SECONDS = 30.0

# Detection/tracking model + confidence floors.
POSE_MODEL_PATH = "yolov8n-pose.pt"  # auto-downloaded by ultralytics on first run
DETECTION_CONFIDENCE = 0.4
KEYPOINT_CONFIDENCE_MIN = 0.5  # per brief: "e.g. 0.5" for a shoulder/ankle keypoint to be trusted

# COCO-17 keypoint indices (Ultralytics' order). Nose/eyes/ears deliberately
# unused for classification — see HEAD_TOTAL_RATIO_MIDPOINT above.
KP_LEFT_SHOULDER, KP_RIGHT_SHOULDER = 5, 6
KP_LEFT_ANKLE, KP_RIGHT_ANKLE = 15, 16

# ============================================================================
# Geometry helpers
# ============================================================================


def _side_of_line(point: tuple[float, float], line: tuple[tuple[float, float], tuple[float, float]]) -> float:
    """Signed distance-like value: >0 on one side of the (infinite) line
    through line[0]/line[1], <0 on the other, 0 exactly on it. Works for a
    line of any orientation, not just axis-aligned."""
    (x1, y1), (x2, y2) = line
    px, py = point
    return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)


def _sigmoid(x: float, midpoint: float, steepness: float) -> float:
    return 1.0 / (1.0 + np.exp(-steepness * (x - midpoint)))


def _keypoint(kpts_xy: np.ndarray, kpts_conf: np.ndarray, index: int) -> tuple[float, float] | None:
    if kpts_conf[index] < KEYPOINT_CONFIDENCE_MIN:
        return None
    return float(kpts_xy[index][0]), float(kpts_xy[index][1])


def _midpoint(a: tuple[float, float] | None, b: tuple[float, float] | None) -> tuple[float, float] | None:
    """Average whichever of the pair is confidently available — per brief,
    a single confident side (e.g. only the left shoulder, the right one
    occluded) should still count, not be discarded for lack of its pair."""
    if a and b:
        return (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
    return a or b


# ============================================================================
# Classification
# ============================================================================


class RollingChildHeightReference:
    """Tracks recent box heights for one classroom to approximate "94-99cm
    in pixels right now" (see HEIGHT_REFERENCE_PERCENTILE above) — adapts
    automatically to this camera's actual distance/depth-of-field instead of
    a single fixed pixel number that would break the moment either changes."""

    def __init__(self, window: int) -> None:
        self._heights: deque[float] = deque(maxlen=window)

    def push(self, height: float) -> None:
        self._heights.append(height)

    def reference_height(self) -> float | None:
        if not self._heights:
            return None
        return float(np.percentile(self._heights, HEIGHT_REFERENCE_PERCENTILE))


def classify_adult_score(
    box_top_y: float,
    box_height: float,
    height_reference: RollingChildHeightReference,
    kpts_xy: np.ndarray,
    kpts_conf: np.ndarray,
) -> float:
    """Returns this frame's adult-likeness score in 0..1, combining the
    bbox-height-vs-rolling-child-reference signal and the bbox-top-based
    skeleton ratio. Either can abstain (contribute nothing) if its inputs
    aren't available this frame; with neither available this returns a
    neutral 0.5. This is a single frame's opinion — see
    ClassroomState.record_vote/majority_is_adult for the temporal
    majority-vote smoothing applied on top of it."""
    scores: list[tuple[float, float]] = []  # (weight, score)

    ref = height_reference.reference_height()
    if ref and ref > 1e-3:
        height_ratio = box_height / ref
        scores.append((HEIGHT_SIGNAL_WEIGHT, _sigmoid(height_ratio, ADULT_HEIGHT_RATIO_MIN, HEIGHT_RATIO_STEEPNESS)))

    shoulder = _midpoint(
        _keypoint(kpts_xy, kpts_conf, KP_LEFT_SHOULDER), _keypoint(kpts_xy, kpts_conf, KP_RIGHT_SHOULDER)
    )
    ankle = _midpoint(_keypoint(kpts_xy, kpts_conf, KP_LEFT_ANKLE), _keypoint(kpts_xy, kpts_conf, KP_RIGHT_ANKLE))
    # bbox top edge stands in for the head-top reference point — orientation
    # invariant (works facing the camera, away from it, or side-on), unlike
    # the nose/eyes, which a preschooler rarely presents to the camera.
    # Vertical distance only (not full 2D) — box_top_y has no meaningful x
    # of its own, so pairing it with a keypoint's real x would inject a
    # spurious horizontal offset into what should be a pure head-length
    # measurement.
    head_len = max(0.0, shoulder[1] - box_top_y) if shoulder else None
    body_len = max(0.0, ankle[1] - box_top_y) if ankle else None
    if head_len is not None and body_len and body_len > 1e-3:
        head_total_ratio = head_len / body_len
        # Higher ratio => bigger head relative to body => more child-like =>
        # LOWER adult score, hence the "1 - sigmoid" here vs. the height
        # signal above (which increases WITH the raw ratio for adults).
        scores.append(
            (POSE_SIGNAL_WEIGHT, 1.0 - _sigmoid(head_total_ratio, HEAD_TOTAL_RATIO_MIDPOINT, HEAD_TOTAL_RATIO_STEEPNESS))
        )

    if not scores:
        return 0.5
    total_weight = sum(w for w, _ in scores)
    return sum(w * s for w, s in scores) / total_weight


# ============================================================================
# Per-classroom state
# ============================================================================


@dataclass
class ClassroomState:
    classroom_id: str
    name: str
    adult_count: int = 0
    status: str = "supervised"  # "supervised" | "unsupervised"
    _zero_since: float | None = field(default=None, repr=False)
    _track_sides: dict[int, float] = field(default_factory=dict, repr=False)
    # Per-tracked-ID vote buffers — a dict keyed by track_id, deliberately,
    # so 2-3 simultaneous people each accumulate independently with no
    # cross-interference between them (never a single frame-global buffer).
    _track_votes: dict[int, deque[bool]] = field(default_factory=dict, repr=False)
    _track_last_seen: dict[int, float] = field(default_factory=dict, repr=False)

    def record_vote(self, track_id: int, is_adult_this_frame: bool, now: float) -> None:
        votes = self._track_votes.setdefault(track_id, deque(maxlen=SMOOTHING_WINDOW))
        votes.append(is_adult_this_frame)
        self._track_last_seen[track_id] = now

    def majority_is_adult(self, track_id: int) -> bool:
        votes = self._track_votes.get(track_id)
        if not votes:
            return False
        adult_votes = sum(votes)
        return adult_votes >= len(votes) / 2.0  # tie resolves to ADULT — see SMOOTHING_WINDOW comment

    def forget_stale_tracks(self, now: float) -> None:
        stale = [tid for tid, last_seen in self._track_last_seen.items() if now - last_seen > TRACK_FORGET_SECONDS]
        for tid in stale:
            self._track_votes.pop(tid, None)
            self._track_last_seen.pop(tid, None)
            self._track_sides.pop(tid, None)

    def register_crossing(self, is_adult: bool, entering: bool) -> None:
        if is_adult:
            if entering:
                self.adult_count += 1
            else:
                self.adult_count = max(0, self.adult_count - 1)

        if self.adult_count > 0:
            self._zero_since = None
            if self.status != "supervised":
                self.status = "supervised"
                logger.info("Classroom %s -> SUPERVISED (adult_count=%d)", self.classroom_id, self.adult_count)
        else:
            if self._zero_since is None:
                self._zero_since = time.time()

    def debounce_tick(self, now: float) -> bool:
        """Call periodically (independent of crossing events) so a
        sustained adult_count==0 eventually flips status even with no new
        crossings. Returns True if status changed this tick."""
        if self.adult_count == 0 and self._zero_since is not None and self.status != "unsupervised":
            if now - self._zero_since >= DEBOUNCE_SECONDS:
                self.status = "unsupervised"
                logger.warning("Classroom %s -> UNSUPERVISED (adult_count=0 for %.0fs)", self.classroom_id, DEBOUNCE_SECONDS)
                return True
        return False

    def as_dict(self) -> dict:
        return {"classroom_id": self.classroom_id, "name": self.name, "adult_count": self.adult_count, "status": self.status}


class StateStore:
    """Thread-safe holder for every classroom's state — camera worker
    threads write to it, the async FastAPI handlers read from it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, ClassroomState] = {}

    def register(self, classroom_id: str, name: str) -> None:
        with self._lock:
            self._states[classroom_id] = ClassroomState(classroom_id=classroom_id, name=name)

    def get(self, classroom_id: str) -> dict | None:
        with self._lock:
            state = self._states.get(classroom_id)
            return state.as_dict() if state else None

    def all_ids(self) -> list[str]:
        with self._lock:
            return list(self._states.keys())

    def with_lock(self, classroom_id: str, fn) -> dict | None:
        """Run `fn(state)` under the lock and return the resulting dict
        snapshot — used by camera workers to mutate + snapshot atomically."""
        with self._lock:
            state = self._states.get(classroom_id)
            if state is None:
                return None
            fn(state)
            return state.as_dict()


STORE = StateStore()

# ============================================================================
# WebSocket broadcasting (bridges background camera threads -> async clients)
# ============================================================================


class Broadcaster:
    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._sockets.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._sockets.discard(ws)

    async def _broadcast(self, payload: dict) -> None:
        async with self._lock:
            dead = set()
            for ws in self._sockets:
                try:
                    await ws.send_json(payload)
                except Exception:
                    dead.add(ws)
            self._sockets -= dead

    def broadcast_from_thread(self, payload: dict) -> None:
        """Call from a non-async camera-worker thread."""
        if self.loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), self.loop)


BROADCAST = Broadcaster()

# ============================================================================
# Camera worker — one background thread per classroom
# ============================================================================


class CameraWorker(threading.Thread):
    def __init__(self, config: dict) -> None:
        super().__init__(daemon=True)
        self.classroom_id = config["classroom_id"]
        self.name_label = config["name"]
        self.rtsp_url = config["rtsp_url"]
        self.door_line = config["door_line"]
        self.inside_is_positive = config["inside_is_positive_side"]
        self.height_ref = RollingChildHeightReference(HEIGHT_REFERENCE_WINDOW)
        self.model = YOLO(POSE_MODEL_PATH)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        logger.info("Classroom %s: connecting to %s", self.classroom_id, self.rtsp_url)
        cap = cv2.VideoCapture(self.rtsp_url)
        if not cap.isOpened():
            logger.error("Classroom %s: failed to open RTSP stream", self.classroom_id)
            return

        while not self._stop:
            ok, frame = cap.read()
            if not ok or frame is None:
                logger.warning("Classroom %s: frame read failed, retrying", self.classroom_id)
                time.sleep(1.0)
                continue

            results = self.model.track(frame, persist=True, conf=DETECTION_CONFIDENCE, verbose=False)
            self._process_result(results[0] if results else None)

        cap.release()

    def _process_result(self, result) -> None:
        if result is None or result.boxes is None or result.boxes.id is None:
            return

        boxes_xyxy = result.boxes.xyxy.cpu().numpy()
        track_ids = result.boxes.id.int().cpu().numpy()
        keypoints_xy = result.keypoints.xy.cpu().numpy() if result.keypoints is not None else None
        keypoints_conf = result.keypoints.conf.cpu().numpy() if result.keypoints is not None else None

        now = time.time()

        for i, track_id in enumerate(track_ids):
            track_id = int(track_id)
            x1, y1, x2, y2 = boxes_xyxy[i]
            box_height = float(y2 - y1)
            centroid = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            self.height_ref.push(box_height)

            side = _side_of_line(centroid, self.door_line)
            kpts_xy = keypoints_xy[i] if keypoints_xy is not None else np.zeros((17, 2))
            kpts_conf = keypoints_conf[i] if keypoints_conf is not None else np.zeros(17)

            # Classified and voted on EVERY frame the track is visible, not
            # just at the moment it crosses — the majority vote read at the
            # crossing instant below needs a buffer that's had time to fill.
            adult_score_this_frame = classify_adult_score(float(y1), box_height, self.height_ref, kpts_xy, kpts_conf)
            is_adult_this_frame = adult_score_this_frame >= ADULT_SCORE_THRESHOLD
            crossed = False

            def _apply(state: ClassroomState, _side=side, _track_id=track_id, _now=now) -> None:
                nonlocal crossed
                state.record_vote(_track_id, is_adult_this_frame, _now)

                previous_side = state._track_sides.get(_track_id)  # noqa: SLF001 (this module's own state)
                state._track_sides[_track_id] = _side  # noqa: SLF001

                if previous_side is None or (previous_side > 0) == (_side > 0):
                    return  # no side flip this frame — either brand new track or no crossing

                crossed = True
                went_positive = _side > 0
                entering = went_positive if self.inside_is_positive else not went_positive

                # Majority vote over the track's whole recent buffer, not
                # just this single frame's score — absorbs one-off noise
                # right at the crossing instant.
                is_adult = state.majority_is_adult(_track_id)
                logger.info(
                    "Classroom %s: track %d crossed %s -> %s",
                    self.classroom_id, _track_id, "IN" if entering else "OUT", "ADULT" if is_adult else "CHILD",
                )
                state.register_crossing(is_adult, entering=entering)

            snapshot = STORE.with_lock(self.classroom_id, _apply)
            if snapshot and crossed:
                BROADCAST.broadcast_from_thread(snapshot)


class DebounceWatcher(threading.Thread):
    """Periodically checks every classroom for a sustained adult_count==0,
    since that transition must happen even with no new door crossings."""

    def __init__(self, interval_seconds: float = 0.5) -> None:
        super().__init__(daemon=True)
        self.interval_seconds = interval_seconds
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        while not self._stop:
            time.sleep(self.interval_seconds)
            now = time.time()
            for classroom_id in STORE.all_ids():
                changed = False

                def _tick(state: ClassroomState, _now=now) -> None:
                    nonlocal changed
                    changed = state.debounce_tick(_now)
                    state.forget_stale_tracks(_now)

                snapshot = STORE.with_lock(classroom_id, _tick)
                if snapshot and changed:
                    BROADCAST.broadcast_from_thread(snapshot)


# ============================================================================
# FastAPI app
# ============================================================================

app = FastAPI(title="Door Monitor")
_workers: list[CameraWorker] = []
_debounce_watcher: DebounceWatcher | None = None


@app.on_event("startup")
async def on_startup() -> None:
    global _debounce_watcher
    BROADCAST.loop = asyncio.get_running_loop()

    for config in CLASSROOMS:
        STORE.register(config["classroom_id"], config["name"])
        worker = CameraWorker(config)
        worker.start()
        _workers.append(worker)

    _debounce_watcher = DebounceWatcher()
    _debounce_watcher.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    for worker in _workers:
        worker.stop()
    if _debounce_watcher:
        _debounce_watcher.stop()


@app.get("/status/{classroom_id}")
async def get_status(classroom_id: str):
    state = STORE.get(classroom_id)
    if state is None:
        return {"error": f"unknown classroom_id '{classroom_id}'"}
    return state


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await BROADCAST.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # client doesn't need to send anything; just keeps the connection open
    except WebSocketDisconnect:
        await BROADCAST.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

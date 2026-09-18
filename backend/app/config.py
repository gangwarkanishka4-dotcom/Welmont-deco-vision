"""Central runtime configuration. Every tunable in the spec is read from the
environment (via .env) — nothing here should require a code change to retune."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/classroom_monitor"
    redis_url: str = "redis://localhost:6379/0"

    # Secrets
    secret_key: str = "dev-secret-change-me"
    credential_encryption_key: str = ""  # Fernet key used to encrypt RTSP passwords at rest

    # Models
    person_model: str = "models/yolov8n.pt"
    age_model: str = ""  # optional trained adult/child classifier (.pt/.onnx/.engine)

    # Optional trained adult/child classifier from ml_pipeline/ (RandomForest
    # over pose-derived features — shoulder/head width, build ratio, etc —
    # not a raw-pixel model, so it's a separate hook from age_model above).
    # Leave blank to keep using the heuristic geometry/pose classifier.
    trained_feature_classifier_path: str = ""
    pose_model: str = "models/yolov8n-pose.pt"
    device: str = "auto"  # auto | cpu | cuda
    detector_classes: str = "0"
    detector_conf_threshold: float = 0.37
    detector_iou_threshold: float = 0.45

    # Pipeline pacing
    inference_fps: int = 12
    classification_every_n_detect: int = 3
    track_timeout_seconds: float = 2.0

    # How often (seconds) to override the gate-crossing occupancy tally with
    # a direct, ground-truth ROI scan of everyone currently tracked. Crossing
    # events are low-latency but can drift (a missed "entered"/"exited" from
    # a tracker glitch permanently mis-states occupancy until corrected) —
    # this bounds how long that drift can persist. Also fires immediately on
    # camera (re)connect, since a crossing-only tally starts at zero and has
    # no way to know who was already in the room before the stream opened.
    occupancy_reconcile_interval_seconds: float = 25.0

    # How long (seconds) after a (re)connect the ground-truth reconcile above
    # stays active on every frame, not just the first one back. Real bug
    # found live (2026-09-15): detection can take a frame or two to
    # restabilize right after an RTSP stream reopens — a confirmed adult who
    # simply isn't re-detected on that exact single reconcile frame falls out
    # of the gate-crossing tally and stays excluded until the next scheduled
    # reconcile (up to occupancy_reconcile_interval_seconds later), producing
    # a false "no adult" reading the whole time despite correct
    # classification on every frame once they reappear.
    reconnect_reconcile_grace_seconds: float = 5.0

    # An adult confirmed "inside" via gate crossing stays counted toward
    # adult_count even while not currently re-detected (occlusion, tracker
    # glitch, briefly out of camera view) — only an actual "exited" gate
    # crossing removes them, not merely dropping out of the current frame's
    # tracks. This is what stops a momentarily-invisible teacher from
    # falsely flipping the room to UNSUPERVISED. This timeout is the safety
    # net for the case that genuinely matters: they left without a clean
    # exit crossing (camera glitch, walked out somewhere the gate line
    # doesn't cover) — bounding how long a departed adult can stay
    # phantom-counted.
    #
    # Narrowed from 300.0 (2026-09-15): real bug found live — on a busy
    # camera, tracker ID churn happens often enough (every reconnect assigns
    # some tracks fresh IDs) that phantom entries were accumulating faster
    # than the old 300s window ever cleared them, inflating adult_count to
    # 7-8 in a room with 1-2 real adults. reconnect_reconcile_grace_seconds
    # above now handles the specific "briefly not re-detected right after a
    # reconnect" case within 5 seconds, which was this setting's original
    # motivating scenario — so it no longer needs to be anywhere near this
    # long. Still comfortably longer than track_timeout_seconds (classifier
    # bookkeeping only) and any normal RTSP blip.
    adult_presence_timeout_seconds: float = 60.0

    # Periodic "digital zoom" pass: on cameras with zoom_regions configured
    # (see CameraConfiguration), every zoom_pass_interval_seconds the worker
    # spends the next zoom_pass_duration_seconds also cropping+upscaling
    # those specific regions and running the detector on the enlarged crop —
    # small/distant/seated people who read under the detector's confidence
    # threshold at native resolution often clear it once enlarged. This is
    # purely additive: the normal full-frame pass still runs every frame
    # regardless (occupancy tracking never stops for this), and only
    # genuinely new boxes the full-frame pass missed get merged in — see
    # app/cv/zoom_pass.py. A camera with no zoom_regions configured is
    # completely unaffected (the whole thing is a no-op).
    zoom_pass_interval_seconds: float = 60.0
    zoom_pass_duration_seconds: float = 10.0
    zoom_pass_upscale: float = 2.5

    # Classification
    classification_window: int = 15
    adult_confidence_threshold: float = 0.75
    child_confidence_threshold: float = 0.75

    # Supervision state machine
    unsupervised_delay_seconds: float = 10.0
    adult_grace_period_seconds: float = 3.0
    # Widened from 5.0 (2026-09-15): this RTSP-over-internet feed routinely
    # has brief multi-second drops that recover on their own — was also
    # being bypassed by a dead-code bug that ignored this value entirely
    # (see CameraWorker.run()), so its old value was never actually tested
    # against real behavior. 15s tolerates a normal blip without flapping
    # the dashboard's online/offline badge for something that self-resolves.
    camera_offline_timeout_seconds: float = 15.0

    # Assumed average adult height (cm), used only to convert a person's
    # calibration-derived height *ratio* into a display centimeter estimate —
    # not a precision measurement. Adjust to the real local average if known.
    reference_adult_height_cm: float = 165.0

    # Video buffer / clips
    video_buffer_seconds: int = 10
    # 2 = today's and yesterday's data only (2026-09-15, per Welmont's request).
    # Governs both video clips AND alert/incident history — see
    # app.video.retention.run_retention_sweep. One retention policy, not two.
    video_retention_days: int = 2
    clip_storage_dir: str = "./storage/clips"

    # Hardware
    alert_output_driver: str = "mock"  # mock | network_relay | esp32
    relay_base_url: str = "http://192.168.1.50"
    relay_timeout_seconds: float = 2.0
    relay_max_retries: int = 3

    # Misc
    debug_mode: bool = False
    cors_origins: str = "http://localhost:5173"

    @property
    def detector_class_ids(self) -> list[int]:
        return [int(c) for c in self.detector_classes.split(",") if c.strip() != ""]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_storage_dirs(self) -> None:
        Path(self.clip_storage_dir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_storage_dirs()
    return settings

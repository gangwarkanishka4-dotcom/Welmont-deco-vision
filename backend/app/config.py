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
    pose_model: str = "models/yolov8n-pose.pt"
    device: str = "auto"  # auto | cpu | cuda
    detector_classes: str = "0"
    detector_conf_threshold: float = 0.4
    detector_iou_threshold: float = 0.45

    # Pipeline pacing
    inference_fps: int = 12
    classification_every_n_detect: int = 3
    track_timeout_seconds: float = 2.0

    # Classification
    classification_window: int = 15
    adult_confidence_threshold: float = 0.75
    child_confidence_threshold: float = 0.75

    # Supervision state machine
    unsupervised_delay_seconds: float = 10.0
    adult_grace_period_seconds: float = 3.0
    camera_offline_timeout_seconds: float = 5.0

    # Assumed average adult height (cm), used only to convert a person's
    # calibration-derived height *ratio* into a display centimeter estimate —
    # not a precision measurement. Adjust to the real local average if known.
    reference_adult_height_cm: float = 165.0

    # Video buffer / clips
    video_buffer_seconds: int = 10
    video_retention_days: int = 7
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

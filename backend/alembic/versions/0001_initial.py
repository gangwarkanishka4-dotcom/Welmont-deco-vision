"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classrooms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), default=""),
        sa.Column("role", sa.String(20), default="VIEWER"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "cameras",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("classroom_id", sa.String(36), sa.ForeignKey("classrooms.id"), nullable=False),
        sa.Column("rtsp_host", sa.String(255), nullable=False),
        sa.Column("rtsp_port", sa.Integer, default=554),
        sa.Column("rtsp_path", sa.String(500), default=""),
        sa.Column("rtsp_username", sa.String(255), default=""),
        sa.Column("rtsp_password_encrypted", sa.String(500), default=""),
        sa.Column("fps", sa.Integer, default=25),
        sa.Column("resolution_width", sa.Integer, default=1920),
        sa.Column("resolution_height", sa.Integer, default=1080),
        sa.Column("status", sa.String(20), default="OFFLINE"),
        sa.Column("enabled", sa.Boolean, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cameras_classroom_id", "cameras", ["classroom_id"])
    op.create_index("ix_cameras_status", "cameras", ["status"])

    op.create_table(
        "camera_configurations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("camera_id", sa.String(36), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("roi_polygon", sa.JSON, default=list),
        sa.Column("calibration_points", sa.JSON, default=list),
        sa.Column("adult_height_ratio", sa.Float, default=0.85),
        sa.Column("child_height_ratio", sa.Float, default=0.60),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_camera_configurations_camera_id", "camera_configurations", ["camera_id"], unique=True)

    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.String(40), primary_key=True),
        sa.Column("incident_id", sa.String(40), nullable=False),
        sa.Column("camera_id", sa.String(36), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("classroom_id", sa.String(36), sa.ForeignKey("classrooms.id"), nullable=False),
        sa.Column("type", sa.String(40), default="UNSUPERVISED_CLASSROOM"),
        sa.Column("severity", sa.String(20), default="HIGH"),
        sa.Column("status", sa.String(20), default="ACTIVE"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("children_count", sa.Integer, default=0),
        sa.Column("adult_count", sa.Integer, default=0),
        sa.Column("snapshot_url", sa.String(500), nullable=True),
        sa.Column("clip_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alerts_incident_id", "alerts", ["incident_id"], unique=True)
    op.create_index("ix_alerts_camera_id", "alerts", ["camera_id"])
    op.create_index("ix_alerts_classroom_id", "alerts", ["classroom_id"])
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])

    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.String(40), sa.ForeignKey("alerts.alert_id"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("message", sa.Text, default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alert_events_alert_id", "alert_events", ["alert_id"])
    op.create_index("ix_alert_events_created_at", "alert_events", ["created_at"])

    op.create_table(
        "tracked_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("camera_id", sa.String(36), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("classroom_id", sa.String(36), sa.ForeignKey("classrooms.id"), nullable=False),
        sa.Column("track_id", sa.Integer, nullable=False),
        sa.Column("label", sa.String(10), nullable=False),
        sa.Column("smoothed_confidence", sa.Float, default=0.0),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tracked_events_camera_id", "tracked_events", ["camera_id"])
    op.create_index("ix_tracked_events_classroom_id", "tracked_events", ["classroom_id"])
    op.create_index("ix_tracked_events_created_at", "tracked_events", ["created_at"])

    op.create_table(
        "video_clips",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_id", sa.String(40), sa.ForeignKey("alerts.alert_id"), nullable=True),
        sa.Column("camera_id", sa.String(36), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_video_clips_alert_id", "video_clips", ["alert_id"])
    op.create_index("ix_video_clips_camera_id", "video_clips", ["camera_id"])
    op.create_index("ix_video_clips_created_at", "video_clips", ["created_at"])
    op.create_index("ix_video_clips_expires_at", "video_clips", ["expires_at"])

    op.create_table(
        "system_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("level", sa.String(10), default="INFO"),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("camera_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_system_logs_camera_id", "system_logs", ["camera_id"])
    op.create_index("ix_system_logs_created_at", "system_logs", ["created_at"])

    op.create_table(
        "access_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(20), default="view"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_access_logs_user_id", "access_logs", ["user_id"])
    op.create_index("ix_access_logs_resource_id", "access_logs", ["resource_id"])
    op.create_index("ix_access_logs_created_at", "access_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("access_logs")
    op.drop_table("system_logs")
    op.drop_table("video_clips")
    op.drop_table("tracked_events")
    op.drop_table("alert_events")
    op.drop_table("alerts")
    op.drop_table("camera_configurations")
    op.drop_table("cameras")
    op.drop_table("users")
    op.drop_table("classrooms")

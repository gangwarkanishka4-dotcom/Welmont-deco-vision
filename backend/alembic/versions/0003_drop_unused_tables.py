"""drop unused tables/columns: users, system_logs, access_logs, tracked_events, alerts.snapshot_url

These were confirmed dead — no route, worker, or auth flow anywhere in the
application reads or writes them (the snapshot capture path was removed
earlier; users/access_logs/tracked_events were unused scaffolding).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("alerts", "snapshot_url")
    op.drop_table("tracked_events")
    op.drop_table("access_logs")
    op.drop_table("system_logs")
    op.drop_table("users")


def downgrade() -> None:
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

    op.add_column("alerts", sa.Column("snapshot_url", sa.String(500), nullable=True))

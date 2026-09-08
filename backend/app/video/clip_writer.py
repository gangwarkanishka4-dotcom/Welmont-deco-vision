"""Writes an incident clip: RingBuffer pre-roll (last VIDEO_BUFFER_SECONDS)
+ a live post-roll tail, muxed into one mp4 file per alert. Runs as a
fire-and-forget background task so it never blocks alert creation.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2

from app.database import AsyncSessionLocal
from app.models.alert import Alert
from app.models.video_clip import VideoClip
from app.video.ring_buffer import RingBuffer

logger = logging.getLogger(__name__)


class ClipWriter:
    def __init__(self, storage_dir: str, retention_days: int, fps: int) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.fps = fps

    def schedule_incident_clip(self, camera_id: str, alert_id: str, ring_buffer: RingBuffer, tail_seconds: int) -> None:
        asyncio.create_task(self._capture(camera_id, alert_id, ring_buffer, tail_seconds))

    async def _capture(self, camera_id: str, alert_id: str, ring_buffer: RingBuffer, tail_seconds: int) -> None:
        try:
            pre_roll = ring_buffer.snapshot()
            last_ts = pre_roll[-1].timestamp if pre_roll else time.time()

            await asyncio.sleep(tail_seconds)

            later = ring_buffer.snapshot()
            post_roll = [f for f in later if f.timestamp > last_ts]
            frames = pre_roll + post_roll

            if not frames:
                logger.warning("No frames available to write incident clip for alert %s", alert_id)
                return

            file_path = self.storage_dir / f"{alert_id}.mp4"
            height, width = frames[0].frame.shape[:2]
            writer = cv2.VideoWriter(str(file_path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (width, height))
            try:
                for buffered in frames:
                    writer.write(buffered.frame)
            finally:
                writer.release()

            started_at = datetime.fromtimestamp(frames[0].timestamp, tz=timezone.utc)
            ended_at = datetime.fromtimestamp(frames[-1].timestamp, tz=timezone.utc)
            expires_at = datetime.now(timezone.utc) + timedelta(days=self.retention_days)

            async with AsyncSessionLocal() as session:
                clip = VideoClip(
                    alert_id=alert_id,
                    camera_id=camera_id,
                    file_path=str(file_path),
                    started_at=started_at,
                    ended_at=ended_at,
                    expires_at=expires_at,
                )
                session.add(clip)
                alert = await session.get(Alert, alert_id)
                if alert is not None:
                    # A browser-servable URL (see the /media/clips StaticFiles
                    # mount in app.main), not the raw filesystem path — that's
                    # what VideoClip.file_path is for (retention sweep).
                    alert.clip_url = f"/media/clips/{file_path.name}"
                await session.commit()

            logger.info("Incident clip written for alert %s: %s (%d frames)", alert_id, file_path, len(frames))
        except Exception:
            logger.exception("Failed to write incident clip for alert %s", alert_id)

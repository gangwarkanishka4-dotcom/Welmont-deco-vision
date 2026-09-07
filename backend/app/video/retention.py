"""Deletes clips (file + DB row) past their retention window. Scheduled as a
periodic background task from main.py — spec §11/§26: never store video
forever, retention configurable via VIDEO_RETENTION_DAYS."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.video_clip import VideoClip

logger = logging.getLogger(__name__)


async def run_retention_sweep(session_factory: async_sessionmaker) -> int:
    now = datetime.now(timezone.utc)
    deleted = 0
    async with session_factory() as session:
        expired = (await session.scalars(select(VideoClip).where(VideoClip.expires_at < now))).all()
        for clip in expired:
            path = Path(clip.file_path)
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    logger.warning("Could not delete expired clip file %s", path)
            await session.delete(clip)
            deleted += 1
        await session.commit()

    if deleted:
        logger.info("Retention sweep deleted %d expired clip(s)", deleted)
    return deleted


async def retention_loop(session_factory: async_sessionmaker, interval_seconds: int = 3600) -> None:
    while True:
        try:
            await run_retention_sweep(session_factory)
        except Exception:
            logger.exception("Retention sweep failed")
        await asyncio.sleep(interval_seconds)

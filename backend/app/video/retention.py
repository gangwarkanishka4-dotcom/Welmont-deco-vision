"""Deletes clips and old alert history past the retention window. Scheduled
as a periodic background task from main.py — spec §11/§26: never store video
forever, retention configurable via VIDEO_RETENTION_DAYS.

2026-09-15: this used to only ever delete VideoClip rows/files once their own
expires_at passed — the Alert (and AlertEvent) rows themselves were kept
forever, so the Alerts/Incidents pages kept accumulating history well past
the point their clips had already expired. Alert retention now uses the same
VIDEO_RETENTION_DAYS window, on the reasoning that an incident with no clip
left isn't worth keeping around indefinitely either — "keep N days of data"
is one policy, not two."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.alert import Alert
from app.models.video_clip import VideoClip

logger = logging.getLogger(__name__)


async def _delete_clip(session, clip: VideoClip, *, clear_alert_url: bool) -> None:
    path = Path(clip.file_path)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            logger.warning("Could not delete clip file %s", path)
    if clear_alert_url:
        # Otherwise the alert keeps pointing at a file that no longer
        # exists — the dashboard would show a broken video player instead
        # of correctly falling back to "clip not available".
        alert = await session.get(Alert, clip.alert_id)
        if alert is not None and alert.clip_url is not None:
            alert.clip_url = None
    await session.delete(clip)


async def run_retention_sweep(session_factory: async_sessionmaker, alert_retention_days: float) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    deleted_clips = 0
    deleted_alerts = 0

    async with session_factory() as session:
        # Clips whose own expiry has passed, independent of their alert's age.
        expired_clips = (await session.scalars(select(VideoClip).where(VideoClip.expires_at < now))).all()
        for clip in expired_clips:
            await _delete_clip(session, clip, clear_alert_url=True)
            deleted_clips += 1
        await session.commit()

        # Alerts (and whatever clips they still have) past the retention window.
        alert_cutoff = now - timedelta(days=alert_retention_days)
        old_alerts = (await session.scalars(select(Alert).where(Alert.started_at < alert_cutoff))).all()
        for alert in old_alerts:
            clips = (await session.scalars(select(VideoClip).where(VideoClip.alert_id == alert.alert_id))).all()
            for clip in clips:
                await _delete_clip(session, clip, clear_alert_url=False)  # the alert itself is about to go too
                deleted_clips += 1
            await session.delete(alert)  # cascades to this alert's AlertEvent rows
            deleted_alerts += 1
        await session.commit()

    if deleted_clips or deleted_alerts:
        logger.info("Retention sweep deleted %d clip(s) and %d old alert(s)", deleted_clips, deleted_alerts)
    return {"clips": deleted_clips, "alerts": deleted_alerts}


async def retention_loop(
    session_factory: async_sessionmaker, alert_retention_days: float, interval_seconds: int = 3600
) -> None:
    while True:
        try:
            await run_retention_sweep(session_factory, alert_retention_days)
        except Exception:
            logger.exception("Retention sweep failed")
        await asyncio.sleep(interval_seconds)

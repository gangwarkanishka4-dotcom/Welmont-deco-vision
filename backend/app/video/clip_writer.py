"""Writes an incident clip: RingBuffer pre-roll (last VIDEO_BUFFER_SECONDS)
+ a live post-roll tail, muxed into one mp4 file per alert. Runs as a
fire-and-forget background task so it never blocks alert creation.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import imageio_ffmpeg
import numpy as np

from app.database import AsyncSessionLocal
from app.models.alert import Alert
from app.models.video_clip import VideoClip
from app.video.ring_buffer import RingBuffer

logger = logging.getLogger(__name__)


def _encode_h264(frames: list[np.ndarray], fps: int, file_path: Path) -> None:
    """Encode raw BGR frames straight to H.264/yuv420p via ffmpeg.

    Real bug found live (2026-09-15): this used to go through
    cv2.VideoWriter with fourcc "mp4v", which — absent the (unlicensed,
    not installed) OpenH264 DLL this machine's OpenCV/FFmpeg build needs
    for real H.264 — silently falls back to the old MPEG-4 Part 2 codec
    ("FMP4"). That file is a perfectly valid, OpenCV-readable video, which
    is exactly why the bug went unnoticed here — it just isn't a codec any
    browser's native <video> element can decode, so every incident clip
    loaded as a blank/broken player on the dashboard. `imageio-ffmpeg`
    bundles a static ffmpeg binary with libx264 built in, sidestepping the
    missing system codec entirely — no separate ffmpeg install needed.
    `-pix_fmt yuv420p` (browsers can't reliably decode libx264's default
    yuv444p) and `-movflags +faststart` (moves the moov atom to the front
    so playback can start before the whole file downloads) are both
    required for this to actually play in a browser, not just exist."""
    height, width = frames[0].shape[:2]
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(file_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    for frame in frames:
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise RuntimeError(f"ffmpeg encode failed (exit {proc.returncode}): {stderr[-2000:]}")


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
            raw_frames = [buffered.frame for buffered in frames]
            await asyncio.to_thread(_encode_h264, raw_frames, self.fps, file_path)

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

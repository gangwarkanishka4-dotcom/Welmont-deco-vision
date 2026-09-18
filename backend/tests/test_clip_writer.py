"""_encode_h264 (2026-09-15): incident clips used to go through
cv2.VideoWriter with fourcc "mp4v", which silently falls back to the
browser-incompatible MPEG-4 Part 2 codec ("FMP4") on a machine without the
OpenH264 DLL — a perfectly valid, OpenCV-readable file that no browser's
<video> element can actually play. This drives the real ffmpeg subprocess
(via imageio-ffmpeg) end to end and confirms the output is genuinely H.264,
not just a file that exists."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.video.clip_writer import _encode_h264


def _fourcc_of(path) -> str:
    cap = cv2.VideoCapture(str(path))
    try:
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        return "".join(chr((fourcc_int >> (8 * i)) & 0xFF) for i in range(4))
    finally:
        cap.release()


def test_encode_h264_produces_a_browser_playable_codec(tmp_path):
    frames = [np.full((48, 64, 3), i * 20, dtype=np.uint8) for i in range(6)]
    out_path = tmp_path / "clip.mp4"

    _encode_h264(frames, fps=12, file_path=out_path)

    assert out_path.exists()
    assert out_path.stat().st_size > 0
    # avc1 is the fourcc H.264-in-MP4 reports as — explicitly NOT mp4v/FMP4,
    # the old codec that browsers can't decode.
    fourcc = _fourcc_of(out_path)
    assert fourcc in ("avc1", "h264", "H264")

    cap = cv2.VideoCapture(str(out_path))
    try:
        assert cap.isOpened()
        assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == len(frames)
        ok, frame = cap.read()
        assert ok
        assert frame.shape[:2] == (48, 64)
    finally:
        cap.release()


def test_encode_h264_raises_on_ffmpeg_failure(tmp_path):
    # An empty frame list has no width/height to size the encode with —
    # exercising the failure path rather than assuming ffmpeg always succeeds.
    with pytest.raises((IndexError, RuntimeError)):
        _encode_h264([], fps=12, file_path=tmp_path / "clip.mp4")

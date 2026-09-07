"""Rolling in-memory frame buffer: always holds the last VIDEO_BUFFER_SECONDS
of raw frames for one camera. When an alert fires, ClipWriter drains this
buffer as the "pre-roll" and keeps recording live frames afterward, so the
saved clip covers [confirmed_at - VIDEO_BUFFER_SECONDS, confirmed_at + tail]."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class BufferedFrame:
    frame: np.ndarray
    timestamp: float


class RingBuffer:
    def __init__(self, buffer_seconds: int, fps: int) -> None:
        maxlen = max(1, buffer_seconds * fps)
        self._frames: deque[BufferedFrame] = deque(maxlen=maxlen)

    def push(self, frame: np.ndarray, timestamp: float | None = None) -> None:
        self._frames.append(BufferedFrame(frame=frame.copy(), timestamp=timestamp or time.time()))

    def snapshot(self) -> list[BufferedFrame]:
        """A point-in-time copy of everything currently buffered, oldest first."""
        return list(self._frames)

    def latest(self) -> BufferedFrame | None:
        return self._frames[-1] if self._frames else None

    def __len__(self) -> int:
        return len(self._frames)

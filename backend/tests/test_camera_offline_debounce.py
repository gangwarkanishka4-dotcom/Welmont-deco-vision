"""Camera offline debounce (2026-09-15): CameraWorker.run() used to mark a
camera OFFLINE (flipping the dashboard badge) on literally every single
failed frame read, even a one-frame blip that resolves a second later — a
dead `or True` made the intended is_stale() debounce check unconditional.
This RTSP-over-internet feed has routine multi-second blips that self-heal,
so this flapped constantly. A full run()-loop test would need to fake real
wall-clock timing (is_stale() reads time.time() internally), which is
fragile — this instead guards the specific regression class directly: the
offline-marking call must be conditioned on is_stale(), not unconditional."""
from __future__ import annotations

import inspect

from app.workers.pipeline import CameraWorker


def test_offline_marking_is_gated_on_staleness_not_unconditional():
    source = inspect.getsource(CameraWorker.run)
    # The exact bug: `if self.monitor.is_stale(now) or True:` — an `or True`
    # (or equivalent always-true tautology) anywhere near the offline check
    # would silently defeat the debounce again.
    assert "or True" not in source
    assert "if self.monitor.is_stale(now):" in source

"""Structured logging setup. Every log line carries a timestamp, module, and
level so the console output matches the format requested in the spec:
[13:38:41] Camera Class-2 frame processed
"""
from __future__ import annotations

import logging
import sys


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt="[%(asctime)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # noisy third-party loggers — these emit a DEBUG line per SQL statement /
    # per-request access log, which drowns out the actually useful debug
    # output (per-track classification, state transitions, camera worker
    # timing) that DEBUG_MODE is meant to surface.
    logging.getLogger("ultralytics").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

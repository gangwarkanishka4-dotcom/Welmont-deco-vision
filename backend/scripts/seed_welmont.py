"""One-off seed script for the two cameras shared for Welmont Lalkothi,
Jaipur. Credentials are encrypted with CREDENTIAL_ENCRYPTION_KEY before being
written to the database — never stored or logged in plaintext.

Reads the real camera credentials from environment variables rather than
hardcoding them here, since this file is committed to source control:
    WELMONT_RTSP_HOST, WELMONT_RTSP_USERNAME, WELMONT_RTSP_PASSWORD
(add them to your local .env — already gitignored — or export them in your
shell before running).

Run after `alembic upgrade head`:
    python -m scripts.seed_welmont
"""
from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv

from app.core.crypto import encrypt_secret
from app.database import AsyncSessionLocal
from app.models.camera import Camera
from app.models.camera_configuration import CameraConfiguration
from app.models.classroom import Classroom

load_dotenv()  # picks up WELMONT_RTSP_* from .env if not already set in the shell

RTSP_HOST = os.environ.get("WELMONT_RTSP_HOST", "")
RTSP_USERNAME = os.environ.get("WELMONT_RTSP_USERNAME", "")
RTSP_PASSWORD = os.environ.get("WELMONT_RTSP_PASSWORD", "")
RTSP_PATH = os.environ.get("WELMONT_RTSP_PATH", "/Streaming/Channels/101")

def _pt(x: float, y: float) -> dict:
    return {"x": x, "y": y}


# ROI (full classroom, corner-to-corner) and gate line (entrance, with the
# "inside" side marked) as configured on-site 2026-09-08 via the dashboard's
# Camera Management -> Configure modal, in each camera's true native pixel
# space (1280x720 — the actual RTSP stream resolution; the ROI editor used
# to scale clicks against Camera.resolution_width/height, which defaulted to
# 1920x1080 and was never reconciled against the real stream, so every point
# below is that original on-site polygon divided by 1.5 to correct for it —
# see the 2026-09-12 ROI-shift bug investigation). Committed here as the
# default so a DB reset / reseed restores the real on-site layout instead of
# coming back up with no ROI/gate at all.
CAMERAS = [
    {
        "name": "Basement 1",
        "port": 556,
        # Top edge nudged down at x~600 (2026-09-12): a wall poster up there
        # (a cartoon figure on an educational display) intermittently scores
        # just above the detector threshold and gets picked up as a phantom
        # person — since it's on the wall, not real floor space, excluding
        # it from the ROI is the correct fix (no confidence threshold can
        # cleanly separate it from genuine hard-to-detect adults).
        "roi": [
            _pt(240.42933810375672, 135.5732484076433),
            _pt(599.9284436493739, 175.0),
            _pt(1197.567084078712, 206.656050955414),
            _pt(329.73166368515206, 713.4076433121019),
        ],
        "gate_line": [
            _pt(938.8193202146692, 319.0127388535032),
            _pt(1085.3667262969589, 429.0764331210191),
        ],
        "gate_inside_point": _pt(920.5008944454495, 362.5796178343949),
    },
    {
        "name": "Basement 2",
        "port": 553,
        # Redrawn 2026-09-12 directly against a real 1280x720 frame after
        # the resolution-mismatch bug above was fixed (the previous points
        # here were rescaled from the buggy 1920x1080-space save, but were
        # replaced with a fresh full-room polygon at the user's request).
        # First attempt cut off the low table/mat area where an adult
        # regularly sits (confirmed live: her track stayed in_roi=False
        # continuously, not a momentary edge case) — bottom edge pushed
        # further down to cover that with margin.
        "roi": [
            _pt(140, 130),
            _pt(1050, 15),
            _pt(1170, 250),
            _pt(990, 660),
            _pt(160, 660),
        ],
        "gate_line": [
            _pt(222.1109123434705, 353.4076433121019),
            _pt(336.60107334525937, 316.71974522292996),
        ],
        "gate_inside_point": _pt(751.0554561717353, 452.00636942675163),
    },
]


async def main() -> None:
    if not (RTSP_HOST and RTSP_USERNAME and RTSP_PASSWORD):
        sys.exit(
            "Missing camera credentials. Set WELMONT_RTSP_HOST, WELMONT_RTSP_USERNAME, "
            "and WELMONT_RTSP_PASSWORD (in your local .env or shell environment) before running this script."
        )

    async with AsyncSessionLocal() as session:
        classroom = Classroom(name="Welmont Lalkothi, Jaipur", location="Welmont Lalkothi, Jaipur")
        session.add(classroom)
        await session.flush()

        for entry in CAMERAS:
            camera = Camera(
                name=entry["name"],
                classroom_id=classroom.id,
                rtsp_host=RTSP_HOST,
                rtsp_port=entry["port"],
                rtsp_path=RTSP_PATH,
                rtsp_username=RTSP_USERNAME,
                rtsp_password_encrypted=encrypt_secret(RTSP_PASSWORD),
                fps=25,
                enabled=True,
                # Must match the true RTSP stream resolution, not the
                # Camera model's 1920x1080 default — see the ROI comment
                # above. The ROI editor scales clicks against this field, so
                # a mismatch here silently reintroduces that bug.
                resolution_width=1280,
                resolution_height=720,
            )
            session.add(camera)
            await session.flush()
            session.add(
                CameraConfiguration(
                    camera_id=camera.id,
                    roi_polygon=entry.get("roi", []),
                    gate_line=entry.get("gate_line", []),
                    gate_inside_point=entry.get("gate_inside_point"),
                )
            )
            print(f"Seeded camera '{entry['name']}' -> id={camera.id}")

        await session.commit()

    print("Done. ROI + calibration are unset — configure them from the dashboard's Camera Management page before relying on supervision alerts for these two cameras.")


if __name__ == "__main__":
    asyncio.run(main())

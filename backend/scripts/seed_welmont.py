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
# Camera Management -> Configure modal, in each camera's native pixel space
# (1920x1080). Committed here as the default so a DB reset / reseed restores
# the real on-site layout instead of coming back up with no ROI/gate at all.
CAMERAS = [
    {
        "name": "Basement 1",
        "port": 556,
        "roi": [
            _pt(65.25939177101968, 158.64649681528664),
            _pt(996.0644007155635, 69.21974522292993),
            _pt(1727.6565295169946, 640.1751592356688),
            _pt(322.8622540250447, 1070.1114649681529),
        ],
        "gate_line": [
            _pt(1408.2289803220037, 478.5191082802548),
            _pt(1628.0500894454383, 643.6146496815287),
        ],
        "gate_inside_point": _pt(1380.7513416815743, 543.8694267515923),
    },
    {
        "name": "Basement 2",
        "port": 553,
        "roi": [
            _pt(92.73703041144901, 344.3789808917197),
            _pt(494.59749552772814, 1049.4745222929937),
            _pt(1772.3076923076924, 272.1496815286624),
            _pt(944.5438282647585, 52.02229299363058),
        ],
        "gate_line": [
            _pt(333.1663685152057, 530.1114649681529),
            _pt(504.9016100178891, 475.0796178343949),
        ],
        "gate_inside_point": _pt(1126.5831842576029, 678.0095541401274),
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

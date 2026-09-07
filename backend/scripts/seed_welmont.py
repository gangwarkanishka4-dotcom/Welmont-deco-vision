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

CAMERAS = [
    {"name": "Basement Class 1", "port": 556},
    {"name": "Basement Class 2", "port": 553},
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
            session.add(CameraConfiguration(camera_id=camera.id))
            print(f"Seeded camera '{entry['name']}' -> id={camera.id}")

        await session.commit()

    print("Done. ROI + calibration are unset — configure them from the dashboard's Camera Management page before relying on supervision alerts for these two cameras.")


if __name__ == "__main__":
    asyncio.run(main())

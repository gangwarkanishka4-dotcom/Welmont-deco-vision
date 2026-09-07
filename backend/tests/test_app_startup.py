"""End-to-end smoke test for app startup/shutdown: real FastAPI lifespan,
real SQLite DB, real event bus / alert manager / websocket manager wiring —
only the heavy YOLO/pose/classifier model loads are stubbed out (no GPU/model
weights available in this environment), so this exercises the actual
integration path (DB table creation via ORM metadata, camera worker registry,
retention loop, router registration) rather than mocking business logic."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import models  # noqa: F401 — registers all ORM models on Base.metadata
from app.database import Base, engine


class _FakeDetector:
    def warmup(self):
        pass

    def detect(self, frame):
        return []


class _FakeClassifier:
    def classify(self, *args, **kwargs):
        raise NotImplementedError


@pytest.fixture
async def prepared_db():
    # Uses app.database's actual module-level engine (set up from
    # DATABASE_URL=sqlite+aiosqlite:///:memory: in conftest.py) so the tables
    # created here are visible to the same connection pool the app code uses
    # — a separate throwaway engine would create tables in a different
    # in-memory database instance.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def test_app_starts_and_stops_cleanly(monkeypatch, prepared_db):
    import app.main as main_module

    monkeypatch.setattr(main_module, "build_detector", lambda settings: _FakeDetector())
    monkeypatch.setattr(main_module, "build_classifier", lambda settings: _FakeClassifier())
    monkeypatch.setattr(main_module, "build_pose_estimator", lambda settings: None)

    with TestClient(main_module.app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        response = client.get("/api/cameras")
        assert response.status_code == 200
        assert response.json() == []

        response = client.get("/api/classrooms")
        assert response.status_code == 200
        assert response.json() == []


def test_classroom_and_camera_crud_flow(monkeypatch, prepared_db):
    import app.main as main_module

    monkeypatch.setattr(main_module, "build_detector", lambda settings: _FakeDetector())
    monkeypatch.setattr(main_module, "build_classifier", lambda settings: _FakeClassifier())
    monkeypatch.setattr(main_module, "build_pose_estimator", lambda settings: None)

    with TestClient(main_module.app) as client:
        classroom_resp = client.post("/api/classrooms", json={"name": "Class 2", "location": "Welmont Lalkothi, Jaipur"})
        assert classroom_resp.status_code == 201
        classroom_id = classroom_resp.json()["id"]

        # enabled=False so no real RTSP connection attempt happens during this test
        camera_resp = client.post(
            "/api/cameras",
            json={
                "name": "Basement Class 1",
                "classroom_id": classroom_id,
                "rtsp_host": "192.0.2.10",
                "rtsp_port": 556,
                "rtsp_path": "/Streaming/Channels/101",
                "rtsp_username": "admin",
                "rtsp_password": "test-password-123",
                "enabled": False,
            },
        )
        assert camera_resp.status_code == 201
        camera_json = camera_resp.json()
        assert "rtsp_password" not in camera_json
        assert "rtsp_password_encrypted" not in camera_json
        camera_id = camera_json["id"]

        roi_resp = client.post(
            f"/api/cameras/{camera_id}/roi",
            json={"roi": [{"x": 0, "y": 0}, {"x": 100, "y": 0}, {"x": 100, "y": 100}, {"x": 0, "y": 100}]},
        )
        assert roi_resp.status_code == 200
        assert len(roi_resp.json()["roi"]) == 4

        list_resp = client.get("/api/cameras")
        assert len(list_resp.json()) == 1

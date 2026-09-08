# Classroom Supervision & Intrusion Detection System

A real-time computer-vision system that watches classroom camera feeds,
detects whether a supervising adult is present whenever children are in the
room, and raises an alert (dashboard + physical buzzer/relay) within seconds
of confirming a classroom is unsupervised.

This is not a UI mock. The CV pipeline (YOLO detection → ByteTrack tracking →
multi-signal adult/child classification → per-camera ROI/calibration →
supervision state machine → event bus → WebSocket → alert engine → buzzer →
clip recording) is fully implemented and unit/integration tested. What *is*
honestly a placeholder, and clearly marked as such below, is the trained
adult/child appearance model — there is no labeled classroom dataset to
train one on yet, so the system runs on a documented geometry+pose heuristic
fallback until you supply one (§ "Training a custom adult/child model").

## Contents

- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Quick start (Docker)](#quick-start-docker)
- [Running locally without Docker](#running-locally-without-docker)
- [Connecting an RTSP camera](#connecting-an-rtsp-camera)
- [Configuring the classroom ROI](#configuring-the-classroom-roi)
- [Calibrating perspective](#calibrating-perspective)
- [Training a custom adult/child model](#training-a-custom-adultchild-model)
- [Connecting an ESP32 relay/buzzer](#connecting-an-esp32-relaybuzzer)
- [Running with GPU](#running-with-gpu)
- [Running the tests](#running-the-tests)
- [Performance tuning](#performance-tuning)
- [Privacy](#privacy)
- [Known limitations / what's next](#known-limitations--whats-next)

## Architecture

```
Camera (RTSP) ──▶ CameraWorker (asyncio task, one per camera)
                     │
                     ├─ YOLODetector           (throttled to INFERENCE_FPS)
                     ├─ ByteTrackTracker        (every processed frame)
                     ├─ AgeGroupClassifier      (heuristic or trained model,
                     │   + RollingClassificationHistory   throttled further)
                     ├─ CameraCalibration (ROI + perspective)
                     └─ ClassroomMonitor ──▶ SupervisionStateMachine
                                                │
                                                ▼
                                            EventBus (in-process, or Redis
                                            for a split API/worker deployment)
                                                │
                        ┌───────────────────────┼───────────────────────┐
                        ▼                       ▼                       ▼
                  AlertManager            ConnectionManager         (future
              (DB + dedup + buzzer)         (WebSocket → React)     consumers)
                        │
                        ├─ AlertOutput (Mock / NetworkRelay / ESP32Relay)
                        └─ ClipWriter (RingBuffer pre-roll + live tail → mp4)
```

Every arrow above is a real interface (`app/cv/detector/base.py`,
`app/cv/tracker/base.py`, `app/cv/classifier/base.py`,
`app/hardware/base.py`) — swapping any implementation (e.g. a trained
adult/child model, a different tracker, a different relay) never requires
touching the rest of the pipeline.

## Project structure

```
classroom-monitor/
├── backend/
│   ├── app/
│   │   ├── api/                 REST routes (cameras, alerts, classrooms)
│   │   ├── models/               SQLAlchemy ORM models
│   │   ├── schemas/               Pydantic request/response schemas
│   │   ├── cv/
│   │   │   ├── detector/          PersonDetector interface + YOLO impl
│   │   │   ├── tracker/           PersonTracker interface + ByteTrack impl
│   │   │   ├── classifier/        AgeGroupClassifier: heuristic + ML + history
│   │   │   ├── pose/              PoseEstimator interface + YOLO-pose impl
│   │   │   └── calibration/       ROI polygon + perspective calibration + overlay
│   │   ├── supervision/          SupervisionStateMachine + ClassroomMonitor
│   │   ├── alerts/                AlertManager (dedup, DB, buzzer, media)
│   │   ├── hardware/              AlertOutput: Mock / NetworkRelay / ESP32
│   │   ├── events/                Async event bus (in-process + Redis)
│   │   ├── websocket/             ConnectionManager + /ws/events route
│   │   ├── video/                 RingBuffer, ClipWriter, retention sweep
│   │   ├── workers/                CameraWorker pipeline + registry + bootstrap
│   │   ├── main.py                Default single-process entrypoint
│   │   └── worker_main.py         Optional split-process CV worker entrypoint
│   ├── alembic/                   DB migrations
│   ├── tests/                     pytest suite (see below)
│   ├── scripts/seed_welmont.py    Example seed data
│   └── requirements.txt
├── frontend/                      React + JS/JSX + Tailwind dashboard
├── models/                        Model weights (mounted volume, see models/README.md)
├── docker/                        Dockerfiles + nginx config
├── docker-compose.yml
└── .env.example
```

## Quick start (Docker)

```bash
cp .env.example .env
# generate a real credential-encryption key and put it in .env:
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# then edit .env: set CREDENTIAL_ENCRYPTION_KEY to the value printed above

# place model weights (see models/README.md) — at minimum models/yolov8n.pt
docker compose up --build
```

- Backend API: http://localhost:8000 (docs at `/docs`)
- Frontend: http://localhost:3000
- Postgres: localhost:5432, Redis: localhost:6379

The backend container runs `alembic upgrade head` automatically before
starting `uvicorn`, so the schema is created on first boot.

## Running locally without Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Postgres must be reachable at DATABASE_URL in .env (or run `docker compose up postgres redis -d`)
cp ../.env.example ../.env   # edit as needed; backend reads .env from its own working directory too
alembic upgrade head

uvicorn app.main:app --reload
```

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

## Connecting an RTSP camera

Camera credentials are stored as **separate encrypted fields** (host, port,
path, username, password), never as one raw `rtsp://user:pass@host` string —
a password containing `@` or `:` makes a single URL ambiguous. Add a camera
via the dashboard's Cameras page, or directly:

```bash
curl -X POST http://localhost:8000/api/cameras \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Basement Class 1",
    "classroom_id": "<classroom-id>",
    "rtsp_host": "192.168.1.60",
    "rtsp_port": 556,
    "rtsp_path": "/Streaming/Channels/101",
    "rtsp_username": "admin",
    "rtsp_password": "your-password",
    "fps": 25,
    "enabled": true
  }'
```

Use **Test Camera** (`POST /api/cameras/{id}/test`) to confirm connectivity
before enabling it for supervision. Two example cameras for this exact
deployment (Welmont Lalkothi, Jaipur — "Basement Class 1" / "Basement Class
2") are pre-wired in `backend/scripts/seed_welmont.py`; run it after
`alembic upgrade head`. It reads the real camera credentials from
`WELMONT_RTSP_HOST` / `WELMONT_RTSP_USERNAME` / `WELMONT_RTSP_PASSWORD`
(set them in your local `.env` — never committed) rather than hardcoding
them:

```bash
cd backend && python -m scripts.seed_welmont
```

That script encrypts the password before writing it to the database — it is
never logged or returned by the API afterward.

## Configuring the classroom ROI

Open the camera's configuration screen (Cameras → row → Configure ROI). Only
people whose **foot point** (bottom-center of their bounding box — the
point where they contact the floor, not the box centroid) falls inside this
polygon count toward supervision. Click points on the live/still frame to
build the polygon, then **Save ROI** — this calls:

```
POST /api/cameras/{id}/roi
{"roi": [{"x": 120, "y": 80}, {"x": 640, "y": 80}, {"x": 640, "y": 460}, {"x": 120, "y": 460}]}
```

Points are in the camera's native pixel coordinates (`resolution_width` /
`resolution_height` on the Camera record) — the frontend scales displayed
canvas coordinates to native resolution before submitting. If no ROI is
configured yet, the system treats the whole frame as the classroom (fails
open on setup, never fails closed on supervision).

## Calibrating perspective

A single global "person is X pixels tall = adult" threshold breaks under
perspective — someone near the camera is larger on-screen than someone far
away, at the same real-world height. Instead, calibrate a few reference
points: at a given row of the frame (`pixel_y`), how tall (in pixels) does an
average adult appear (`reference_height_px`)? Two points (near and far) are
enough for linear interpolation across the frame; more points improve
accuracy for cameras with strong perspective distortion.

```
POST /api/cameras/{id}/calibration
{
  "calibration_points": [
    {"pixel_y": 200, "reference_height_px": 180},
    {"pixel_y": 600, "reference_height_px": 420}
  ],
  "adult_height_ratio": 0.85,
  "child_height_ratio": 0.60
}
```

`adult_height_ratio` / `child_height_ratio` control how the classifier maps
"detected height ÷ expected adult height at that row" into an adult-likeness
score (`app/cv/classifier/heuristic_classifier.py`) — tune them if you see
systematic over/under-classification for a specific camera angle.

## Training a custom adult/child model

The heuristic fallback (calibrated geometry + pose proportions) works
without any training data, but a model trained on your own classroom
footage will be more accurate. The interface is `AgeGroupClassifier`
(`app/cv/classifier/base.py`); `MLAgeClassifier`
(`app/cv/classifier/ml_classifier.py`) already implements it and fuses a
trained model's output with the heuristic fallback so accuracy degrades
gracefully rather than breaking outright.

1. **Collect crops**: for labeled training data, save cropped person images
   from `TrackedEvent`-adjacent frames (or run the detector standalone over
   recorded clips) and label each crop `adult` / `child`.
2. **Train** a binary classifier (any framework) that outputs
   `P(adult)` for a fixed-size RGB crop. `MLAgeClassifier` defaults to a
   224×224 input with ImageNet normalization (typical torchvision
   classifier-head convention) — adjust `_run_model` in
   `ml_classifier.py` if your training pipeline differs.
3. **Export** to `.pt` (a `torch.load`-able module in eval mode) or `.onnx`.
4. **Deploy**: place the file under `models/`, set `AGE_MODEL=models/your_model.onnx`
   (or `.pt`) in `.env`, restart the backend. No other code changes needed —
   `app/cv/factory.py` picks `MLAgeClassifier` automatically whenever
   `AGE_MODEL` is non-empty.

## Connecting an ESP32 relay/buzzer

Set `ALERT_OUTPUT_DRIVER=esp32` and `RELAY_BASE_URL=http://<esp32-ip>` in
`.env`. `ESP32Relay` (`app/hardware/esp32_relay.py`) calls `GET
{RELAY_BASE_URL}/buzzer/on` when an alert becomes ACTIVE and `GET
{RELAY_BASE_URL}/buzzer/off` when it resolves, with retry/backoff
(`RELAY_MAX_RETRIES`, `RELAY_TIMEOUT_SECONDS`).

Minimal ESP32 (Arduino core) sketch sketch outline:

```cpp
#include <WiFi.h>
#include <WebServer.h>
#define RELAY_PIN 5

WebServer server(80);

void setup() {
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);
  WiFi.begin("<ssid>", "<password>");
  while (WiFi.status() != WL_CONNECTED) delay(200);

  server.on("/buzzer/on", []() { digitalWrite(RELAY_PIN, HIGH); server.send(200, "text/plain", "on"); });
  server.on("/buzzer/off", []() { digitalWrite(RELAY_PIN, LOW); server.send(200, "text/plain", "off"); });
  server.begin();
}

void loop() { server.handleClient(); }
```

For a relay board with its own HTTP API instead, use
`ALERT_OUTPUT_DRIVER=network_relay` (`app/hardware/network_relay.py`, POSTs
to `{RELAY_BASE_URL}/relay/on` / `/relay/off` — edit `trigger_path`/
`clear_path` to match your board). `ALERT_OUTPUT_DRIVER=mock` (default)
requires no hardware and logs `[MOCK BUZZER] TRIGGER/CLEAR` — use this for
development.

## Running with GPU

Set `DEVICE=auto` (default) in `.env` — `app/core/device.py` checks
`torch.cuda.is_available()` at model-load time and uses `cuda:0`
automatically if present, falling back to CPU otherwise. To force one or the
other, set `DEVICE=cpu` or `DEVICE=cuda:0`.

With Docker, uncomment the `deploy.resources.reservations.devices` block for
the `backend` service in `docker-compose.yml` (requires the [NVIDIA
Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
on the host) and make sure the installed `torch`/`torchvision` build matches
your CUDA version (the pinned versions in `requirements.txt` default to a
CPU-compatible build — reinstall with the correct `--index-url` from
[pytorch.org](https://pytorch.org/get-started/locally/) for your CUDA
version if using GPU).

## Running the tests

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install pytest pytest-asyncio sqlalchemy aiosqlite asyncpg pydantic pydantic-settings python-dotenv cryptography httpx fastapi
PYTHONPATH=. pytest tests/ -v
```

This test suite runs against real SQLite (in-memory) databases, the real
`MockBuzzer`, the real `EventBus`, and the real FastAPI app lifespan — no
CV/torch/ultralytics install is required for these tests, since the
supervision state machine, alert dedup logic, and app wiring have no heavy
model dependency. It covers every case from the spec:

| Test | Case |
|---|---|
| `test_supervision_state_machine.py::test_case1_*` | Adult + children → SUPERVISED |
| `test_case2_*` | Children only, briefly (< grace period) → no alert |
| `test_case3_*` | Children only, past the full delay → alert confirmed |
| `test_case4_*` | Adult returns → auto-resolve |
| `test_case5_*` | Adult briefly occluded → no alert |
| `test_classroom_monitor.py::test_camera_offline_*` | Camera offline ≠ unsupervised |
| `test_case8_*` | Multiple classrooms tracked independently |
| `test_alert_manager.py::test_dedup_*` | One incident = one alert row, no re-firing |
| `test_app_startup.py` | Full FastAPI lifespan + DB + camera CRUD + ROI endpoint |

**This has also been run live** against the two real Welmont Lalkothi RTSP
cameras (CPU-only, no GPU) — both streams opened successfully, both age/child
counts and the supervision state (`EMPTY`, correctly, for an unoccupied room)
came through over `/ws/events` in real time, and `GET /api/cameras`
correctly flipped to `status: "ONLINE"`. Measured on that run: ~6–8 FPS
effective per camera with two cameras running concurrently on CPU, ~120–180ms
YOLOv8n inference latency per frame at 1920×1080. That's below the
`INFERENCE_FPS=12` target because two cameras are sharing one CPU-bound
detector instance — see "Performance tuning" below, and expect meaningfully
better throughput on GPU or with one camera per process.

## Performance tuning

- `INFERENCE_FPS` — how often detection+tracking actually runs, independent
  of camera FPS. A 25 FPS camera doesn't need 25 YOLO calls/sec; 10–15 is
  usually enough for classroom-scale movement.
- `CLASSIFICATION_EVERY_N_DETECT` — classification (the most expensive
  per-track step once pose estimation is involved) runs once every N
  detection cycles; the rolling window absorbs the gap.
- `TRACK_TIMEOUT_SECONDS` — how long a track survives occlusion before
  ByteTrack drops its ID.
- Debug mode (`DEBUG_MODE=true`) logs per-camera FPS, inference latency,
  track count, and classification confidences — use it to tune the above
  against your actual hardware rather than guessing.
- GPU vs CPU: see above. CPU-only YOLOv8n on a modern multi-core CPU
  typically handles a couple of cameras at 10 FPS; beyond that, GPU or a
  smaller/quantized model becomes necessary.

## Privacy

- No facial recognition, no name-based identity — only a per-session
  `track_id` (an arbitrary integer) + age-group label (`ADULT`/`CHILD`/
  `UNKNOWN`) are ever used, and only transiently in-memory during tracking.
- RTSP credentials are encrypted at rest (Fernet, `CREDENTIAL_ENCRYPTION_KEY`)
  and never returned by the API (`CameraOut` excludes both the plaintext and
  encrypted password fields).
- Incident clips are retained for `VIDEO_RETENTION_DAYS` (default 7) and
  automatically deleted by a background sweep (`app/video/retention.py`).

## Known limitations / what's next

Being direct about what's genuinely done vs. still open, rather than
overclaiming:

- **No authentication/authorization.** Every API endpoint is currently open.
  If you need this, it requires real design work (login flow, route
  protection, credential storage) — add it before exposing the API beyond a
  trusted network.
- **Split CV-worker/API deployment** (`app/worker_main.py` +
  `RedisEventBus`) is implemented for the event-bus/inference side, but
  camera CRUD/ROI/calibration/enable-disable and manual alert
  acknowledge/resolve still assume they're mutating an in-process
  `CameraWorkerRegistry` — in split mode those actions need to be routed to
  the worker process (e.g. via a Redis command channel), which is not yet
  wired up. The default single-process deployment (`app/main.py`, what
  `docker-compose.yml` runs) does not have this limitation and is the
  configuration this project was tested against.
- **No trained adult/child model ships with this repo** — see "Training a
  custom adult/child model" above. The heuristic fallback is real and
  functional, not a stub, but it will not match a model trained on your
  actual classroom footage.
- **The adult/child classification accuracy itself is still unvalidated
  against real supervision scenarios.** Live inference against the two real
  Welmont cameras confirms the pipeline runs end-to-end (detection, tracking,
  ROI, state machine, WebSocket, DB) on real RTSP video — but both rooms were
  empty during that run, so the heuristic classifier's actual adult-vs-child
  accuracy, and the supervision alert's real-world false-positive/negative
  rate, have not yet been observed with real people in frame. Configure ROI +
  calibration for these two cameras (see above) and observe a real
  supervised/unsupervised transition before trusting alerts from them.
- **No GPU was available where this was tested** — CPU-only numbers are in
  the paragraph above; a GPU should substantially raise the achievable FPS
  and camera count per process.

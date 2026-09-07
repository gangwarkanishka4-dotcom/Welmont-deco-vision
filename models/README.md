# Model weights

This directory is mounted into the backend container at `/app/models`
(see `docker-compose.yml`). It is not committed to source control — the
files are large binaries; download or train them, then place them here.

## Required

- **`yolov8n.pt`** — person detector (`PERSON_MODEL` in `.env`). Ultralytics
  will auto-download this on first run if it's missing and the container has
  internet access:
  ```bash
  python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
  ```
  Then copy the downloaded file here. For better accuracy at the cost of
  speed, swap in `yolov8s.pt` / `yolov8m.pt` (edit `PERSON_MODEL` in `.env`
  accordingly).

## Optional

- **`yolov8n-pose.pt`** — pose estimator (`POSE_MODEL`), used as one signal
  in the adult/child heuristic classifier. Same auto-download approach:
  ```bash
  python -c "from ultralytics import YOLO; YOLO('yolov8n-pose.pt')"
  ```
  Leave `POSE_MODEL` empty in `.env` to disable pose entirely — the
  classifier falls back to geometry-only scoring.

- **A trained adult/child classifier** (`AGE_MODEL`) — see the root
  `README.md` section "Training a custom adult/child model" for the export
  format (`.pt` or `.onnx`) and expected input contract. Until you have one,
  leave `AGE_MODEL` empty; the system runs on the geometry+pose heuristic
  fallback (`app/cv/classifier/heuristic_classifier.py`), which is fully
  functional but less accurate than a model trained on your own classroom
  footage.

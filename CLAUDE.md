# Project Context

## Goal
Extend demos/camera/videocamera.py to support Picamera2 (Raspberry Pi HQ Camera)
alongside the existing Qt6 QCamera backend (for USB/V4L2 cameras like Logitech C920).

## Hardware
- Raspberry Pi 5
- Raspberry Pi HQ Camera Module (CSI, via libcamera/Picamera2)
- Logitech C920 Pro webcam (USB, V4L2, works with Qt6 QCamera natively)

## Problem
Qt6 QMultimedia cannot see CSI cameras on Pi because they are libcamera-only
and do not expose a real V4L2 node. Qt6 GStreamer and FFmpeg backends both fail
with CSI cameras on RPi (confirmed broken through Qt 6.7+).

## Requirements

### Must have
- Keep QCamera path working for USB/V4L2 cameras (Logitech etc.)
- Add Picamera2 backend for CSI cameras (Pi HQ Camera Module)
- VideoCamera class must remain based on QCamera, not QLabel
- Selectable backend at runtime (e.g. --camera picamera2 vs --camera qt)
- frame_ready signal interface must be preserved for the CSI overlay in camera.py

### Nice to have
- Camera selection UI or CLI arg when multiple cameras are connected
- At startup, enumerate all available cameras across both backends:
    - Qt6 backend: QMediaDevices.videoInputs() → USB/V4L2 devices (e.g. Logitech)
    - Picamera2 backend: Picamera2.global_camera_info() → CSI devices (e.g. HQ Camera)
- Present a unified list to the user (dialog box or --list-cameras + --camera-index N)
- Graceful fallback: if selected backend not available, warn and try the other
- Selection should survive the demo's existing argparse/YAML config system

## Repo
https://github.com/eriklundh/pyespargos
Upstream: https://github.com/ESPARGOS/pyespargos

## venv
python3 -m venv .venv --system-site-packages
source .venv/bin/activate

## Key files to read first
- demos/camera/videocamera.py   — the class to extend
- demos/camera/camera.py        — how VideoCamera is used, signals consumed
- demos/common/                 — shared argparse/YAML config framework used by all demos

## Git Workflow

### Repository setup
- Origin: https://github.com/eriklundh/pyespargos (your fork)
- Upstream: https://github.com/ESPARGOS/pyespargos

### Branch strategy
All work goes on a feature branch, never on main:
  git checkout -b feature/picamera2-backend

Keep main in sync with upstream:
  git fetch upstream
  git checkout main
  git merge upstream/main

### Commit discipline
- One logical change per commit — never bundle unrelated changes
- Commit after each working step, not at end of session
- Always verify the code runs before committing

### Commit message format
Follow conventional commits style:

  <type>(<scope>): <short summary>

  <body — what changed and why, not how>

  <footer — references if relevant>

Types: feat, fix, refactor, docs, test, chore
Scope: videocamera, camera, qml, config

Examples:
  feat(videocamera): add list_all_cameras() enumerating Qt and Picamera2 devices
  feat(videocamera): add Picamera2VideoCamera class with QCamera-compatible interface
  feat(camera): add --camera-backend and --list-cameras CLI arguments
  feat(qml): branch CaptureSession/VideoOutput on backend type
  fix(videocamera): handle ImportError gracefully when picamera2 not installed
  docs(camera): update CLAUDE.md with final implementation notes

### Planned commit sequence
Claude Code should commit in this order, verifying at each step:
  1. chore: add CLAUDE.md and FINDINGS.md (already done)
  2. refactor(videocamera): extract _detect_backend() and list_all_cameras()
  3. feat(videocamera): add Picamera2VideoCamera class
  4. feat(videocamera): add make_video_camera() factory
  5. feat(camera): add --camera-backend and --list-cameras CLI args
  6. feat(camera): wire make_video_camera() factory and expose Qt properties
  7. feat(qml): add Picamera2 VideoOutput branch in CameraOverlay.qml
  8. fix: any fixes found during testing on Pi5 hardware

### Before each commit
  - Run: python -c "import demos.camera.videocamera" (import check)
  - Run the demo briefly to verify no regression on Qt/USB path
  - git diff to review what is actually being committed

### Pull request preparation
When ready for upstream PR:
  git fetch upstream
  git rebase upstream/main feature/picamera2-backend
  # Squash fixup commits if any, keep the logical step commits clean
  # Push to fork:
  git push origin feature/picamera2-backend

PR description should include:
  - Problem: Qt6 QMultimedia cannot enumerate libcamera CSI cameras on Pi
  - Solution: Picamera2VideoCamera subclass + factory + QML branch
  - Hardware tested on: Pi5 + HQ Camera Module + Logitech C920
  - Backwards compatible: Qt path unchanged, picamera2 optional import

## Headless smoke test (no display needed)

Uses Xvfb (install: `sudo apt-get install xvfb`). Both backends tested:

```bash
# Start virtual display
Xvfb :99 -screen 0 1920x1080x24 &
XVFB_PID=$!
sleep 1

cd demos/camera
source /home/eriklundh/pyespargos/.venv/bin/activate

# Qt backend
timeout 10 env DISPLAY=:99 QT_QPA_PLATFORM=xcb \
    python camera.py --camera-backend qt -s 192.168.1.2

# Picamera2 backend
timeout 10 env DISPLAY=:99 QT_QPA_PLATFORM=xcb \
    python camera.py --camera-backend picamera2 -s 192.168.1.2

kill $XVFB_PID
```

Expected output for both (app runs until timeout kills it — exit code 0 = pass):
- Pool connects and identifies ESPARGOS board
- Qt path: `WARNING:root:VideoCamera: no formats available for device ''` — normal when no USB camera attached
- Picamera2 path: libcamera enumerates IMX477 sensor modes, `setFocusMode() is a no-op` warning fires
- Calibration completes (~196–197 clusters)
- `INFO:pyespargos.backlog:Started CSI backlog thread`
- App runs indefinitely (killed by timeout, not by a crash)

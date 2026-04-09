# Camera Demo

Overlays the WiFi spatial spectrum on a live camera feed.

## Camera Backends

Two backends are supported:

| Backend | Camera type | When to use |
|---------|-------------|-------------|
| `qt` (default) | USB / V4L2 cameras (e.g. Logitech C920) | Any platform with a standard webcam |
| `picamera2` | Raspberry Pi CSI cameras (e.g. HQ Camera Module via libcamera) | Raspberry Pi 4 / 5 with a CSI camera attached |

### Selecting a backend

```bash
# Qt backend (default — USB/V4L2 webcam)
python camera.py --camera-backend qt -s 192.168.1.2

# Picamera2 backend (Raspberry Pi CSI camera)
python camera.py --camera-backend picamera2 -s 192.168.1.2

# Auto-detect (tries Picamera2 on Raspberry Pi, falls back to Qt elsewhere)
python camera.py --camera-backend auto -s 192.168.1.2
```

### Listing available cameras

```bash
python camera.py --list-cameras
```

This prints all cameras found across both backends (Qt/V4L2 devices and Picamera2/CSI devices).

### Picamera2 requirements

The Picamera2 backend requires the `picamera2` package. On Raspberry Pi OS it is usually pre-installed system-wide. If not:

```bash
sudo apt install python3-picamera2
```

**Important — virtual environment must use `--system-site-packages`:**
`picamera2` is a system package and cannot be installed inside a normal isolated venv via `pip`. The venv must be created with `--system-site-packages` so it can see the system installation:

```bash
python3 -m venv .venv --system-site-packages
```

If you already have a venv without this flag, delete it and recreate it:

```bash
rm -rf .venv
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -e ".[demos]"   # reinstall pyespargos + demo deps
```

After recreating the venv, verify picamera2 is visible:

```bash
python -c "import picamera2; print('OK')"
```

## Shader Compilation

Before running the demo the fragment and vertex shaders must be compiled. The pre-compiled shaders found in the repository usually work fine.

If you need to recompile, use `compile_shader.sh` (Linux / macOS) or `compile_shader.bat` (Windows). You may need to adapt the path to `qsb` in the script.
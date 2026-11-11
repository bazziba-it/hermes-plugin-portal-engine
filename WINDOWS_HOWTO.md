# Portal Engine — Windows Setup Guide

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.8 – 3.12 | **Must be ≤3.12** for MediaPipe wheels |
| **Camera** | Built-in or USB | Webcam or capture card |
| **Projector** | Optional | For projection mapping |
| **Git** | Latest | For plugin install |

---

## 1. Install Python (≤3.12)

### Option A: Chocolatey (Recommended)
```powershell
# Install Chocolatey if not present
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Install Python 3.12
choco install python --version=3.12.9 -y
refreshenv
```

### Option B: Official Installer
1. Go to https://www.python.org/downloads/windows/
2. Download **Python 3.12.x** (not 3.13+)
3. Run installer → **Check "Add Python to PATH"**
4. Verify: `python --version` → `Python 3.12.x`

---

## 2. Install System Dependencies

### Visual C++ Redistributable (Required for OpenCV)
```powershell
choco install vcredist140 -y
# Or download from: https://aka.ms/vs/17/release/vc_redist.x64.exe
```

### NDI Runtime (For NDI Output to MadMapper/Resolume)
1. Go to https://ndi.video/for-developers/ndi-sdk/
2. Download **NDI 5 SDK** (Windows)
3. Run installer → installs NDI runtime + tools
4. Verify: `C:\Program Files\NDI\NDI 5 SDK\Bin\x64\NDIScan.exe` should run

### Spout (Already included via `spout-gl` pip package)
No separate install needed — `pip install spout-gl` handles it.

---

## 3. Install Python Dependencies

```powershell
# Upgrade pip
python -m pip install --upgrade pip

# Core dependencies
pip install mediapipe opencv-python numpy

# Output protocols
pip install spout-gl                    # Spout (Windows native)
pip install ndi-python                  # NDI (cross-platform)
# pip install pyvirtualcam               # Optional: virtual camera (needs OBS Virtual Cam)
```

**Verify:**
```powershell
python -c "import cv2; print('OpenCV:', cv2.__version__); import mediapipe as mp; print('MediaPipe:', mp.__version__); import spout; print('Spout: OK'); import ndi; print('NDI: OK')"
```

---

## 4. Install Hermes Agent

### Option A: Official Installer (when available)
Check https://hermes-agent.nousresearch.com/docs for Windows installer.

### Option B: From Source (Current)
```powershell
# Install uv
pip install uv

# Clone Hermes
git clone https://github.com/NousResearch/hermes-agent.git
cd hermes-agent

# Install in development mode
uv pip install -e .
# Or: pip install -e .

# Verify
hermes --version
```

---

## 5. Install Portal Engine Plugin

```powershell
# From local directory
hermes plugins install %USERPROFILE%\.hermes\plugins\portal_engine --enable

# Or from GitHub (when published)
# hermes plugins install github:yourname/portal-engine --enable

# Verify
hermes plugins doctor portal-engine
# Should show: 8 tools, 1 hook, 1 skill
```

---

## 6. Configure Hermes (Optional)

Edit `%USERPROFILE%\.hermes\profiles\default\config.yaml`:

```yaml
plugins:
  enabled:
    - portal-engine

portal_engine:
  default_camera_index: 0          # 0 = built-in, 1+ = USB
  effect_intensity: 1.0
  portal_width: 1920               # Your projector/screen resolution
  portal_height: 1080
  show_fps: true
  enable_projector_mode: true      # Fullscreen on secondary display
```

---

## 7. Usage Workflow

### Start Everything
```powershell
# 1. Start Hermes (in one terminal)
hermes

# 2. In agent chat, run:
# "Start the portal engine"
portal_start({"camera_index": 0, "effect_mode": "all", "fullscreen": true})

# 3. Calibrate for your projector/screen
# "Calibrate for my 1920x1080 projector"
portal_calibrate({"method": "auto", "screen_width": 1920, "screen_height": 1080})
# → Move hand to 4 screen corners (TL, TR, BR, BL)

# 4. Start output bridge (auto-detects Spout on Windows)
# "Start NDI/Spout output for MadMapper"
portal_syphon_start({"server_name": "PortalEngine", "protocol": "auto"})
```

### In MadMapper / Resolume / TouchDesigner

| App | How to Receive |
|-----|----------------|
| **MadMapper** | Media → Syphon/Spout/NDI → Select "PortalEngine" |
| **Resolume Arena** | Sources → Spout/NDI → "PortalEngine" |
| **TouchDesigner** | NDI In TOP / Spout In TOP → "PortalEngine" |
| **vMix** | Add Input → NDI → "PortalEngine" |
| **OBS** | NDI Source → "PortalEngine" (or Virtual Camera) |

### Map to Physical Frame
1. In MadMapper: Create **Quad** surface
2. Place quad over your physical picture frame area
3. Enable **Mesh Warping** for curved surfaces
4. Assign "PortalEngine" as texture
5. Fullscreen output to projector (Ctrl+F)

---

## 8. Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: mediapipe` | Python must be ≤3.12. Reinstall Python 3.12. |
| `ImportError: DLL load failed` | Install Visual C++ Redistributable (`vcredist140`). |
| `spout-gl` fails | Ensure Windows 10/11, update GPU drivers. |
| NDI not found | Install NDI 5 SDK from ndi.video. Restart after install. |
| Camera not detected | Try `camera_index: 1` or `2`. Check Device Manager. |
| Low FPS | Reduce `max_hands: 1`, lower resolution, close other apps. |
| Calibration off | Re-run with better lighting, hold hand steadier at corners. |
| Projector not fullscreen | Press `Ctrl+F` in MadMapper, check Windows display settings (Extend mode). |

---

## 9. Performance Tips

- **GPU**: Use dedicated GPU (NVIDIA/AMD) — set in Windows Graphics Settings
- **Camera**: 720p @ 30fps is sufficient; 1080p @ 60fps needs more CPU
- **Resolution**: Match `portal_width/height` to projector native resolution
- **Effects**: `effect_mode: "glowing_hands"` is lightest; `"all"` is heaviest

---

## 10. Uninstall

```powershell
hermes plugins disable portal-engine
hermes plugins remove portal-engine
Remove-Item "$env:USERPROFILE\.hermes\plugins\portal_engine" -Recurse -Force
Remove-Item "$env:USERPROFILE\.config\portal_engine" -Recurse -Force -ErrorAction SilentlyContinue
```

---

## Quick Reference Card

```powershell
# List cameras
hermes portal_engine list_cameras

# Start
hermes portal_engine start

# Calibrate (auto)
hermes portal_engine calibrate --method auto --width 1920 --height 1080

# Status
hermes portal_engine status

# Output bridge
hermes portal_engine syphon_start --server_name PortalEngine

# Stop all
hermes portal_engine syphon_stop
hermes portal_engine stop
```

---

*Portal Engine v0.1.0 — Windows Setup for NousResearch Hermes Agent Plugin Hackathon*
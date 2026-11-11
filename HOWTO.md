# Portal Engine — Step-by-Step How-To

## Prerequisites

| Platform | Python | Camera | MediaPipe |
|----------|--------|--------|-----------|
| Linux/macOS/Windows | **3.8–3.12** | Built-in or USB | ✅ `pip install mediapipe` |
| Android/Termux | 3.14 | ✅ | ❌ No ARM64 wheels yet |

**⚠️ Python 3.13+ not supported** — MediaPipe has no wheels for 3.13+. Use Python 3.12 or earlier.

---

## 1. Install Dependencies

### On Linux/macOS/Windows (Python ≤3.12)
```bash
# Core dependencies
pip install mediapipe opencv-python numpy

# Output protocols (choose based on platform)
pip install ndi-python                    # NDI (cross-platform, professional)
pip install spout-gl                      # Spout (Windows native, GPU sharing)
pip install syphon                        # Syphon (macOS only)
pip install pyvirtualcam                  # Virtual Camera (Linux, needs v4l2loopback)
```

### On Termux/Android (current limitation)
```bash
# OpenCV works via system package
pkg install python-numpy opencv-python

# Symlink into Hermes venv
ln -sf /data/data/com.termux/files/usr/lib/python3.14/site-packages/cv2 \
       /data/data/com.termux/files/usr/lib/hermes-agent/venv/lib/python3.14/site-packages/cv2
ln -sf /data/data/com.termux/files/usr/lib/python3.14/site-packages/numpy \
       /data/data/com.termux/files/usr/lib/hermes-agent/venv/lib/python3.14/site-packages/numpy

# MediaPipe: NOT YET AVAILABLE on Python 3.14 ARM64
# Plugin loads but portal_start will fail with "MediaPipe not installed"
```

---

## 2. Install the Plugin

```bash
# From local directory (development)
hermes plugins install ~/.hermes/plugins/portal_engine --enable

# Or from GitHub (when published)
hermes plugins install github:yourname/portal-engine --enable
```

### Verify Installation
```bash
hermes plugins list | grep portal
# Should show: portal-engine  enabled=True

hermes plugins doctor portal-engine
# Should show: OK - 8 tools, 1 hook, 1 skill
```

---

## 3. Enable the Plugin (if not auto-enabled)

```bash
# Add to your profile's config.yaml
cat >> ~/.hermes/profiles/default/config.yaml << 'EOF'
plugins:
  enabled:
    - portal-engine
EOF

# Restart Hermes or reload plugins
hermes plugins doctor portal-engine
```

---

## 4. List Available Cameras

```bash
# Via CLI
hermes portal_engine list_cameras

# Or via agent tool call
# portal_list_cameras(max_test=5)
```

**Expected output:**
```json
{
  "ok": true,
  "cameras": [
    {"index": 0, "width": 1280, "height": 720, "fps": 30.0, "backend": "V4L2"},
    {"index": 1, "width": 1920, "height": 1080, "fps": 30.0, "backend": "V4L2"}
  ],
  "count": 2
}
```

Pick your camera index (usually `0` for built-in).

---

## 5. Start the Portal Engine

### Basic Start (all effects, fullscreen, camera 0)
```bash
# CLI
hermes portal_engine start

# Agent
# portal_start({})
```

### Custom Configuration
```bash
# Agent only - full options
portal_start({
  "camera_index": 0,           // Camera to use
  "effect_mode": "all",        // glowing_hands | portal_rings | pass_through | particles | all
  "fullscreen": true,          // Fullscreen window
  "mirror": true,              // Mirror horizontally (natural for webcam)
  "detection_confidence": 0.7, // Hand detection threshold (0.1–1.0)
  "tracking_confidence": 0.5,  // Hand tracking threshold (0.1–1.0)
  "max_hands": 2               // Max simultaneous hands (1–4)
})
```

**What you'll see:** OpenCV window opens with live camera feed + hand tracking overlay.

---

## 6. Calibrate Camera → Screen/Projector

Calibration maps hand positions from camera coordinates to screen/projector coordinates.

### Method 1: Auto (Hand-Based) — Recommended
```bash
# CLI
hermes portal_engine calibrate --method auto --width 1920 --height 1080

# Agent
portal_calibrate({
  "method": "auto",
  "screen_width": 1920,
  "screen_height": 1080,
  "save_profile": "my_setup"
})
```

**Process:**
1. Portal engine must be running (`portal_start` first)
2. System says: "Move hand to top-left corner and hold"
3. Hold your hand steady at screen corner for ~2 seconds
4. Repeat for: top-right → bottom-right → bottom-left
5. Homography computed and saved to `~/.config/portal_engine/my_setup.json`

### Method 2: Manual (Click-Based)
```bash
portal_calibrate({"method": "manual", "screen_width": 1920, "screen_height": 1080})
```
- Camera feed window opens
- Click 4 corners in order: TL → TR → BR → BL
- Press ESC to cancel

### Method 3: Checkerboard (OpenCV Standard)
```bash
portal_calibrate({"method": "checkerboard", "screen_width": 1920, "screen_height": 1080})
```
- Print/display a 9×6 internal corner chessboard
- Show to camera from multiple angles
- Press SPACE when detected (need 10+ samples)
- **Note:** Requires screen corner correspondences for full projector mapping

### Load Saved Profile on Next Start
```bash
# Automatic: profile named "default" loads on portal_start
# Manual:
portal_start({...})  # then in another call:
# The tracker auto-loads "default" profile if it exists
```

---

## 7. Start Output Bridge (Syphon/Spout/NDI/Virtual Camera)

**Auto-detects best protocol for your platform:**
- **macOS** → Syphon (preferred) → NDI
- **Windows** → Spout (preferred) → NDI
- **Linux** → NDI → Virtual Camera → Shared Memory

```bash
# CLI (auto-detect)
hermes portal_engine syphon_start --server_name PortalEngine

# Agent (explicit protocol)
portal_syphon_start({
  "server_name": "PortalEngine",
  "protocol": "auto",       // auto | ndi | spout | syphon | virtual_camera | shared_memory
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "include_alpha": true
})
```

**What happens:**
1. Output bridge starts in background thread
2. Frames from portal engine sent to selected protocol
3. Available in MadMapper/Resolume/TouchDesigner as "PortalEngine"

### In MadMapper / Resolume / TouchDesigner / vMix / OBS

| App | How to Receive |
|-----|----------------|
| **MadMapper** | Media → Syphon/Spout/NDI → Select "PortalEngine" |
| **Resolume Arena** | Sources → Spout/NDI → "PortalEngine" |
| **TouchDesigner** | NDI In TOP / Spout In TOP → "PortalEngine" |
| **vMix** | Add Input → NDI → "PortalEngine" |
| **OBS** | NDI Source → "PortalEngine" (or Virtual Camera) |

---

## 8. Check Status

```bash
# CLI
hermes portal_engine status

# Agent
portal_status({})
```

**Response:**
```json
{
  "ok": true,
  "running": true,
  "camera": {"opened": true, "width": 1280, "height": 720, "fps": 30.0, "index": 0},
  "calibrated": true,
  "homography": [[...], [...], [...]],
  "profiles": ["default", "my_setup"],
  "current_frame": {
    "hands_detected": 2,
    "fps": 28.5,
    "hands": [
      {"handedness": "Right", "center": [640, 360], "score": 0.92, "bbox": [600, 300, 80, 120]},
      {"handedness": "Left", "center": [320, 240], "score": 0.88, "bbox": [280, 180, 80, 120]}
    ]
  }
}
```

### Output Bridge Status
```bash
# CLI
hermes portal_engine syphon_status

# Agent
portal_syphon_status({})
```

**Response:**
```json
{
  "ok": true,
  "running": true,
  "protocol": "spout",
  "server_name": "PortalEngine",
  "config": {"width": 1920, "height": 1080, "fps": 30, "include_alpha": true},
  "available_protocols": {
    "shared_memory": true,
    "ndi": false,
    "spout": true,
    "syphon": false,
    "virtual_camera": false
  }
}
```

---

## 9. Stop Everything

```bash
# CLI (stop output bridge first, then engine)
hermes portal_engine syphon_stop
hermes portal_engine stop

# Agent
portal_syphon_stop({})
portal_stop({})
```

- Closes OpenCV window
- Releases camera
- Stops background threads
- Auto-runs on session end via `on_session_end` hook

---

## 10. Effect Modes Quick Reference

| Mode | Command | Best For |
|------|---------|----------|
| `glowing_hands` | `portal_start({"effect_mode": "glowing_hands"})` | Subtle highlighting, presentations |
| `portal_rings` | `portal_start({"effect_mode": "portal_rings"})` | Sci-fi aesthetic, installations |
| `pass_through` | `portal_start({"effect_mode": "pass_through"})` | "Reaching through" illusion |
| `particles` | `portal_start({"effect_mode": "particles"})` | Artistic, trailing effects |
| `all` (default) | `portal_start({})` | Full demo, maximum impact |

---

## 11. Projector Setup (Optional)

For projection mapping on a wall/screen:

```bash
# 1. Connect projector as secondary display
# 2. Note its resolution (e.g., 1920×1080)
# 3. Enable projector mode in config
cat >> ~/.hermes/profiles/default/config.yaml << 'EOF'
portal_engine:
  enable_projector_mode: true
  portal_width: 1920
  portal_height: 1080
EOF

# 4. Start engine
portal_start({"fullscreen": true})

# 5. Start output bridge
portal_syphon_start({"server_name": "PortalEngine"})

# 6. Calibrate pointing AT the projected area
portal_calibrate({
  "method": "auto",
  "screen_width": 1920,
  "screen_height": 1080,
  "save_profile": "projector_wall"
})

# 7. In MadMapper: map "PortalEngine" to physical frame/projector surface
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Camera not found" | Run `portal_list_cameras`, try different `camera_index` |
| "MediaPipe not installed" | `pip install mediapipe` (requires Python 3.8–3.12) |
| "MediaPipe not available on Python 3.13+" | Use Python 3.12 or earlier |
| Low FPS (<15) | Reduce `max_hands`, close other apps, lower camera resolution |
| Calibration inaccurate | Re-run with stable hand positions, better lighting |
| Hand tracking jittery | Increase `detection_confidence` to 0.8, ensure good lighting |
| Window not fullscreen | Try `fullscreen: false` then toggle manually (F11 on Linux) |
| `cv2.imshow` fails | Need X11/Wayland display; won't work headless |
| NDI not found | Install NDI 5 SDK from ndi.video, then `pip install ndi-python` |
| Spout/Syphon not found | `pip install spout-gl` (Windows) or `pip install syphon` (macOS) |

---

## Example Session

```text
User: "Start the portal engine"
Agent: portal_start() 
       → "Portal engine started on camera 0"

User: "Calibrate it for my 1920x1080 monitor"
Agent: portal_calibrate(method="auto", screen_width=1920, screen_height=1080)
       → "Move hand to top-left corner..." → "Calibration complete, saved as 'default'"

User: "Send to MadMapper"
Agent: portal_syphon_start({"server_name": "PortalEngine"})
       → "Output bridge started (spout). Available in MadMapper as 'PortalEngine'."

User: "Show me the status"
Agent: portal_status()
       → {running: true, hands_detected: 1, calibrated: true, ...}

User: "Switch to just glowing hands"
Agent: portal_stop()
       → portal_start({"effect_mode": "glowing_hands"})

User: "Stop everything"
Agent: portal_syphon_stop()
       → portal_stop()
       → "Portal engine stopped"
```

---

## Creative Ideas to Try

1. **Interactive Presentation** — Use hand position to highlight slides
2. **Art Installation** — Project on wall, let visitors create portal trails
3. **Gesture Control** — Map hand zones to `kanban_create`, `agent_journal`, etc.
4. **Live Performance** — Sync with music via separate audio-reactive script
5. **Education** — Demonstrate homography, hand tracking, real-time CV

---

## File Locations Reference

| File | Path |
|------|------|
| Plugin config | `~/.hermes/profiles/<name>/config.yaml` → `portal_engine:` section |
| Calibration profiles | `~/.config/portal_engine/<profile>.json` |
| Plugin source | `~/.hermes/plugins/portal_engine/` |
| Skill (for agents) | `~/.hermes/plugins/portal_engine/skills/portal_engine/SKILL.md` |

---

## Uninstall

```bash
hermes plugins disable portal-engine
hermes plugins remove portal-engine
# That also removes the plugin directory under ~/.hermes/plugins/ and the
# calibration profiles under ~/.config/portal_engine/ (delete that folder
# manually if you want to keep profiles).
```

---

*Portal Engine v0.1.0 — Built for NousResearch Hermes Agent Plugin Hackathon*
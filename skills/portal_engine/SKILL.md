---
name: portal-engine
description: "Use when you need to control the interactive portal engine — start/stop hand tracking, calibrate camera-to-screen, create portal visual effects. Teaches the agent how to set up and use portals interactively."
version: 0.1.0
author: NousResearch Hackathon
tags: [portal, computer-vision, hand-tracking, opencv, mediapipe, interactive, projection-mapping]
---

# Portal Engine Skill

This skill teaches you how to use the **portal-engine** Hermes plugin to create interactive "viral portal" effects using OpenCV hand tracking and real-time visual overlays.

## Overview

The portal-engine plugin provides:
- **Real-time hand tracking** via MediaPipe (up to 4 hands simultaneously)
- **Visual effects**: glowing hands, expanding portal rings, pass-through portals, particle trails
- **Camera calibration** for projector/screen mapping (auto, manual, or checkerboard)
- **Hermes tools** for full agent control

## Quick Start

### 1. Check Available Cameras
```python
# List cameras to find the right index
result = portal_list_cameras(max_test=5)
```

### 2. Start the Portal Engine
```python
# Start with default settings (camera 0, all effects, fullscreen)
result = portal_start({
    "camera_index": 0,
    "effect_mode": "all",        # glowing_hands | portal_rings | pass_through | particles | all
    "fullscreen": true,
    "mirror": true,
    "detection_confidence": 0.7,
    "tracking_confidence": 0.5,
    "max_hands": 2
})
```

### 3. Calibrate for Projector/Screen Mapping
```python
# Auto-calibration: move hand to 4 screen corners
result = portal_calibrate({
    "method": "auto",           # auto | manual | checkerboard
    "screen_width": 1920,
    "screen_height": 1080,
    "save_profile": "my_setup"
})

# Manual: click 4 corners on camera feed
result = portal_calibrate({"method": "manual", "screen_width": 1920, "screen_height": 1080})

# Checkerboard: show OpenCV chessboard pattern
result = portal_calibrate({"method": "checkerboard", "screen_width": 1920, "screen_height": 1080})
```

### 4. Check Status
```python
result = portal_status()
# Returns: running state, camera info, calibration, detected hands with positions
```

### 5. Stop When Done
```python
result = portal_stop()
```

## Effect Modes

| Mode | Description |
|------|-------------|
| `glowing_hands` | Pulsing glow around hands, skeleton overlay, fingertip highlights |
| `portal_rings` | Expanding cyan rings emanating from hand positions |
| `pass_through` | Rectangular portal frame with scanlines at hand position |
| `particles` | Sparkle particles trailing from fingertips |
| `all` | All effects combined (default) |

## Calibration Methods

### Auto (Hand-Based)
1. Start portal engine
2. Run `portal_calibrate` with `method: "auto"`
3. Move your hand to each screen corner (TL, TR, BR, BL) and hold for ~2 seconds
4. Homography is computed and saved

### Manual (Click-Based)
1. Run `portal_calibrate` with `method: "manual"`
2. Camera feed window opens
3. Click 4 corners in order: top-left, top-right, bottom-right, bottom-left
4. Press ESC to cancel

### Checkerboard (OpenCV Standard)
1. Print or display a chessboard pattern (9x6 internal corners)
2. Run `portal_calibrate` with `method: "checkerboard"`
3. Show chessboard to camera from multiple angles
4. Press SPACE when detected (need 10+ samples)
5. Note: Requires screen corner correspondences for full projector mapping

## Calibration Profiles

Calibrations are saved to `~/.config/portal_engine/<profile>.json`

```python
# List saved profiles
profiles = list_calibration_profiles()  # via portal_status()

# Load a profile on startup
load_calibration_profile("my_setup", tracker)
```

## Advanced Usage

### Custom Effect Configuration
```python
# Subtle effects for presentations
portal_start({
    "effect_mode": "glowing_hands",
    "detection_confidence": 0.8,
    "max_hands": 1
})

# Particle-only for artistic effect
portal_start({
    "effect_mode": "particles",
    "fullscreen": false,
})
```

### Multi-Hand Interactions
With `max_hands: 2` (default), both hands create independent effects:
- Each hand gets its own portal rings
- Particle trails from all fingertips
- Pass-through portals at each hand position

### Projector Setup
1. Connect projector as secondary display
2. Set `enable_projector_mode: true` in config.yaml
3. Run auto-calibration pointing at projected area
4. Portal engine will render fullscreen on projector

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Camera not found" | Check `portal_list_cameras`, try different `camera_index` |
| "MediaPipe not installed" | `pip install mediapipe opencv-python numpy` |
| Low FPS | Reduce camera resolution, lower `max_hands`, close other apps |
| Calibration inaccurate | Re-run with more stable hand positions, better lighting |
| Hand tracking jittery | Increase `detection_confidence` to 0.8, ensure good lighting |
| Window not fullscreen | Check `cv2` backend, try `fullscreen: false` then toggle manually |

## Dependencies

```bash
pip install mediapipe opencv-python numpy
```

**System requirements:**
- Python 3.8+
- Camera (built-in or USB)
- OpenCV with GUI support (cv2.imshow)
- Optional: Projector for projection mapping

## Hardware Disclosure

- **Camera access**: Required for hand tracking (uses OpenCV VideoCapture)
- **Display window**: Opens OpenCV window for real-time visualization
- **Projector (optional)**: For projection mapping, uses secondary display
- **No network access**: All processing is local
- **No shell commands**: Pure Python/OpenCV

## Example Session

```
User: "Start the portal engine"
Agent: portal_start() → "Portal engine started on camera 0"

User: "Calibrate it for my 1920x1080 projector"
Agent: portal_calibrate(method="auto", screen_width=1920, screen_height=1080)
       → "Move hand to top-left corner..." → calibration complete

User: "Show me the status"
Agent: portal_status() → {running: true, hands: [...], calibrated: true}

User: "Stop it"
Agent: portal_stop() → "Portal engine stopped"
```

## Creative Ideas

1. **Interactive Presentation**: Use hand gestures to highlight slides
2. **Art Installation**: Project portal effects on walls, let visitors interact
3. **Gesture Control**: Map hand positions to control other tools
4. **Performance**: Combine with music/visuals for live shows
5. **Education**: Demonstrate computer vision concepts interactively

---

*Portal Engine v0.1.0 — Built for the NousResearch Hermes Agent Plugin Hackathon*
# Portal Engine — Hackathon Submission

**NousResearch Hermes Agent Plugin Hackathon**

Author: bazziba-it
Plugin: `portal-engine` v0.1.0
Repo: https://github.com/bazziba-it/hermes-plugin-portal-engine

---

## What It Does

Portal Engine gives Hermes **real-time control over an interactive computer-vision "portal" system** — the viral concept popularized by @builtwbrendan (OpenCV hand tracking + projection mapping + physical frames), reimagined as a software-first agent-controllable plugin with professional video output.

The agent can start/stop hand tracking, calibrate camera-to-screen, read live hand positions as JSON, and stream the annotated video to MadMapper / Resolume / TouchDesigner / vMix / OBS via Syphon (macOS), Spout (Windows), NDI, or virtual camera.

## Why It's More Than a Skill

- **8 registered tools** with JSON schemas — the agent calls them like any other tool
- **1 hook** (`on_session_end`) — auto-cleanup, no leaked cameras/threads
- **1 bundled skill** — teaches the agent the workflow
- **Real CV pipeline** — MediaPipe hand tracking (up to 4 hands) + OpenCV effects rendering at 30fps
- **Professional output bridge** — 5 protocols with platform auto-detection and graceful fallback

## Tool Surface

| Tool | What the agent does with it |
|------|----------------------------|
| `portal_start` | Launch tracker + effects with chosen mode, camera, confidence |
| `portal_stop` | Stop engine, release camera, close window |
| `portal_calibrate` | Run auto (hand-point), manual (click), or checkerboard calibration; save profile |
| `portal_status` | Get live JSON: hands detected, positions, bbox, handedness, FPS, homography |
| `portal_list_cameras` | Probe available cameras with resolution/FPS/backend |
| `portal_syphon_start` | Start output bridge (auto-detects Syphon/Spout/NDI/virtual-cam/shared-memory) |
| `portal_syphon_stop` | Stop output bridge |
| `portal_syphon_status` | Report bridge status + which protocols are available on this machine |

## Demo (under 90 seconds)

1. `portal_list_cameras` → shows camera 0 at 1280×720
2. `portal_start({effect_mode: "all"})` → OpenCV window opens, hands glow with rings + particles
3. `portal_calibrate({method: "auto", screen_width: 1920, screen_height: 1080})` → 4-corner homography
4. `portal_syphon_start({protocol: "ndi", server_name: "PortalEngine"})` → stream live
5. `portal_status()` → JSON with 2 hands, positions, FPS
6. In MadMapper/Resolume: NDI In → "PortalEngine" → mapped onto a physical frame on the wall
7. `portal_stop()` → clean shutdown

## Dependencies & Disclosure

| Dependency | Type | Required? |
|-----------|------|-----------|
| Python 3.8–3.12 | runtime | yes (MediaPipe wheel ceiling; plugin checks and reports clearly on 3.13+) |
| `mediapipe` | pip | yes for tracking; plugin loads without it and returns a clear JSON error |
| `opencv-python` + `numpy` | pip | yes |
| Camera | hardware | yes for tracking; `portal_list_cameras` probes gracefully |
| `ndi-python` + NDI 5 SDK | pip + SDK | optional, for NDI output |
| `spout-gl` | pip | optional, Windows output |
| Syphon framework | macOS | optional, macOS output |
| `pyvirtualcam` + v4l2loopback | pip + kernel module | optional, Linux virtual camera |
| Projector | hardware | optional, projection mapping |

- **Network**: none — all processing and IPC is local
- **Shell**: none — pure Python/OpenCV
- **Secrets**: none

## Cross-Platform

- **Windows**: Spout preferred (GPU texture sharing), NDI fallback — see `WINDOWS_HOWTO.md`
- **macOS**: Syphon preferred, NDI fallback
- **Linux**: NDI preferred, virtual camera / shared-memory fallback
- `plugin.yaml` declares `python_runtime: ">=3.8,<3.13"` so the catalog filters incompatible environments

## Works With Official Plugins

Complements [`hermes-plugin-touchdesigner`](https://github.com/NousResearch/hermes-plugin-touchdesigner): portal-engine feeds **video** into TouchDesigner via NDI/Spout (perception), the TouchDesigner plugin drives **parameters** via MCP (action). Together: hand tracking controls both visuals and logic in a TouchDesigner installation.

## Install

```bash
hermes plugins install github:bazziba-it/hermes-plugin-portal-engine --enable
pip install mediapipe opencv-python numpy ndi-python
```

## Files

```
plugin.yaml  __init__.py  schemas.py  tools.py
portal_tracker.py  portal_effects.py  portal_calibration.py  portal_output.py
skills/portal_engine/SKILL.md
README.md  HOWTO.md  WINDOWS_HOWTO.md  HACKATHON.md
```

## License

MIT
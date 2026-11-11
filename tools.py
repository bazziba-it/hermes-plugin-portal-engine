"""Tool handlers for portal-engine plugin."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Optional

import cv2

from .schemas import (
    PORTAL_START_SCHEMA,
    PORTAL_STOP_SCHEMA,
    PORTAL_CALIBRATE_SCHEMA,
    PORTAL_STATUS_SCHEMA,
    PORTAL_LIST_CAMERAS_SCHEMA,
    PORTAL_SYPHON_START_SCHEMA,
    PORTAL_SYPHON_STOP_SCHEMA,
    PORTAL_SYPHON_STATUS_SCHEMA,
)
from .portal_tracker import HandTracker
from .portal_effects import PortalEffects, EffectConfig, create_portal_window
from .portal_calibration import (
    list_cameras,
    run_calibration,
    load_calibration_profile,
    delete_calibration_profile,
    list_calibration_profiles,
    get_calibration_info,
)
from .portal_output import (
    create_sender,
    OutputConfig,
    list_available_protocols,
)

logger = logging.getLogger(__name__)

# Global tracker instance (singleton per session)
_tracker: Optional[HandTracker] = None
_effects: Optional[PortalEffects] = None
_display_thread: Optional[threading.Thread] = None
_stop_display = threading.Event()
_tracker_lock = threading.Lock()

# Global output sender (for Syphon/Spout/NDI/virtual camera)
_output_sender: Optional[Any] = None
_output_thread: Optional[threading.Thread] = None
_stop_output = threading.Event()
_output_lock = threading.Lock()


def _get_tracker() -> Optional[HandTracker]:
    global _tracker
    with _tracker_lock:
        return _tracker


def _set_tracker(tracker: Optional[HandTracker]) -> None:
    global _tracker, _effects, _display_thread, _stop_display
    with _tracker_lock:
        # Clean up existing
        if _tracker:
            _tracker.stop()
        if _display_thread and _display_thread.is_alive():
            _stop_display.set()
            _display_thread.join(timeout=2.0)
        _stop_display.clear()

        _tracker = tracker
        if tracker:
            _effects = PortalEffects()
        else:
            _effects = None


def _get_output_sender() -> Optional[Any]:
    global _output_sender
    with _output_lock:
        return _output_sender


def _set_output_sender(sender: Optional[Any]) -> None:
    global _output_sender, _output_thread, _stop_output
    with _output_lock:
        # Clean up existing
        if _output_sender:
            _output_sender.stop()
        if _output_thread and _output_thread.is_alive():
            _stop_output.set()
            _output_thread.join(timeout=2.0)
        _stop_output.clear()

        _output_sender = sender


def _output_loop() -> None:
    """Background thread for sending frames to output protocol."""
    global _tracker, _effects, _output_sender, _stop_output

    while not _stop_output.is_set() and _tracker and _tracker.is_running() and _output_sender:
        frame_data = _tracker.get_latest_frame()
        if frame_data and _effects:
            # Apply effects (same as display)
            output = _effects.process(frame_data, effect_mode="all")

            # Send to output protocol
            _output_sender.send_frame(output)

        # Control frame rate
        time.sleep(1.0 / 60.0)  # Cap at 60fps

    logger.info("Output sender loop ended")


def _display_loop(window_name: str = "Portal Engine", fullscreen: bool = True) -> None:
    """Background thread for displaying the portal window."""
    global _tracker, _effects, _stop_display

    create_portal_window(window_name, fullscreen=fullscreen)

    while not _stop_display.is_set() and _tracker and _tracker.is_running():
        frame_data = _tracker.get_latest_frame()
        if frame_data and _effects:
            # Apply effects
            output = _effects.process(frame_data, effect_mode="all")

            # Show FPS on frame
            cv2.imshow(window_name, output)

        # Check for quit key
        key = cv2.waitKey(1) & 0xFF
        if key == 27 or key == ord('q'):  # ESC or q
            break

    cv2.destroyWindow(window_name)
    logger.info("Portal display loop ended")


def portal_start_handler(args: dict[str, Any], ctx: Any = None) -> str:
    """Start the portal engine with hand tracking and visual effects."""
    global _display_thread, _stop_display

    # Check MediaPipe availability early for clear error message
    try:
        import mediapipe
    except ImportError:
        import sys
        py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        if sys.version_info >= (3, 13):
            return json.dumps({
                "ok": False,
                "error": f"MediaPipe not available on Python {py_version} (no wheels for 3.13+). Use Python 3.8–3.12.",
                "status": "mediapipe_unavailable",
                "python_version": py_version,
                "solution": "Install Python 3.12 or earlier, then: pip install mediapipe opencv-python numpy",
            })
        else:
            return json.dumps({
                "ok": False,
                "error": "MediaPipe not installed. Run: pip install mediapipe opencv-python numpy",
                "status": "mediapipe_not_installed",
                "solution": "pip install mediapipe opencv-python numpy",
            })

    camera_index = args.get("camera_index", 0)
    effect_mode = args.get("effect_mode", "all")
    fullscreen = args.get("fullscreen", True)
    mirror = args.get("mirror", True)
    detection_confidence = args.get("detection_confidence", 0.7)
    tracking_confidence = args.get("tracking_confidence", 0.5)
    max_hands = args.get("max_hands", 2)

    # Check if already running
    existing = _get_tracker()
    if existing and existing.is_running():
        return json.dumps({
            "ok": False,
            "error": "Portal engine already running. Call portal_stop first.",
            "status": "already_running",
        })

    # Create and start tracker
    tracker = HandTracker(
        camera_index=camera_index,
        detection_confidence=detection_confidence,
        tracking_confidence=tracking_confidence,
        max_hands=max_hands,
        mirror=mirror,
    )

    if not tracker.start():
        return json.dumps({
            "ok": False,
            "error": f"Failed to start hand tracker on camera {camera_index}",
            "status": "init_failed",
        })

    _set_tracker(tracker)

    # Start display thread
    _stop_display.clear()
    _display_thread = threading.Thread(
        target=_display_loop,
        args=("Portal Engine", fullscreen),
        daemon=True,
    )
    _display_thread.start()

    # Try to load default calibration
    load_calibration_profile("default", tracker)

    camera_info = tracker.get_camera_info()
    return json.dumps({
        "ok": True,
        "status": "started",
        "camera": camera_info,
        "settings": {
            "effect_mode": effect_mode,
            "fullscreen": fullscreen,
            "mirror": mirror,
            "detection_confidence": detection_confidence,
            "tracking_confidence": tracking_confidence,
            "max_hands": max_hands,
        },
        "message": "Portal engine started. Press ESC or 'q' in the window to stop.",
    })


def portal_stop_handler(args: dict[str, Any], ctx: Any = None) -> str:
    """Stop the portal engine."""
    global _display_thread, _stop_display

    tracker = _get_tracker()
    if not tracker or not tracker.is_running():
        return json.dumps({
            "ok": True,
            "status": "already_stopped",
            "message": "Portal engine was not running",
        })

    _stop_display.set()
    if _display_thread and _display_thread.is_alive():
        _display_thread.join(timeout=2.0)

    tracker.stop()
    _set_tracker(None)

    cv2.destroyAllWindows()

    return json.dumps({
        "ok": True,
        "status": "stopped",
        "message": "Portal engine stopped",
    })


def portal_calibrate_handler(args: dict[str, Any], ctx: Any = None) -> str:
    """Run camera-to-screen calibration."""
    tracker = _get_tracker()
    if not tracker or not tracker.is_running():
        return json.dumps({
            "ok": False,
            "error": "Portal engine not running. Start it first with portal_start.",
            "status": "not_running",
        })

    method = args.get("method", "auto")
    screen_width = args.get("screen_width", 1920)
    screen_height = args.get("screen_height", 1080)
    save_profile = args.get("save_profile", "default")

    # Run calibration in a way that doesn't block the display
    # For auto calibration, we can run it in background
    result = run_calibration(
        tracker=tracker,
        method=method,
        screen_width=screen_width,
        screen_height=screen_height,
        save_profile=save_profile,
    )

    return json.dumps(result)


def portal_status_handler(args: dict[str, Any], ctx: Any = None) -> str:
    """Get current portal engine status."""
    tracker = _get_tracker()

    if not tracker:
        return json.dumps({
            "ok": True,
            "running": False,
            "message": "Portal engine not initialized",
        })

    is_running = tracker.is_running()
    camera_info = tracker.get_camera_info()
    homography = tracker.get_homography()

    status = {
        "ok": True,
        "running": is_running,
        "camera": camera_info,
        "calibrated": homography is not None,
        "homography": homography.tolist() if homography is not None else None,
        "profiles": list_calibration_profiles(),
    }

    if is_running:
        frame = tracker.get_latest_frame()
        if frame:
            status["current_frame"] = {
                "hands_detected": len(frame.hands),
                "fps": frame.fps,
                "timestamp": frame.timestamp,
                "hands": [
                    {
                        "handedness": h.handedness,
                        "center": h.center,
                        "score": h.score,
                        "bbox": h.bbox,
                    }
                    for h in frame.hands
                ],
            }

    return json.dumps(status)


def portal_list_cameras_handler(args: dict[str, Any], ctx: Any = None) -> str:
    """List available cameras."""
    max_test = args.get("max_test", 10)
    cameras = list_cameras(max_test)

    return json.dumps({
        "ok": True,
        "cameras": cameras,
        "count": len(cameras),
    })


def portal_syphon_start_handler(args: dict[str, Any], ctx: Any = None) -> str:
    """Start the Syphon/Spout/NDI/virtual camera output bridge."""
    global _output_thread, _stop_output

    # Check if portal engine is running
    tracker = _get_tracker()
    if not tracker or not tracker.is_running():
        return json.dumps({
            "ok": False,
            "error": "Portal engine not running. Start it first with portal_start.",
            "status": "engine_not_running",
        })

    # Check if output already running
    existing = _get_output_sender()
    if existing and existing.is_running():
        return json.dumps({
            "ok": False,
            "error": "Output bridge already running. Call portal_syphon_stop first.",
            "status": "already_running",
        })

    # Create output config
    config = OutputConfig(
        server_name=args.get("server_name", "PortalEngine"),
        protocol=args.get("protocol", "auto"),
        width=args.get("width", 1920),
        height=args.get("height", 1080),
        fps=args.get("fps", 30),
        include_alpha=args.get("include_alpha", True),
    )

    # Create sender
    sender = create_sender(config)
    if not sender.start():
        return json.dumps({
            "ok": False,
            "error": f"Failed to start {config.protocol} output sender",
            "status": "init_failed",
            "available_protocols": list_available_protocols(),
        })

    _set_output_sender(sender)

    # Start output thread
    _stop_output.clear()
    _output_thread = threading.Thread(
        target=_output_loop,
        daemon=True,
    )
    _output_thread.start()

    return json.dumps({
        "ok": True,
        "status": "started",
        "protocol": config.protocol,
        "server_name": config.server_name,
        "config": {
            "width": config.width,
            "height": config.height,
            "fps": config.fps,
            "include_alpha": config.include_alpha,
        },
        "available_protocols": list_available_protocols(),
        "message": f"Output bridge started ({config.protocol}). Available in MadMapper/Resolume/TouchDesigner as '{config.server_name}'.",
    })


def portal_syphon_stop_handler(args: dict[str, Any], ctx: Any = None) -> str:
    """Stop the output bridge."""
    global _output_thread, _stop_output

    sender = _get_output_sender()
    if not sender or not sender.is_running():
        return json.dumps({
            "ok": True,
            "status": "already_stopped",
            "message": "Output bridge was not running",
        })

    _stop_output.set()
    if _output_thread and _output_thread.is_alive():
        _output_thread.join(timeout=2.0)

    sender.stop()
    _set_output_sender(None)

    return json.dumps({
        "ok": True,
        "status": "stopped",
        "message": "Output bridge stopped",
    })


def portal_syphon_status_handler(args: dict[str, Any], ctx: Any = None) -> str:
    """Get output bridge status and available protocols."""
    sender = _get_output_sender()

    if not sender:
        return json.dumps({
            "ok": True,
            "running": False,
            "message": "Output bridge not initialized",
            "available_protocols": list_available_protocols(),
        })

    status = sender.get_status()
    status["ok"] = True
    status["available_protocols"] = list_available_protocols()

    return json.dumps(status)


# Tool registration schemas for Hermes
TOOL_SCHEMAS = {
    "portal_start": PORTAL_START_SCHEMA,
    "portal_stop": PORTAL_STOP_SCHEMA,
    "portal_calibrate": PORTAL_CALIBRATE_SCHEMA,
    "portal_status": PORTAL_STATUS_SCHEMA,
    "portal_list_cameras": PORTAL_LIST_CAMERAS_SCHEMA,
    "portal_syphon_start": PORTAL_SYPHON_START_SCHEMA,
    "portal_syphon_stop": PORTAL_SYPHON_STOP_SCHEMA,
    "portal_syphon_status": PORTAL_SYPHON_STATUS_SCHEMA,
}

TOOL_HANDLERS = {
    "portal_start": portal_start_handler,
    "portal_stop": portal_stop_handler,
    "portal_calibrate": portal_calibrate_handler,
    "portal_status": portal_status_handler,
    "portal_list_cameras": portal_list_cameras_handler,
    "portal_syphon_start": portal_syphon_start_handler,
    "portal_syphon_stop": portal_syphon_stop_handler,
    "portal_syphon_status": portal_syphon_status_handler,
}


def register_all_tools(ctx) -> None:
    """Register all portal-engine tools with Hermes."""
    for name, schema in TOOL_SCHEMAS.items():
        handler = TOOL_HANDLERS[name]
        ctx.register_tool(
            name=name,
            toolset="portal_engine",
            schema=schema,
            handler=handler,
            description=f"Portal Engine: {name.replace('_', ' ').title()}",
            emoji={
                "portal_start": "🌀",
                "portal_stop": "⏹️",
                "portal_calibrate": "🎯",
                "portal_status": "📊",
                "portal_list_cameras": "📷",
                "portal_syphon_start": "📡",
                "portal_syphon_stop": "🔌",
                "portal_syphon_status": "📈",
            }.get(name, "✨"),
        )
    logger.info("Registered %d portal-engine tools", len(TOOL_SCHEMAS))
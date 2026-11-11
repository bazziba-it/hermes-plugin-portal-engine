"""portal-engine — Interactive portal engine for Hermes.

OpenCV + MediaPipe hand tracking with real-time visual effects.
Control portals from Hermes: start/stop tracker, calibrate camera-to-screen,
render glowing hand overlays and pass-through effects.

Tools:
  - portal_start: Start hand tracking with visual effects
  - portal_stop: Stop the portal engine
  - portal_calibrate: Calibrate camera to screen/projector
  - portal_status: Get current status and hand positions
  - portal_list_cameras: List available cameras
  - portal_syphon_start: Start Syphon/Spout/NDI/virtual camera output
  - portal_syphon_stop: Stop output bridge
  - portal_syphon_status: Get output bridge status

Hooks:
  - on_session_end: Auto-stop portal engine on session end
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from .tools import register_all_tools

logger = logging.getLogger(__name__)

# Python version check — MediaPipe only provides wheels up to Python 3.12
if sys.version_info >= (3, 13):
    logger.error(
        "portal-engine requires Python 3.8–3.12 (MediaPipe has no wheels for 3.13+). "
        f"Current: Python {sys.version_info.major}.{sys.version_info.minor}. "
        "Please use a supported Python version."
    )
    # Don't raise — let plugin load fail gracefully with clear message

def _check_mediapipe_available() -> bool:
    """Check if MediaPipe can be imported."""
    try:
        import mediapipe
        return True
    except ImportError:
        return False


def _on_session_end(session_id: str = "", completed: bool = True, interrupted: bool = False, **_: Any) -> None:
    """Auto-stop portal engine and output bridge when Hermes session ends."""
    try:
        from .tools import _get_tracker, _stop_display, _display_thread, _get_output_sender, _stop_output, _output_thread

        # Stop output bridge first
        sender = _get_output_sender()
        if sender and sender.is_running():
            logger.info("Session ending — stopping output bridge")
            _stop_output.set()
            if _output_thread and _output_thread.is_alive():
                _output_thread.join(timeout=2.0)
            sender.stop()
            from .tools import _set_output_sender
            _set_output_sender(None)

        # Stop portal engine
        tracker = _get_tracker()
        if tracker and tracker.is_running():
            logger.info("Session ending — stopping portal engine")
            _stop_display.set()
            if _display_thread and _display_thread.is_alive():
                _display_thread.join(timeout=2.0)
            tracker.stop()
            from .tools import _set_tracker
            _set_tracker(None)
    except Exception as exc:
        logger.debug("portal-engine session end cleanup failed: %s", exc)


def _load_bundled_skill(ctx) -> None:
    """Load the bundled portal-engine skill."""
    skill_dir = Path(__file__).parent / "skills" / "portal_engine"
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists():
        # register_skill expects the path to SKILL.md, not the content
        description = "Interactive portal engine — OpenCV hand tracking with real-time visual effects."
        ctx.register_skill("portal-engine", skill_file, description, {})
        logger.info("Registered portal-engine skill")
    else:
        logger.warning("SKILL.md not found at %s", skill_file)


def register(ctx) -> None:
    """Plugin entry point — called by Hermes plugin loader."""
    logger.info("portal-engine plugin registering...")

    # Register tools
    register_all_tools(ctx)

    # Register session end hook for cleanup
    ctx.register_hook("on_session_end", _on_session_end)

    # Register bundled skill
    _load_bundled_skill(ctx)

    logger.info("portal-engine plugin registered (8 tools + on_session_end hook + 1 skill)")
"""Calibration tools for portal-engine."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from .portal_tracker import HandTracker, PortalCalibrator

logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".config" / "portal_engine"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def list_cameras(max_test: int = 10) -> list[dict[str, Any]]:
    """List available cameras with their properties."""
    cameras = []
    for i in range(max_test):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            cameras.append({
                "index": i,
                "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": cap.get(cv2.CAP_PROP_FPS),
                "backend": cap.getBackendName(),
            })
            cap.release()
        else:
            break
    return cameras


def run_calibration(
    tracker: HandTracker,
    method: str = "auto",
    screen_width: int = 1920,
    screen_height: int = 1080,
    save_profile: str = "default",
) -> dict[str, Any]:
    """Run calibration with the specified method."""
    calibrator = PortalCalibrator(tracker)

    if method == "auto":
        homography = calibrator.auto_calibrate_from_hands(screen_width, screen_height)
    elif method == "manual":
        homography = calibrator.manual_calibrate(screen_width, screen_height)
    elif method == "checkerboard":
        homography = calibrator.checkerboard_calibrate(screen_width, screen_height)
    else:
        return {"success": False, "error": f"Unknown calibration method: {method}"}

    if homography is not None:
        calibrator.save_calibration(save_profile, homography)
        return {
            "success": True,
            "method": method,
            "profile": save_profile,
            "screen_size": [screen_width, screen_height],
            "homography": homography.tolist(),
        }
    else:
        return {"success": False, "error": "Calibration failed"}


def load_calibration_profile(profile: str, tracker: HandTracker) -> bool:
    """Load a saved calibration profile."""
    calibrator = PortalCalibrator(tracker)
    homography = calibrator.load_calibration(profile)
    return homography is not None


def delete_calibration_profile(profile: str) -> bool:
    """Delete a saved calibration profile."""
    profile_file = CONFIG_DIR / f"{profile}.json"
    if profile_file.exists():
        profile_file.unlink()
        logger.info(f"Deleted calibration profile: {profile}")
        return True
    return False


def list_calibration_profiles() -> list[str]:
    """List available calibration profiles."""
    profiles = []
    for f in CONFIG_DIR.glob("*.json"):
        profiles.append(f.stem)
    return sorted(profiles)


def get_calibration_info(profile: str) -> Optional[dict[str, Any]]:
    """Get info about a calibration profile."""
    profile_file = CONFIG_DIR / f"{profile}.json"
    if not profile_file.exists():
        return None
    try:
        with open(profile_file) as f:
            return json.load(f)
    except Exception:
        return None
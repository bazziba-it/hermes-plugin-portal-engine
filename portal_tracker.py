"""OpenCV + MediaPipe hand tracking for portal-engine."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class HandLandmark:
    """Single hand landmark point."""
    x: float
    y: float
    z: float
    visibility: float = 1.0


@dataclass
class Hand:
    """Detected hand with landmarks and metadata."""
    landmarks: list[HandLandmark]
    handedness: str  # "Left" or "Right"
    score: float
    bbox: tuple[int, int, int, int]  # x, y, w, h
    center: tuple[float, float]


@dataclass
class PortalFrame:
    """Processed frame with hand tracking data."""
    frame: np.ndarray
    hands: list[Hand]
    timestamp: float
    fps: float
    frame_shape: tuple[int, int]


class HandTracker:
    """MediaPipe-based hand tracker with portal-specific utilities."""

    def __init__(
        self,
        camera_index: int = 0,
        detection_confidence: float = 0.7,
        tracking_confidence: float = 0.5,
        max_hands: int = 2,
        mirror: bool = True,
    ):
        self.camera_index = camera_index
        self.detection_confidence = detection_confidence
        self.tracking_confidence = tracking_confidence
        self.max_hands = max_hands
        self.mirror = mirror

        self._cap: Optional[cv2.VideoCapture] = None
        self._hands_detector = None
        self._running = False
        self._lock = threading.Lock()
        self._latest_frame: Optional[PortalFrame] = None
        self._thread: Optional[threading.Thread] = None

        # FPS calculation
        self._frame_times: list[float] = []
        self._last_fps = 0.0

        # Homography for camera-to-screen mapping
        self._homography: Optional[np.ndarray] = None
        self._calibration_points: list[tuple[float, float]] = []

    def initialize(self) -> bool:
        """Initialize camera and MediaPipe hands detector."""
        try:
            import mediapipe as mp
        except ImportError:
            logger.error("MediaPipe not installed. Run: pip install mediapipe")
            return False

        # Open camera
        self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            logger.error(f"Failed to open camera index {self.camera_index}")
            return False

        # Set reasonable defaults
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self._cap.set(cv2.CAP_PROP_FPS, 30)

        # Initialize MediaPipe Hands
        self._mp_hands = mp.solutions.hands
        self._hands_detector = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=self.max_hands,
            min_detection_confidence=self.detection_confidence,
            min_tracking_confidence=self.tracking_confidence,
            model_complexity=1,
        )
        self._mp_drawing = mp.solutions.drawing_utils
        self._mp_drawing_styles = mp.solutions.drawing_styles

        logger.info(f"Hand tracker initialized on camera {self.camera_index}")
        return True

    def start(self) -> bool:
        """Start the tracking thread."""
        if self._running:
            return True

        if not self.initialize():
            return False

        self._running = True
        self._thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop the tracking thread and release resources."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        if self._hands_detector:
            self._hands_detector.close()
            self._hands_detector = None
        logger.info("Hand tracker stopped")

    def _tracking_loop(self) -> None:
        """Main tracking loop running in background thread."""
        while self._running and self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # Mirror for natural webcam view
            if self.mirror:
                frame = cv2.flip(frame, 1)

            # Convert to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb_frame.flags.writeable = False

            # Process with MediaPipe
            results = self._hands_detector.process(rgb_frame)

            # Convert back to BGR for OpenCV display
            rgb_frame.flags.writeable = True
            frame = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR)

            # Extract hand data
            hands = []
            if results.multi_hand_landmarks and results.multi_handedness:
                for hand_landmarks, handedness in zip(
                    results.multi_hand_landmarks, results.multi_handedness
                ):
                    hand = self._process_hand(hand_landmarks, handedness, frame.shape)
                    if hand:
                        hands.append(hand)

            # Calculate FPS
            now = time.time()
            self._frame_times.append(now)
            self._frame_times = [t for t in self._frame_times if now - t < 1.0]
            self._last_fps = len(self._frame_times)

            # Store latest frame
            portal_frame = PortalFrame(
                frame=frame,
                hands=hands,
                timestamp=now,
                fps=self._last_fps,
                frame_shape=frame.shape[:2],
            )

            with self._lock:
                self._latest_frame = portal_frame

    def _process_hand(
        self, landmarks, handedness, frame_shape: tuple[int, int]
    ) -> Optional[Hand]:
        """Process MediaPipe hand landmarks into our Hand dataclass."""
        h, w = frame_shape[:2]

        # Extract landmarks
        hand_landmarks = []
        x_coords = []
        y_coords = []

        for lm in landmarks.landmark:
            x, y, z = lm.x * w, lm.y * h, lm.z * w
            hand_landmarks.append(HandLandmark(x=x, y=y, z=z, visibility=lm.visibility))
            x_coords.append(x)
            y_coords.append(y)

        # Bounding box
        x_min, x_max = min(x_coords), max(x_coords)
        y_min, y_max = min(y_coords), max(y_coords)
        bbox = (int(x_min), int(y_min), int(x_max - x_min), int(y_max - y_min))

        # Center point (palm center - landmark 0 is wrist, 9 is middle finger MCP)
        palm_x = (landmarks.landmark[0].x + landmarks.landmark[9].x) / 2 * w
        palm_y = (landmarks.landmark[0].y + landmarks.landmark[9].y) / 2 * h

        # Handedness
        hand_label = handedness.classification[0].label
        score = handedness.classification[0].score

        return Hand(
            landmarks=hand_landmarks,
            handedness=hand_label,
            score=score,
            bbox=bbox,
            center=(palm_x, palm_y),
        )

    def get_latest_frame(self) -> Optional[PortalFrame]:
        """Get the most recent processed frame (thread-safe)."""
        with self._lock:
            return self._latest_frame

    def set_homography(self, matrix: np.ndarray) -> None:
        """Set the camera-to-screen homography matrix."""
        self._homography = matrix

    def get_homography(self) -> Optional[np.ndarray]:
        """Get the current homography matrix."""
        return self._homography

    def map_point(self, point: tuple[float, float]) -> Optional[tuple[float, float]]:
        """Map a point from camera space to screen space using homography."""
        if self._homography is None:
            return None
        pt = np.array([[point]], dtype=np.float32)
        mapped = cv2.perspectiveTransform(pt, self._homography)
        return tuple(mapped[0][0])

    def map_points(self, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """Map multiple points from camera space to screen space."""
        if self._homography is None or not points:
            return []
        pts = np.array([points], dtype=np.float32)
        mapped = cv2.perspectiveTransform(pts, self._homography)
        return [tuple(p) for p in mapped[0]]

    def is_running(self) -> bool:
        return self._running

    def get_camera_info(self) -> dict[str, Any]:
        """Get camera information."""
        if not self._cap:
            return {"opened": False}
        return {
            "opened": True,
            "width": int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": self._cap.get(cv2.CAP_PROP_FPS),
            "index": self.camera_index,
        }


class PortalCalibrator:
    """Calibration utilities for camera-to-screen/projector mapping."""

    def __init__(self, tracker: HandTracker):
        self.tracker = tracker
        self._calibration_points_src: list[tuple[float, float]] = []
        self._calibration_points_dst: list[tuple[float, float]] = []

    def auto_calibrate_from_hands(
        self, screen_width: int, screen_height: int, num_samples: int = 30
    ) -> Optional[np.ndarray]:
        """
        Auto-calibrate using hand positions.
        Assumes user moves hand to screen corners in order: TL, TR, BR, BL.
        """
        logger.info("Starting auto-calibration. Move hand to 4 screen corners...")
        corners = [
            (0, 0),
            (screen_width, 0),
            (screen_width, screen_height),
            (0, screen_height),
        ]

        src_points = []
        dst_points = []

        for i, (sx, sy) in enumerate(corners):
            logger.info(f"Corner {i+1}/4: Move hand to ({sx}, {sy}) and hold still")
            # Wait for stable hand detection at this corner
            samples = []
            while len(samples) < num_samples:
                frame = self.tracker.get_latest_frame()
                if frame and frame.hands:
                    # Use the first detected hand's palm center
                    hand = frame.hands[0]
                    samples.append(hand.center)
                time.sleep(0.05)

            # Average the samples
            avg_x = sum(p[0] for p in samples) / len(samples)
            avg_y = sum(p[1] for p in samples) / len(samples)
            src_points.append((avg_x, avg_y))
            dst_points.append((float(sx), float(sy)))
            logger.info(f"  Captured: camera=({avg_x:.1f}, {avg_y:.1f}) -> screen=({sx}, {sy})")

        # Compute homography
        src = np.array(src_points, dtype=np.float32)
        dst = np.array(dst_points, dtype=np.float32)
        homography, _ = cv2.findHomography(src, dst)

        if homography is not None:
            self.tracker.set_homography(homography)
            logger.info("Auto-calibration complete")
            return homography

        logger.error("Auto-calibration failed: could not compute homography")
        return None

    def manual_calibrate(
        self, screen_width: int, screen_height: int
    ) -> Optional[np.ndarray]:
        """Manual 4-point calibration by clicking on the camera feed."""
        logger.info("Manual calibration: Click 4 corners on camera feed (TL, TR, BR, BL)")

        corners = [
            (0, 0),
            (screen_width, 0),
            (screen_width, screen_height),
            (0, screen_height),
        ]

        src_points = []
        dst_points = []

        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN and len(src_points) < 4:
                src_points.append((float(x), float(y)))
                dst_points.append(corners[len(src_points) - 1])
                logger.info(f"  Point {len(src_points)}: camera=({x}, {y}) -> screen={dst_points[-1]}")

        cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
        cv2.setMouseCallback("Calibration", mouse_callback)

        while len(src_points) < 4:
            frame = self.tracker.get_latest_frame()
            if frame:
                display = frame.frame.copy()
                # Draw instructions
                cv2.putText(
                    display,
                    f"Click corner {len(src_points)+1}/4: {['TL','TR','BR','BL'][len(src_points)]}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 255),
                    2,
                )
                # Draw existing points
                for i, (px, py) in enumerate(src_points):
                    cv2.circle(display, (int(px), int(py)), 10, (0, 255, 0), -1)
                    cv2.putText(
                        display,
                        str(i+1),
                        (int(px)+15, int(py)+5),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (0, 255, 0),
                        2,
                    )
                cv2.imshow("Calibration", display)
            if cv2.waitKey(30) & 0xFF == 27:  # ESC to cancel
                break

        cv2.destroyWindow("Calibration")

        if len(src_points) == 4:
            src = np.array(src_points, dtype=np.float32)
            dst = np.array(dst_points, dtype=np.float32)
            homography, _ = cv2.findHomography(src, dst)
            if homography is not None:
                self.tracker.set_homography(homography)
                logger.info("Manual calibration complete")
                return homography

        logger.error("Manual calibration cancelled or failed")
        return None

    def checkerboard_calibrate(
        self, screen_width: int, screen_height: int, pattern_size: tuple[int, int] = (9, 6)
    ) -> Optional[np.ndarray]:
        """Calibrate using OpenCV chessboard pattern detection."""
        logger.info("Checkerboard calibration: Show chessboard to camera")

        objp = np.zeros((pattern_size[0] * pattern_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0:pattern_size[0], 0:pattern_size[1]].T.reshape(-1, 2)

        objpoints = []
        imgpoints = []

        cv2.namedWindow("Checkerboard Calibration", cv2.WINDOW_NORMAL)

        while len(objpoints) < 10:
            frame = self.tracker.get_latest_frame()
            if not frame:
                continue

            gray = cv2.cvtColor(frame.frame, cv2.COLOR_BGR2GRAY)
            ret, corners = cv2.findChessboardCorners(gray, pattern_size, None)

            display = frame.frame.copy()
            if ret:
                corners_refined = cv2.cornerSubPix(
                    gray, corners, (11, 11), (-1, -1),
                    (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                )
                cv2.drawChessboardCorners(display, pattern_size, corners_refined, ret)
                cv2.putText(
                    display,
                    f"Detected! Press SPACE to capture ({len(objpoints)+1}/10)",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )
                key = cv2.waitKey(30) & 0xFF
                if key == ord(' '):
                    objpoints.append(objp)
                    imgpoints.append(corners_refined)
                    logger.info(f"  Captured sample {len(objpoints)}/10")
            else:
                cv2.putText(
                    display,
                    "Show chessboard to camera, press SPACE when detected",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                )
                cv2.waitKey(30)

            cv2.imshow("Checkerboard Calibration", display)

        cv2.destroyWindow("Checkerboard Calibration")

        if len(objpoints) >= 5:
            # Calibrate camera
            ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
                objpoints, imgpoints, gray.shape[::-1], None, None
            )

            # For projector mapping, we'd need screen corners in world coords
            # This is a simplified version - in practice you'd need the screen corners
            logger.info("Camera intrinsic calibration complete")
            logger.warning("Checkerboard method needs screen corner correspondences for full homography")
            return mtx

        return None

    def save_calibration(self, profile_name: str, homography: np.ndarray) -> bool:
        """Save calibration profile to disk."""
        import json
        from pathlib import Path

        config_dir = Path.home() / ".config" / "portal_engine"
        config_dir.mkdir(parents=True, exist_ok=True)

        profile_file = config_dir / f"{profile_name}.json"
        data = {
            "homography": homography.tolist(),
            "camera_index": self.tracker.camera_index,
        }

        try:
            with open(profile_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Calibration saved to {profile_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save calibration: {e}")
            return False

    def load_calibration(self, profile_name: str) -> Optional[np.ndarray]:
        """Load calibration profile from disk."""
        import json
        from pathlib import Path

        profile_file = Path.home() / ".config" / "portal_engine" / f"{profile_name}.json"

        if not profile_file.exists():
            logger.warning(f"Calibration profile '{profile_name}' not found")
            return None

        try:
            with open(profile_file) as f:
                data = json.load(f)
            homography = np.array(data["homography"], dtype=np.float32)
            self.tracker.set_homography(homography)
            logger.info(f"Calibration loaded from {profile_file}")
            return homography
        except Exception as e:
            logger.error(f"Failed to load calibration: {e}")
            return None
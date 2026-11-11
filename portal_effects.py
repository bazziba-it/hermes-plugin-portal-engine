"""Visual effects for portal-engine — glowing hands, portal rings, pass-through effects."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Optional

import cv2
import numpy as np

from .portal_tracker import Hand, PortalFrame


@dataclass
class EffectConfig:
    """Configuration for visual effects."""
    intensity: float = 1.0
    show_fps: bool = True
    portal_color: tuple[int, int, int] = (0, 255, 255)  # Cyan
    glow_color: tuple[int, int, int] = (255, 100, 255)  # Magenta
    particle_color: tuple[int, int, int] = (255, 255, 100)  # Yellow


class Particle:
    """Single particle for particle effects."""
    def __init__(self, x: float, y: float, vx: float, vy: float, life: float, color: tuple[int, int, int], size: float):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.color = color
        self.size = size

    def update(self, dt: float) -> bool:
        """Update particle. Returns True if still alive."""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += 50 * dt  # Gravity
        self.life -= dt
        return self.life > 0

    def draw(self, frame: np.ndarray) -> None:
        """Draw particle on frame."""
        if self.life <= 0:
            return
        alpha = self.life / self.max_life
        size = max(1, int(self.size * alpha))
        color = tuple(int(c * alpha) for c in self.color)
        cv2.circle(frame, (int(self.x), int(self.y)), size, color, -1)


class PortalEffects:
    """Renders portal visual effects on tracked frames."""

    def __init__(self, config: Optional[EffectConfig] = None):
        self.config = config or EffectConfig()
        self._particles: list[Particle] = []
        self._last_time = time.time()
        self._frame_count = 0
        self._portal_rings: list[dict] = []
        self._hand_trails: dict[str, list[tuple[float, float]]] = {}

    def process(self, portal_frame: PortalFrame, effect_mode: str = "all") -> np.ndarray:
        """Apply effects to a portal frame and return the output frame."""
        frame = portal_frame.frame.copy()
        h, w = frame.shape[:2]

        now = time.time()
        dt = now - self._last_time
        self._last_time = now

        # Update and draw particles
        self._update_particles(dt, frame)

        # Process each detected hand
        for hand in portal_frame.hands:
            hand_id = f"{hand.handedness}_{id(hand)}"

            if effect_mode in ("glowing_hands", "all"):
                self._draw_glowing_hand(frame, hand)

            if effect_mode in ("portal_rings", "all"):
                self._draw_portal_rings(frame, hand, now)

            if effect_mode in ("pass_through", "all"):
                self._draw_pass_through(frame, hand, w, h)

            if effect_mode in ("particles", "all"):
                self._spawn_particles(hand)
                self._update_hand_trail(hand_id, hand.center)

        # Draw hand trails
        self._draw_hand_trails(frame)

        # Draw FPS counter
        if self.config.show_fps:
            self._draw_fps(frame, portal_frame.fps)

        self._frame_count += 1
        return frame

    def _draw_glowing_hand(self, frame: np.ndarray, hand: Hand) -> None:
        """Draw glowing hand outline with pulse effect."""
        # Palm center
        cx, cy = hand.center

        # Pulsing glow radius
        pulse = 1.0 + 0.3 * math.sin(time.time() * 4)
        base_radius = 40 * self.config.intensity
        glow_radius = int(base_radius * pulse)

        # Multi-layer glow for bloom effect
        for i in range(5):
            radius = glow_radius + i * 8
            alpha = 0.15 * (1.0 - i * 0.15) * self.config.intensity
            color = tuple(int(c * alpha) for c in self.config.glow_color)
            overlay = frame.copy()
            cv2.circle(overlay, (int(cx), int(cy)), radius, color, -1)
            cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # Draw hand skeleton with glow
        self._draw_hand_skeleton(frame, hand, self.config.glow_color)

        # Fingertip highlights
        self._draw_fingertips(frame, hand)

    def _draw_hand_skeleton(self, frame: np.ndarray, hand: Hand, color: tuple[int, int, int]) -> None:
        """Draw hand bone connections."""
        # MediaPipe hand connections
        connections = [
            (0, 1), (1, 2), (2, 3), (3, 4),        # Thumb
            (0, 5), (5, 6), (6, 7), (7, 8),        # Index
            (5, 9), (9, 10), (10, 11), (11, 12),   # Middle
            (9, 13), (13, 14), (14, 15), (15, 16), # Ring
            (13, 17), (17, 18), (18, 19), (19, 20),# Pinky
            (0, 17),                                # Palm base
        ]

        intensity = self.config.intensity
        for start_idx, end_idx in connections:
            if start_idx < len(hand.landmarks) and end_idx < len(hand.landmarks):
                p1 = hand.landmarks[start_idx]
                p2 = hand.landmarks[end_idx]
                pt1 = (int(p1.x), int(p1.y))
                pt2 = (int(p2.x), int(p2.y))
                cv2.line(frame, pt1, pt2, color, max(1, int(3 * intensity)))

    def _draw_fingertips(self, frame: np.ndarray, hand: Hand) -> None:
        """Draw bright dots at fingertips."""
        # Fingertip indices: thumb=4, index=8, middle=12, ring=16, pinky=20
        fingertips = [4, 8, 12, 16, 20]
        for idx in fingertips:
            if idx < len(hand.landmarks):
                lm = hand.landmarks[idx]
                cv2.circle(frame, (int(lm.x), int(lm.y)), 8, (255, 255, 255), -1)
                cv2.circle(frame, (int(lm.x), int(lm.y)), 5, self.config.glow_color, -1)

    def _draw_portal_rings(self, frame: np.ndarray, hand: Hand, now: float) -> None:
        """Draw expanding portal rings at hand position."""
        cx, cy = hand.center

        # Create new rings periodically
        if len(self._portal_rings) < 3 and self._frame_count % 15 == 0:
            self._portal_rings.append({
                "x": cx,
                "y": cy,
                "radius": 20,
                "max_radius": 200 * self.config.intensity,
                "born": now,
                "color": self.config.portal_color,
            })

        # Update and draw rings
        new_rings = []
        for ring in self._portal_rings:
            age = now - ring["born"]
            ring["radius"] = 20 + age * 150 * self.config.intensity
            alpha = max(0, 1.0 - age / 2.0)

            if alpha > 0:
                color = tuple(int(c * alpha) for c in ring["color"])
                cv2.circle(
                    frame,
                    (int(ring["x"]), int(ring["y"])),
                    int(ring["radius"]),
                    color,
                    max(1, int(3 * alpha * self.config.intensity)),
                )
                # Inner glow
                cv2.circle(
                    frame,
                    (int(ring["x"]), int(ring["y"])),
                    int(ring["radius"] * 0.9),
                    tuple(int(c * alpha * 0.3) for c in ring["color"]),
                    1,
                )
                new_rings.append(ring)

        self._portal_rings = new_rings

    def _draw_pass_through(self, frame: np.ndarray, hand: Hand, w: int, h: int) -> None:
        """Draw portal pass-through effect — hand appears to reach through."""
        cx, cy = hand.center

        # Portal rectangle centered on hand
        portal_w = int(300 * self.config.intensity)
        portal_h = int(400 * self.config.intensity)

        x1 = max(0, int(cx - portal_w // 2))
        y1 = max(0, int(cy - portal_h // 2))
        x2 = min(w, int(cx + portal_w // 2))
        y2 = min(h, int(cy + portal_h // 2))

        # Draw portal frame
        color = self.config.portal_color
        thickness = max(2, int(4 * self.config.intensity))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        # Corner brackets for sci-fi look
        bracket_len = 30
        for (bx, by) in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
            if bx == x1:
                cv2.line(frame, (bx, by), (bx + bracket_len, by), color, thickness)
                cv2.line(frame, (bx, by), (bx, by + bracket_len if by == y1 else by - bracket_len), color, thickness)
            else:
                cv2.line(frame, (bx, by), (bx - bracket_len, by), color, thickness)
                cv2.line(frame, (bx, by), (bx, by + bracket_len if by == y1 else by - bracket_len), color, thickness)

        # Scanlines inside portal
        for y in range(y1, y2, 4):
            alpha = 0.1 * self.config.intensity
            overlay = frame.copy()
            cv2.line(overlay, (x1, y), (x2, y), color, 1)
            cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        # "Depth" indicator - concentric rects
        for i in range(3):
            inset = (i + 1) * 10
            xi1, yi1 = x1 + inset, y1 + inset
            xi2, yi2 = x2 - inset, y2 - inset
            if xi1 < xi2 and yi1 < yi2:
                alpha = 0.05 * (3 - i) * self.config.intensity
                overlay = frame.copy()
                cv2.rectangle(overlay, (xi1, yi1), (xi2, yi2), color, 1)
                cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    def _spawn_particles(self, hand: Hand) -> None:
        """Spawn particles from fingertips."""
        if len(self._particles) > 200:
            return

        fingertips = [4, 8, 12, 16, 20]
        for idx in fingertips:
            if idx < len(hand.landmarks):
                lm = hand.landmarks[idx]
                # Spawn 1-2 particles per fingertip per frame
                if np.random.random() < 0.3 * self.config.intensity:
                    angle = np.random.uniform(0, 2 * math.pi)
                    speed = np.random.uniform(50, 150)
                    self._particles.append(Particle(
                        x=lm.x,
                        y=lm.y,
                        vx=math.cos(angle) * speed,
                        vy=math.sin(angle) * speed - 100,  # Upward bias
                        life=np.random.uniform(0.5, 1.5),
                        color=self.config.particle_color,
                        size=np.random.uniform(2, 6) * self.config.intensity,
                    ))

    def _update_particles(self, dt: float, frame: np.ndarray) -> None:
        """Update and draw all particles."""
        alive = []
        for p in self._particles:
            if p.update(dt):
                p.draw(frame)
                alive.append(p)
        self._particles = alive

    def _update_hand_trail(self, hand_id: str, center: tuple[float, float]) -> None:
        """Update hand position trail."""
        if hand_id not in self._hand_trails:
            self._hand_trails[hand_id] = []
        trail = self._hand_trails[hand_id]
        trail.append(center)
        # Keep last 30 positions
        if len(trail) > 30:
            trail.pop(0)

    def _draw_hand_trails(self, frame: np.ndarray) -> None:
        """Draw trailing effect behind hands."""
        for hand_id, trail in self._hand_trails.items():
            if len(trail) < 2:
                continue
            for i in range(1, len(trail)):
                alpha = i / len(trail) * 0.5 * self.config.intensity
                color = tuple(int(c * alpha) for c in self.config.glow_color)
                pt1 = (int(trail[i-1][0]), int(trail[i-1][1]))
                pt2 = (int(trail[i][0]), int(trail[i][1]))
                thickness = max(1, int(4 * alpha))
                cv2.line(frame, pt1, pt2, color, thickness)

    def _draw_fps(self, frame: np.ndarray, fps: float) -> None:
        """Draw FPS counter."""
        text = f"FPS: {fps:.1f}"
        cv2.putText(
            frame, text, (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2
        )

    def reset(self) -> None:
        """Reset all effect state."""
        self._particles.clear()
        self._portal_rings.clear()
        self._hand_trails.clear()
        self._last_time = time.time()
        self._frame_count = 0


def create_portal_window(
    name: str = "Portal Engine",
    width: int = 1920,
    height: int = 1080,
    fullscreen: bool = True,
    monitor: int = 0,
) -> bool:
    """Create and configure the portal display window."""
    cv2.namedWindow(name, cv2.WINDOW_NORMAL)

    if fullscreen:
        cv2.setWindowProperty(name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        cv2.resizeWindow(name, width, height)

    # Try to position on specific monitor (limited support in OpenCV)
    # On X11/Wayland, this may need wmctrl or similar
    return True
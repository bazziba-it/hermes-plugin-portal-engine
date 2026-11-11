"""Syphon/Spout/NDI/Virtual Camera output bridge for portal-engine.

Supports multiple output protocols:
- NDI (cross-platform, professional) — requires `pip install ndi-python` or `pip install PyNDI`
- Spout (Windows) — requires `pip install spout-gl` 
- Syphon (macOS) — requires `pip install syphon`
- Virtual Camera (Linux v4l2loopback) — requires `pip install pyvirtualcam` + loading the v4l2loopback kernel module
- Shared Memory (local apps) — pure Python, no extra deps
"""

from __future__ import annotations

import logging
import platform
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OutputConfig:
    server_name: str = "PortalEngine"
    protocol: str = "auto"  # auto, ndi, spout, syphon, virtual_camera, shared_memory
    width: int = 1920
    height: int = 1080
    fps: int = 30
    include_alpha: bool = True


class OutputSender(ABC):
    """Abstract base for output senders."""

    def __init__(self, config: OutputConfig):
        self.config = config
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

    @abstractmethod
    def start(self) -> bool:
        """Initialize and start sender. Returns True on success."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop sender and clean up."""
        pass

    @abstractmethod
    def send_frame(self, frame: np.ndarray) -> bool:
        """Send a frame. Returns True on success."""
        pass

    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> dict[str, Any]:
        return {
            "protocol": self.__class__.__name__,
            "running": self._running,
            "config": {
                "server_name": self.config.server_name,
                "width": self.config.width,
                "height": self.config.height,
                "fps": self.config.fps,
            }
        }


class SharedMemorySender(OutputSender):
    """Shared memory sender for local apps (zero-copy via numpy arrays in multiprocessing).

    Other Python processes can access frames via the shared memory name.
    """

    def __init__(self, config: OutputConfig):
        super().__init__(config)
        self._shm = None
        self._shm_name = f"portal_engine_{config.server_name}"

    def start(self) -> bool:
        try:
            from multiprocessing import shared_memory

            # Calculate buffer size (RGBA)
            channels = 4 if self.config.include_alpha else 3
            buffer_size = self.config.width * self.config.height * channels

            # Create or connect to shared memory
            try:
                self._shm = shared_memory.SharedMemory(
                    name=self._shm_name,
                    create=True,
                    size=buffer_size
                )
            except FileExistsError:
                # Already exists, connect to it
                self._shm = shared_memory.SharedMemory(name=self._shm_name)

            self._running = True
            logger.info(f"SharedMemory sender started: {self._shm_name} ({self.config.width}x{self.config.height})")
            return True
        except Exception as e:
            logger.error(f"SharedMemory sender failed: {e}")
            return False

    def stop(self) -> None:
        self._running = False
        if self._shm:
            try:
                self._shm.close()
                self._shm.unlink()
            except Exception:
                pass
            self._shm = None
        logger.info("SharedMemory sender stopped")

    def send_frame(self, frame: np.ndarray) -> bool:
        if not self._running or not self._shm:
            return False

        try:
            # Ensure frame is correct size and format
            if frame.shape[0] != self.config.height or frame.shape[1] != self.config.width:
                frame = cv2.resize(frame, (self.config.width, self.config.height))

            # Convert to RGBA if needed
            if self.config.include_alpha and frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
            elif not self.config.include_alpha and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # Write to shared memory (numpy view)
            channels = 4 if self.config.include_alpha else 3
            expected_size = self.config.width * self.config.height * channels
            if frame.nbytes != expected_size:
                # Handle stride issues
                frame = np.ascontiguousarray(frame)

            # Copy to shared memory buffer
            dst = np.ndarray(
                (self.config.height, self.config.width, channels),
                dtype=np.uint8,
                buffer=self._shm.buf
            )
            np.copyto(dst, frame)
            return True
        except Exception as e:
            logger.debug(f"SharedMemory send_frame error: {e}")
            return False


class VirtualCameraSender(OutputSender):
    """Virtual camera sender using pyvirtualcam (Linux v4l2loopback)."""

    def __init__(self, config: OutputConfig):
        super().__init__(config)
        self._cam = None

    def start(self) -> bool:
        try:
            import pyvirtualcam

            self._cam = pyvirtualcam.Camera(
                width=self.config.width,
                height=self.config.height,
                fps=self.config.fps,
                fmt=pyvirtualcam.PixelFormat.BGR,
                device=f"/dev/video{self._find_virtual_device()}",
                print_fps=False
            )
            self._running = True
            logger.info(f"VirtualCamera sender started: {self._cam.device} ({self.config.width}x{self.config.height}@{self.config.fps}fps)")
            return True
        except ImportError:
            logger.error("pyvirtualcam not installed. Run: pip install pyvirtualcam")
            logger.error("Also load the v4l2loopback kernel module as root: modprobe v4l2loopback devices=1 video_nr=10 card_label='PortalEngine' exclusive_caps=1")
            return False
        except Exception as e:
            logger.error(f"VirtualCamera sender failed: {e}")
            logger.error("Ensure the v4l2loopback kernel module is loaded: modprobe v4l2loopback")
            return False

    def _find_virtual_device(self) -> int:
        # Try to find a v4l2loopback device
        for i in range(10, 20):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cap.release()
                return i
        return 10  # Default

    def stop(self) -> None:
        self._running = False
        if self._cam:
            try:
                self._cam.close()
            except Exception:
                pass
            self._cam = None
        logger.info("VirtualCamera sender stopped")

    def send_frame(self, frame: np.ndarray) -> bool:
        if not self._running or not self._cam:
            return False

        try:
            if frame.shape[0] != self.config.height or frame.shape[1] != self.config.width:
                frame = cv2.resize(frame, (self.config.width, self.config.height))

            # pyvirtualcam expects BGR
            if frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            self._cam.send(frame)
            self._cam.sleep_until_next_frame()
            return True
        except Exception as e:
            logger.debug(f"VirtualCamera send_frame error: {e}")
            return False


class NDISender(OutputSender):
    """NDI sender for cross-platform professional video transport."""

    def __init__(self, config: OutputConfig):
        super().__init__(config)
        self._ndi_send = None
        self._ndi_lib = None

    def start(self) -> bool:
        # Try multiple NDI Python bindings
        for lib_name in ("ndi", "PyNDI", "ndi-python"):
            try:
                self._ndi_lib = __import__(lib_name)
                break
            except ImportError:
                continue

        if not self._ndi_lib:
            logger.error("NDI not available. Install: pip install ndi-python  (or PyNDI, ndi-python)")
            return False

        try:
            # Initialize NDI
            if not self._ndi_lib.initialize():
                logger.error("NDI initialization failed")
                return False

            # Create sender
            send_settings = self._ndi_lib.SendCreate()
            send_settings.ndi_name = self.config.server_name
            send_settings.clock_video = True
            send_settings.clock_audio = False

            self._ndi_send = self._ndi_lib.send_create(send_settings)
            if not self._ndi_send:
                logger.error("NDI sender creation failed")
                return False

            self._running = True
            logger.info(f"NDI sender started: {self.config.server_name}")
            return True
        except Exception as e:
            logger.error(f"NDI sender failed: {e}")
            return False

    def stop(self) -> None:
        self._running = False
        if self._ndi_send and self._ndi_lib:
            try:
                self._ndi_lib.send_destroy(self._ndi_send)
            except Exception:
                pass
        if self._ndi_lib:
            try:
                self._ndi_lib.destroy()
            except Exception:
                pass
        self._ndi_send = None
        logger.info("NDI sender stopped")

    def send_frame(self, frame: np.ndarray) -> bool:
        if not self._running or not self._ndi_send or not self._ndi_lib:
            return False

        try:
            if frame.shape[0] != self.config.height or frame.shape[1] != self.config.width:
                frame = cv2.resize(frame, (self.config.width, self.config.height))

            # NDI expects BGRA or BGR
            if self.config.include_alpha and frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
            elif not self.config.include_alpha and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # Create NDI frame
            video_frame = self._ndi_lib.VideoFrameV2()
            video_frame.width = self.config.width
            video_frame.height = self.config.height
            video_frame.fourcc = self._ndi_lib.FOURCC_VIDEO_TYPE_BGRA if self.config.include_alpha else self._ndi_lib.FOURCC_VIDEO_TYPE_BGR
            video_frame.frame_rate_N = self.config.fps
            video_frame.frame_rate_D = 1
            video_frame.p_data = frame.ctypes.data_as(self._ndi_lib.c_void_p)
            video_frame.line_stride_in_bytes = frame.strides[0]

            self._ndi_lib.send_send_video_v2(self._ndi_send, video_frame)
            return True
        except Exception as e:
            logger.debug(f"NDI send_frame error: {e}")
            return False


class SpoutSender(OutputSender):
    """Spout sender for Windows (via spout-gl)."""

    def __init__(self, config: OutputConfig):
        super().__init__(config)
        self._sender = None

    def start(self) -> bool:
        if platform.system() != "Windows":
            logger.error("Spout only available on Windows")
            return False

        try:
            import spout

            self._sender = spout.SpoutSender()
            if not self._sender.CreateSender(self.config.server_name, self.config.width, self.config.height):
                logger.error(f"Spout sender creation failed for {self.config.server_name}")
                return False

            self._running = True
            logger.info(f"Spout sender started: {self.config.server_name}")
            return True
        except ImportError:
            logger.error("spout-gl not installed. Run: pip install spout-gl")
            return False
        except Exception as e:
            logger.error(f"Spout sender failed: {e}")
            return False

    def stop(self) -> None:
        self._running = False
        if self._sender:
            try:
                self._sender.ReleaseSender()
            except Exception:
                pass
            self._sender = None
        logger.info("Spout sender stopped")

    def send_frame(self, frame: np.ndarray) -> bool:
        if not self._running or not self._sender:
            return False

        try:
            if frame.shape[0] != self.config.height or frame.shape[1] != self.config.width:
                frame = cv2.resize(frame, (self.config.width, self.config.height))

            # Spout expects BGR or BGRA
            if self.config.include_alpha and frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
            elif not self.config.include_alpha and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # Send via Spout (uses OpenGL texture sharing)
            success = self._sender.SendImage(
                frame.ctypes.data_as(ctypes.c_void_p),
                self.config.width,
                self.config.height,
                ctypes.c_int(4 if self.config.include_alpha else 3),
                False  # bInvert
            )
            return bool(success)
        except Exception as e:
            logger.debug(f"Spout send_frame error: {e}")
            return False


class SyphonSender(OutputSender):
    """Syphon sender for macOS (via pySyphon or metal)."""

    def __init__(self, config: OutputConfig):
        super().__init__(config)
        self._server = None

    def start(self) -> bool:
        if platform.system() != "Darwin":
            logger.error("Syphon only available on macOS")
            return False

        try:
            # Try pySyphon first
            import syphon
            self._server = syphon.SyphonServer(self.config.server_name)
            self._running = True
            logger.info(f"Syphon sender started: {self.config.server_name}")
            return True
        except ImportError:
            try:
                # Try metal-capture approach
                import metal
                # Metal-based Syphon implementation would go here
                logger.warning("pySyphon not installed. Run: pip install syphon")
                return False
            except ImportError:
                logger.error("Syphon not available. Install: pip install syphon")
                return False
        except Exception as e:
            logger.error(f"Syphon sender failed: {e}")
            return False

    def stop(self) -> None:
        self._running = False
        if self._server:
            try:
                self._server.stop()
            except Exception:
                pass
            self._server = None
        logger.info("Syphon sender stopped")

    def send_frame(self, frame: np.ndarray) -> bool:
        if not self._running or not self._server:
            return False

        try:
            if frame.shape[0] != self.config.height or frame.shape[1] != self.config.width:
                frame = cv2.resize(frame, (self.config.width, self.config.height))

            if self.config.include_alpha and frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
            elif not self.config.include_alpha and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # Send via Syphon (uses IOSurface/Metal texture sharing)
            self._server.publish_frame(frame)
            return True
        except Exception as e:
            logger.debug(f"Syphon send_frame error: {e}")
            return False


def create_sender(config: OutputConfig) -> OutputSender:
    """Factory function to create the appropriate sender based on protocol and platform.
    
    Tries protocols in platform-preferred order, falling back if not installed.
    """
    system = platform.system().lower()

    # Define protocol preference order per platform
    PROTOCOL_PREFERENCE = {
        "darwin": ["syphon", "ndi", "shared_memory"],      # macOS: Syphon > NDI > shared memory
        "windows": ["spout", "ndi", "shared_memory"],      # Windows: Spout > NDI > shared memory
        "linux": ["ndi", "virtual_camera", "shared_memory"],  # Linux: NDI > virtual cam > shared memory
    }

    # Auto-detect: try preferred protocols in order until one works
    if config.protocol == "auto":
        for proto in PROTOCOL_PREFERENCE.get(system, ["shared_memory"]):
            if _protocol_available(proto, system):
                config.protocol = proto
                logger.info(f"Auto-selected output protocol: {proto}")
                break
        else:
            config.protocol = "shared_memory"
            logger.warning("No preferred protocols available, falling back to shared_memory")

    # Create sender based on protocol
    sender = _create_sender_for_protocol(config.protocol, config)
    if sender:
        return sender

    # Fallback chain: try other available protocols
    logger.warning(f"Failed to create {config.protocol} sender, trying fallbacks...")
    for proto in PROTOCOL_PREFERENCE.get(system, []):
        if proto == config.protocol:
            continue
        if _protocol_available(proto, system):
            sender = _create_sender_for_protocol(proto, config)
            if sender:
                config.protocol = proto
                logger.info(f"Fell back to: {proto}")
                return sender

    # Last resort: shared memory (always works)
    logger.warning("All protocols failed, using shared_memory fallback")
    return SharedMemorySender(config)


def _protocol_available(protocol: str, system: str) -> bool:
    """Check if a protocol is available on this system."""
    if protocol == "shared_memory":
        return True
    elif protocol == "ndi":
        for lib in ("ndi", "PyNDI", "ndi-python"):
            try:
                __import__(lib)
                return True
            except ImportError:
                continue
        return False
    elif protocol == "spout":
        return system == "windows"
    elif protocol == "syphon":
        return system == "darwin"
    elif protocol == "virtual_camera":
        return system == "linux"
    return False


def _create_sender_for_protocol(protocol: str, config: OutputConfig) -> Optional[OutputSender]:
    """Create sender for specific protocol, returning None if unavailable."""
    try:
        if protocol == "ndi":
            return NDISender(config)
        elif protocol == "spout":
            return SpoutSender(config)
        elif protocol == "syphon":
            return SyphonSender(config)
        elif protocol == "virtual_camera":
            return VirtualCameraSender(config)
        elif protocol == "shared_memory":
            return SharedMemorySender(config)
    except Exception as e:
        logger.debug(f"Failed to create {protocol} sender: {e}")
    return None


def list_available_protocols() -> dict[str, bool]:
    """Check which output protocols are available on this system."""
    system = platform.system().lower()
    available = {}

    # Shared memory always available
    available["shared_memory"] = True

    # NDI
    for lib in ("ndi", "PyNDI", "ndi-python"):
        try:
            __import__(lib)
            available["ndi"] = True
            break
        except ImportError:
            continue
    else:
        available["ndi"] = False

    # Spout (Windows only)
    if system == "windows":
        try:
            import spout
            available["spout"] = True
        except ImportError:
            available["spout"] = False
    else:
        available["spout"] = False

    # Syphon (macOS only)
    if system == "darwin":
        try:
            import syphon
            available["syphon"] = True
        except ImportError:
            available["syphon"] = False
    else:
        available["syphon"] = False

    # Virtual camera (Linux with v4l2loopback)
    if system == "linux":
        try:
            import pyvirtualcam
            available["virtual_camera"] = True
        except ImportError:
            available["virtual_camera"] = False
    else:
        available["virtual_camera"] = False

    return available
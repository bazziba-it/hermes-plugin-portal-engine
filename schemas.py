"""JSON schemas for portal-engine tools."""

PORTAL_START_SCHEMA = {
    "type": "object",
    "properties": {
        "camera_index": {
            "type": "integer",
            "default": 0,
            "description": "Camera index to use (0 = built-in, 1+ = external USB/IP cameras)"
        },
        "effect_mode": {
            "type": "string",
            "enum": ["glowing_hands", "portal_rings", "pass_through", "particles", "all"],
            "default": "all",
            "description": "Visual effect mode to enable"
        },
        "fullscreen": {
            "type": "boolean",
            "default": True,
            "description": "Run in fullscreen mode (use secondary display if projector mode enabled)"
        },
        "mirror": {
            "type": "boolean",
            "default": True,
            "description": "Mirror the camera feed horizontally (natural for webcam)"
        },
        "detection_confidence": {
            "type": "number",
            "default": 0.7,
            "minimum": 0.1,
            "maximum": 1.0,
            "description": "MediaPipe hand detection confidence threshold"
        },
        "tracking_confidence": {
            "type": "number",
            "default": 0.5,
            "minimum": 0.1,
            "maximum": 1.0,
            "description": "MediaPipe hand tracking confidence threshold"
        },
        "max_hands": {
            "type": "integer",
            "default": 2,
            "minimum": 1,
            "maximum": 4,
            "description": "Maximum number of hands to track simultaneously"
        }
    },
    "required": []
}

PORTAL_STOP_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": []
}

PORTAL_CALIBRATE_SCHEMA = {
    "type": "object",
    "properties": {
        "method": {
            "type": "string",
            "enum": ["auto", "manual", "checkerboard"],
            "default": "auto",
            "description": "Calibration method: auto (hand-based), manual (click 4 corners), checkerboard (OpenCV chessboard)"
        },
        "screen_width": {
            "type": "integer",
            "default": 1920,
            "description": "Target screen/projector width in pixels"
        },
        "screen_height": {
            "type": "integer",
            "default": 1080,
            "description": "Target screen/projector height in pixels"
        },
        "save_profile": {
            "type": "string",
            "default": "default",
            "description": "Profile name to save calibration data"
        }
    },
    "required": []
}

PORTAL_STATUS_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": []
}

PORTAL_LIST_CAMERAS_SCHEMA = {
    "type": "object",
    "properties": {
        "max_test": {
            "type": "integer",
            "default": 10,
            "description": "Maximum camera indices to test"
        }
    },
    "required": []
}

PORTAL_SYPHON_START_SCHEMA = {
    "type": "object",
    "properties": {
        "server_name": {
            "type": "string",
            "default": "PortalEngine",
            "description": "Syphon/Spout/NDI server name (appears in MadMapper, Resolume, etc.)"
        },
        "protocol": {
            "type": "string",
            "enum": ["auto", "ndi", "spout", "syphon", "virtual_camera", "shared_memory"],
            "default": "auto",
            "description": "Output protocol: auto-detect, NDI (cross-platform), Spout (Windows), Syphon (macOS), virtual_camera (Linux v4l2loopback), shared_memory (local apps)"
        },
        "width": {
            "type": "integer",
            "default": 1920,
            "description": "Output width in pixels"
        },
        "height": {
            "type": "integer",
            "default": 1080,
            "description": "Output height in pixels"
        },
        "fps": {
            "type": "integer",
            "default": 30,
            "minimum": 1,
            "maximum": 60,
            "description": "Target FPS for output stream"
        },
        "include_alpha": {
            "type": "boolean",
            "default": True,
            "description": "Include alpha channel for transparency (portal effects on transparent background)"
        }
    },
    "required": []
}

PORTAL_SYPHON_STOP_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": []
}

PORTAL_SYPHON_STATUS_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": []
}
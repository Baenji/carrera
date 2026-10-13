"""
Configuration constants for the Carrera tracking system.
"""
import numpy as np

CAM_INDEX = 1

CAMERA_RESOLUTION = 'FHD'

# Resolution presets
RESOLUTIONS = {
    'HD': (1280, 720),
    'FHD': (1920, 1080),
    '4K': (3840, 2160),
}

# Color thresholds (HSV)
GREEN_LOW = np.array([65, 50, 80])
GREEN_HIGH = np.array([90, 180, 180])
YELLOW_LOW = np.array([25, 110, 50])
YELLOW_HIGH = np.array([35, 210, 150])

# Network settings
SIMULATION_IP = '127.0.0.1'
SIMULATION_PORT = 11360

# UI settings
MAIN_WINDOW_NAME = "Carrera divine vision"

DISPLAY_WINDOW_SIZE = (960, 540)  # Resize display to 720p for comfortable viewing

# AprilTag tracking settings
STABLE_TAG_FRAMES = 15

# Feature flags
TRACK_YELLOW = True
TRACK_VISUALIZATION_ENABLED = False
TRACK_VISUALIZATION_SIGNAL_RATE_FACTOR = 100.0
SHOW_TRACK_GRAPH = True

# Simulation settings
SIMULATION_CAR_SAMPLING_RATE = 5.0

# Auto-reset settings
AUTO_RESET_ENABLED = True
AUTO_RESET_THROTTLES = [40, 30, 25] # Main speed and then approach speed to the finish line during reset
AUTO_RESET_PROGRESS_THRESHOLD = [95.0, 99.9] # Progress need to stay in between here to consider reset complete
AUTO_RESET_TIMEOUT = 60.0
AUTO_RESET_WAIT_AT_START_DURATION = 1.5
AUTO_RESET_GRACE_PERIOD = 0.5 * 60 # FRAMES (60FPS) after a reset during which crash detection is disabled (to enable model training right after reset)

# AprilTag ID mapping
TAG_MAP = {
    1: "Start/Ziel",
    2: "kurze Gerade",
    3: "Mittlere Gerade",
    4: "Lange Gerade",
    5: "Kurve"
}

# Track parts enum for network protocol
PARTS = {
    'NONE': 0,
    'FINISH': 1,
    'SHORT_STRAIGHT': 2,
    'MEDIUM_STRAIGHT': 3,
    'LONG_STRAIGHT': 4,
    'RIGHT_CURVE': 5,
    'LEFT_CURVE': 6
}

# Mapping track names to PARTS enum
NAME_TO_PART = {
    'Start/Ziel': PARTS['FINISH'],
    'kurze Gerade': PARTS['SHORT_STRAIGHT'],
    'Mittlere Gerade': PARTS['MEDIUM_STRAIGHT'],
    'Lange Gerade': PARTS['LONG_STRAIGHT'],
    'Curve Rechts': PARTS['RIGHT_CURVE'],
    'Curve Links': PARTS['LEFT_CURVE']
}

# Global state (to be refactored later if needed)
last_signal_rate = 0

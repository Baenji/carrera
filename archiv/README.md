# DS-Carrera-v1

Computer vision and reinforcement learning system for tracking and controlling a Carrera slot car racing track.

## Architecture (Refactored v2.0)

The codebase has been refactored into a clean modular structure:

### Project Structure

```
DS-Carrera-v1/
├── quick_object_tracking.py   # Entry point (backward-compatible wrapper)
├── src/                        # Main application package
│   ├── config.py              # Configuration constants
│   ├── main.py                # Main application class
│   ├── camera/                # Camera initialization and color detection
│   │   ├── camera_manager.py  # Platform-specific camera setup
│   │   └── color_detector.py  # HSV-based car/reference tracking
│   ├── tracking/              # AprilTag detection and track mapping
│   │   ├── apriltag_detector.py  # AprilTag detection wrapper
│   │   ├── track_mapper.py      # Complex track order mapping algorithm
│   │   └── track_graph.py       # Progress calculation along track
│   ├── network/               # Simulation communication
│   │   └── network_client.py   # Non-blocking socket, JSON protocol, Arduino control
│   └── hardware/              # Hardware interfaces
│       └── arduino/           # Arduino serial communication
├── launcher/                  # Multi-component launcher
├── Documentation/             # Project documentation
├── arduino_geschwindigkeit_skaliert/  # Arduino firmware
├── simulator/                 # Godot simulator (untouched)
├── CarreraSimulator/          # Godot RL simulator (untouched)
└── archive/                   # Archived experimental code
    ├── Carrera/              # Old virtual environment
    ├── segmentation/         # Experimental segmentation approaches
    ├── camera_test.py        # Camera debugging utility
    └── carrera_anti_reflection.py  # Experimental track detection

```

### Module Responsibilities

- **src.config**: All configuration constants (camera settings, colors, network, tag mappings)
- **src.camera**: Platform-specific camera initialization and HSV color detection
- **src.tracking**: AprilTag detection, complex track mapping algorithm with visualization, progress calculation
- **src.network**: Non-blocking socket communication with Godot simulator, JSON protocol, Arduino signal control
- **src.hardware**: Arduino serial interface for controlling track components
- **src.main**: Main application orchestrator and event loop

### Running the Application

```bash
# Direct execution
python quick_object_tracking.py

# Or using the launcher for full system
cd launcher
python launcher.py
```

### Import as Module

```python
from src.camera import CarTracker
from src.tracking import TrackRecognizer, TrackGraph
from src.network import Network
from src.main import QuickObjectTrackingApp

# Or use the backward-compatible imports
from quick_object_tracking import CarTracker, TrackRecognizer, Network
```

## Features

- Real-time computer vision tracking using OpenCV
- AprilTag-based track layout recognition
- Automatic curve direction detection (left/right)
- Progress tracking around the circuit
- Non-blocking network communication with Godot simulator
- Arduino integration for hardware control
- Platform-specific camera support (Windows/macOS/Linux)
- Inline track mapping visualization

## Installation

### Quick Start

1. **Clone the repository**
```bash
git clone https://github.com/your-org/DS-Carrera-v1.git
cd DS-Carrera-v1
```

2. **Install the package** (recommended: use a virtual environment)
```bash
# Install in development/editable mode
pip install -e .

# Or install from pyproject.toml
pip install .
```

This will install all dependencies and make the `src` package available for import.

### Manual Installation

If you prefer to install dependencies separately:
```bash
pip install -r requirements.txt
```

## Requirements

See `requirements.txt` for Python dependencies:
- opencv-python - Computer vision
- pupil-apriltags - AprilTag detection
- numpy - Numerical operations
- pyserial - Arduino communication
- godot-rl - Godot RL integration
- stable-baselines3 - RL training
- tensorflow - Deep learning
- tensorboard - Training visualization
# Installation and Usage Guide

## Installation

The package can be installed in development mode, making all `src` modules importable:

```bash
# From the project root directory
pip install -e .
```

This installs the package in "editable" mode, meaning:
- Changes to source files are immediately reflected
- No need to reinstall after code changes
- The `src` package becomes available system-wide in your Python environment

## Verifying Installation

Test that imports work:

```bash
python -c "from src.config import TAG_MAP; print('✓ Installation successful!')"
```

## Usage

### Running the Application

```bash
# Direct execution
python quick_object_tracking.py

# Or from anywhere after installation
carrera-track
```

### Using with the Launcher

```bash
cd launcher
python launcher.py
```

Launcher profiles:
- `full`: Godot simulator + RL training + tracking
- `training`: Godot simulator + RL training
- `simulation`: Godot simulator + tracking
- `camera`: Tracking only
- `tensorboard`: TensorBoard visualization

### Importing as Module

```python
# Import from src package
from src.camera import CarTracker, initialize_camera
from src.tracking import TrackRecognizer, TrackGraph
from src.network import Network
from src.config import TAG_MAP, SIMULATION_IP

# Or use backward-compatible imports
from quick_object_tracking import (
    CarTracker, 
    TrackRecognizer, 
    Network,
    QuickObjectTrackingApp
)
```

## Development Setup

### Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install package
pip install -e .
```

### Dependencies

All dependencies are specified in:
- `requirements.txt` - Simple pip requirements
- `pyproject.toml` - Modern Python packaging (PEP 621)
- `setup.py` - Traditional setuptools configuration

## Troubleshooting

### Import Errors

If you get `ModuleNotFoundError: No module named 'src'`:

1. **Install the package in editable mode:**
   ```bash
   pip install -e .
   ```

2. **Or add to PYTHONPATH temporarily:**
   ```bash
   export PYTHONPATH="${PYTHONPATH}:/path/to/DS-Carrera-v1"
   python quick_object_tracking.py
   ```

3. **Check installation:**
   ```bash
   pip list | grep ds-carrera
   ```

### Camera Not Found

On macOS, you may need to grant camera permissions:
- System Settings → Privacy & Security → Camera

### Arduino Connection Issues

1. Check available ports:
   ```bash
   python -m serial.tools.list_ports
   ```

2. Specify port explicitly in code or config

### Module Dependencies

If specific packages fail to install:
```bash
# Install system dependencies first (macOS)
brew install pkg-config

# Then install Python packages
pip install -e .
```

## Configuration

Edit `src/config.py` to modify:
- Camera index and settings
- Color thresholds for detection
- Network settings (IP, port)
- AprilTag mappings
- Visualization options

## Project Structure

```
DS-Carrera-v1/
├── setup.py              # Package setup (traditional)
├── pyproject.toml        # Package setup (modern)
├── requirements.txt      # Dependencies
├── quick_object_tracking.py  # Entry point
└── src/                  # Main package
    ├── config.py         # Configuration
    ├── main.py           # Application
    ├── camera/           # Camera & detection
    ├── tracking/         # AprilTag & mapping
    ├── network/          # Communication
    └── hardware/         # Arduino interface
```

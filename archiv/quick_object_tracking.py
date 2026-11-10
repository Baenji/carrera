"""
Quick Object Tracking - Entry Point

This is a backward-compatible wrapper for the refactored modular application.
All functionality has been moved to the src/ package.

For development, you can import and use components from:
- src.camera: Camera initialization and color detection
- src.tracking: AprilTag detection and track mapping
- src.network: Network communication with simulator
- src.hardware: Arduino interface
- src.main: Main application class
"""

# Import and run the main application
from src.main import main

if __name__ == "__main__":
    main()

# Backward compatibility - expose classes if imported as module
from src.camera import CarTracker
from src.tracking import TrackRecognizer, TrackGraph
from src.network import Network
from src.main import QuickObjectTrackingApp

__all__ = ['CarTracker', 'TrackRecognizer', 'TrackGraph', 'Network', 'QuickObjectTrackingApp', 'main']

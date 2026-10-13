"""
Camera module for Carrera tracking system.
"""
from .color_detector import CarTracker
from .camera_manager import initialize_camera

__all__ = ['CarTracker', 'initialize_camera']

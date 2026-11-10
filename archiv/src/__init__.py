"""
Carrera Object Tracking System

Refactored modular architecture for tracking and simulation integration.
"""
from .main import QuickObjectTrackingApp, main
from .config import *
from . import camera, tracking, network, hardware

__version__ = '2.0.0'
__all__ = ['QuickObjectTrackingApp', 'main', 'camera', 'tracking', 'network', 'hardware']

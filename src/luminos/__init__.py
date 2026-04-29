"""
Luminos Stage (6-axis motorised positioning stage) Python Interface

A Python package for controlling Luminos motorised stages with up to 6 axes
(X, Y, Z linear + Roll, Pitch, Yaw rotational) via Zaber motion control.
"""

from .luminos_stage import LuminosStage, _LinearAxis, _RotationalAxis

__version__ = "0.1.0"
__all__ = ["LuminosStage", "_LinearAxis", "_RotationalAxis"]

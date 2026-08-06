"""Tracking backends (pluggable; MediaPipe Tasks is the default)."""

from easyfbt.backends.base import FaceBackend, PoseBackend

__all__ = ["FaceBackend", "PoseBackend"]

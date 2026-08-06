"""Camera capture: one grab thread per camera, latest frame wins.

Tracking must never block on camera I/O, so each camera runs a daemon thread
that keeps only the most recent frame (older frames are dropped, not queued).
``cv2`` is imported lazily to keep the core importable without OpenCV.
"""

from __future__ import annotations

import threading
import time

import numpy as np

from easyfbt.config import CameraConfig


class LatestFrame:
    """Thread-safe holder for the most recent frame."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._timestamp = 0.0
        self._seq = 0

    def put(self, frame: np.ndarray, timestamp: float) -> None:
        with self._lock:
            self._frame = frame
            self._timestamp = timestamp
            self._seq += 1

    def get(self) -> tuple[np.ndarray | None, float, int]:
        with self._lock:
            return self._frame, self._timestamp, self._seq


class CameraSource:
    """Background-threaded webcam reader."""

    def __init__(self, config: CameraConfig):
        self.config = config
        self.latest = LatestFrame()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        import cv2

        cap = cv2.VideoCapture(self.config.device)
        if not cap.isOpened():
            raise RuntimeError(f"cannot open camera device {self.config.device}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        cap.set(cv2.CAP_PROP_FPS, self.config.fps)
        self._thread = threading.Thread(
            target=self._run, args=(cap,), name=f"camera-{self.config.device}", daemon=True
        )
        self._thread.start()

    def _run(self, cap) -> None:
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                self.latest.put(frame, time.monotonic())
        finally:
            cap.release()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def list_cameras(max_devices: int = 10) -> list[int]:
    """Probe device indices and return the ones that open."""
    import cv2

    found = []
    for idx in range(max_devices):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            found.append(idx)
        cap.release()
    return found

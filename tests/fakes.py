"""Shared test doubles: deterministic frame sources, backends and clock."""

import numpy as np

from easyfbt import trackers as tk
from easyfbt.capture import LatestFrame
from easyfbt.types import FaceResult, PoseResult

#: Inverse of the yaw-0 camera->room transform (it is its own inverse).
ROOM_TO_CAMERA = np.array([1.0, -1.0, -1.0])


class FakeSource:
    def __init__(self):
        self.latest = LatestFrame()
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def push(self, ts: float):
        self.latest.put(np.zeros((4, 4, 3), dtype=np.uint8), ts)


class FakeClock:
    def __init__(self, start: float = 100.0):
        self.now = start

    def tick(self, dt: float = 1 / 30):
        self.now += dt
        return self.now

    def __call__(self):
        return self.now


class StaticPoseBackend:
    """Returns fixed room-space landmarks, converted to yaw-0 camera space."""

    def __init__(self, room_landmarks: np.ndarray):
        self.camera_landmarks = room_landmarks * ROOM_TO_CAMERA
        self.closed = False

    def process(self, frame, timestamp):
        return PoseResult(
            world_landmarks=self.camera_landmarks.copy(),
            visibility=np.ones(tk.NUM_LANDMARKS),
            timestamp=timestamp,
        )

    def close(self):
        self.closed = True


class StaticFaceBackend:
    def __init__(self, blendshapes: dict[str, float], eye_pitch=0.0, eye_yaw=0.0):
        self.blendshapes = blendshapes
        self.eye_pitch = eye_pitch
        self.eye_yaw = eye_yaw

    def process(self, frame, timestamp):
        return FaceResult(
            blendshapes=dict(self.blendshapes),
            confidence=0.9,
            eye_pitch=self.eye_pitch,
            eye_yaw=self.eye_yaw,
            timestamp=timestamp,
        )

    def close(self):
        pass

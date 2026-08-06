"""Core data types shared across the pipeline.

Conventions:

* Positions are metres in a right-handed, Y-up "room" space (SteamVR
  convention: +X right, +Y up, -Z forward as seen by the user).
* Quaternions are ``numpy`` arrays ``[x, y, z, w]``.
* Blendshape/expression values are floats in ``[0, 1]``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np


class TrackerRole(StrEnum):
    """SteamVR tracker roles emitted by the skeleton mapper."""

    HIP = "hip"
    CHEST = "chest"
    LEFT_KNEE = "left_knee"
    RIGHT_KNEE = "right_knee"
    LEFT_FOOT = "left_foot"
    RIGHT_FOOT = "right_foot"
    LEFT_ELBOW = "left_elbow"
    RIGHT_ELBOW = "right_elbow"


#: Stable tracker indices used by the VMT and VRChat outputs.  Order matters:
#: VRChat supports tracker slots 1..8.
TRACKER_INDEX: dict[TrackerRole, int] = {
    TrackerRole.HIP: 1,
    TrackerRole.LEFT_FOOT: 2,
    TrackerRole.RIGHT_FOOT: 3,
    TrackerRole.LEFT_KNEE: 4,
    TrackerRole.RIGHT_KNEE: 5,
    TrackerRole.CHEST: 6,
    TrackerRole.LEFT_ELBOW: 7,
    TrackerRole.RIGHT_ELBOW: 8,
}


@dataclass
class TrackerPose:
    """A single virtual tracker pose in room space."""

    role: TrackerRole
    position: np.ndarray  # shape (3,)
    rotation: np.ndarray  # quaternion [x, y, z, w]

    @property
    def index(self) -> int:
        return TRACKER_INDEX[self.role]


@dataclass
class PoseResult:
    """Body pose estimate from one camera frame.

    ``world_landmarks`` are the 33 MediaPipe pose landmarks in metres,
    origin at the mid-hip point, in *camera* space (see
    :mod:`easyfbt.trackers` for the camera→room transform).
    """

    world_landmarks: np.ndarray  # shape (33, 3)
    visibility: np.ndarray  # shape (33,)
    image_landmarks: np.ndarray | None = None  # shape (33, 2), normalised, debug only
    timestamp: float = 0.0


@dataclass
class FaceResult:
    """Facial expression estimate from one camera frame."""

    blendshapes: dict[str, float]  # ARKit-style blendshape name -> [0, 1]
    confidence: float = 1.0
    eye_pitch: float = 0.0  # radians, positive looking up
    eye_yaw: float = 0.0  # radians, positive looking left
    timestamp: float = 0.0


@dataclass
class TrackingFrame:
    """Fused output of one pipeline iteration."""

    trackers: list[TrackerPose] = field(default_factory=list)
    expressions: dict[str, float] = field(default_factory=dict)  # UnifiedExpressions
    face: FaceResult | None = None
    timestamp: float = 0.0
    fps: float = 0.0

import numpy as np
import pytest

from easyfbt import trackers as tk
from easyfbt.types import PoseResult


def standing_landmarks() -> np.ndarray:
    """Hip-centred, room-oriented skeleton of a person facing +Z (left = +X)."""
    lm = np.zeros((tk.NUM_LANDMARKS, 3))
    lm[tk.LEFT_HIP] = [0.10, 0.0, 0.0]
    lm[tk.RIGHT_HIP] = [-0.10, 0.0, 0.0]
    lm[tk.LEFT_SHOULDER] = [0.15, 0.50, 0.0]
    lm[tk.RIGHT_SHOULDER] = [-0.15, 0.50, 0.0]
    lm[tk.LEFT_ELBOW] = [0.35, 0.25, 0.05]
    lm[tk.RIGHT_ELBOW] = [-0.35, 0.25, 0.05]
    lm[tk.LEFT_WRIST] = [0.30, 0.00, 0.0]
    lm[tk.RIGHT_WRIST] = [-0.30, 0.00, 0.0]
    lm[tk.LEFT_KNEE] = [0.10, -0.45, 0.03]
    lm[tk.RIGHT_KNEE] = [-0.10, -0.45, 0.03]
    lm[tk.LEFT_ANKLE] = [0.10, -0.85, 0.0]
    lm[tk.RIGHT_ANKLE] = [-0.10, -0.85, 0.0]
    lm[tk.LEFT_HEEL] = [0.10, -0.90, -0.03]
    lm[tk.RIGHT_HEEL] = [-0.10, -0.90, -0.03]
    lm[tk.LEFT_FOOT_INDEX] = [0.10, -0.90, 0.12]
    lm[tk.RIGHT_FOOT_INDEX] = [-0.10, -0.90, 0.12]
    return lm


@pytest.fixture
def standing_pose() -> PoseResult:
    return PoseResult(
        world_landmarks=standing_landmarks(),
        visibility=np.ones(tk.NUM_LANDMARKS),
        timestamp=1.0,
    )

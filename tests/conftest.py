import numpy as np
import pytest

from easyfbt import trackers as tk
from easyfbt.types import PoseResult


def pytest_addoption(parser):
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="rewrite golden sample files from the current outputs instead of comparing",
    )


@pytest.fixture
def update_goldens(request) -> bool:
    return request.config.getoption("--update-goldens")


def assert_close(actual, expected, tol: float, path: str = "$"):
    """Recursively compare JSON-like structures with a float tolerance."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected dict, got {type(actual).__name__}"
        assert set(actual) == set(expected), (
            f"{path}: keys differ: extra={set(actual) - set(expected)}, "
            f"missing={set(expected) - set(actual)}"
        )
        for key in expected:
            assert_close(actual[key], expected[key], tol, f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected list, got {type(actual).__name__}"
        assert len(actual) == len(expected), f"{path}: length {len(actual)} != {len(expected)}"
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            assert_close(a, e, tol, f"{path}[{i}]")
    elif isinstance(expected, bool) or not isinstance(expected, int | float):
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"
    else:
        assert isinstance(actual, int | float), f"{path}: expected number, got {actual!r}"
        assert abs(actual - expected) <= tol, f"{path}: {actual} != {expected} (tol {tol})"


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

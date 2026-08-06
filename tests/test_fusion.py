import numpy as np
import pytest

from easyfbt.fusion import fuse_faces, fuse_poses
from easyfbt.types import FaceResult, PoseResult

N = 33


def make_pose(value: float, visibility: float, ts: float = 0.0) -> PoseResult:
    return PoseResult(
        world_landmarks=np.full((N, 3), value),
        visibility=np.full(N, visibility),
        timestamp=ts,
    )


def test_empty_returns_none():
    assert fuse_poses([]) is None
    assert fuse_faces([]) is None


def test_single_pose_passthrough():
    p = make_pose(1.0, 1.0)
    assert fuse_poses([p]) is p


def test_visibility_weighted_average():
    a = make_pose(0.0, 1.0)
    b = make_pose(1.0, 0.25)
    fused = fuse_poses([a, b])
    assert fused is not None
    assert np.allclose(fused.world_landmarks, 0.25 / 1.25)
    assert np.allclose(fused.visibility, 1.0)


def test_occluded_camera_is_ignored():
    good = make_pose(2.0, 1.0)
    blind = make_pose(99.0, 0.0)
    fused = fuse_poses([good, blind])
    assert fused is not None
    assert np.allclose(fused.world_landmarks, 2.0, atol=1e-6)


def test_per_landmark_weighting():
    a = make_pose(0.0, 1.0)
    b = make_pose(1.0, 1.0)
    b.visibility[5] = 0.0  # camera b cannot see landmark 5
    fused = fuse_poses([a, b])
    assert fused is not None
    assert np.allclose(fused.world_landmarks[5], 0.0, atol=1e-6)
    assert np.allclose(fused.world_landmarks[6], 0.5, atol=1e-6)


def test_all_blind_landmark_falls_back_to_mean():
    a = make_pose(0.0, 0.0)
    b = make_pose(1.0, 0.0)
    fused = fuse_poses([a, b])
    assert fused is not None
    assert np.allclose(fused.world_landmarks, 0.5)


def test_timestamp_is_latest():
    fused = fuse_poses([make_pose(0, 1, ts=1.0), make_pose(0, 1, ts=2.5)])
    assert fused is not None
    assert fused.timestamp == pytest.approx(2.5)


def test_face_highest_confidence_wins():
    weak = FaceResult(blendshapes={"jawOpen": 0.1}, confidence=0.2)
    strong = FaceResult(blendshapes={"jawOpen": 0.9}, confidence=0.8)
    fused = fuse_faces([weak, strong])
    assert fused is strong

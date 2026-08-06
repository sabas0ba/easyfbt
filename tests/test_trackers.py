import numpy as np
import pytest

from easyfbt import quat
from easyfbt import trackers as tk
from easyfbt.types import TrackerRole

ALL_ROLES = list(TrackerRole)

FORWARD = np.array([0.0, 0.0, -1.0])  # device forward axis (SteamVR -Z)


def device_forward(rotation):
    return quat.rotate_vec(rotation, FORWARD)


def test_to_room_axes_yaw_zero():
    cam = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    room = tk.to_room(cam, yaw_deg=0.0)
    assert np.allclose(room[0], [1.0, 0.0, 0.0], atol=1e-9)  # image right -> +X
    assert np.allclose(room[1], [0.0, -1.0, 0.0], atol=1e-9)  # image down -> -Y
    assert np.allclose(room[2], [0.0, 0.0, -1.0], atol=1e-9)  # depth -> along view (-Z)


def test_to_room_yaw_rotates_horizontally():
    cam = np.array([[0.0, 0.0, 1.0]])  # one unit into the scene
    room = tk.to_room(cam, yaw_deg=90.0)
    assert np.allclose(room[0], [-1.0, 0.0, 0.0], atol=1e-9)


def test_all_trackers_present_for_full_visibility(standing_pose):
    result = tk.build_trackers(standing_pose, ALL_ROLES)
    assert {t.role for t in result} == set(ALL_ROLES)


def test_hip_anchor_height(standing_pose):
    result = tk.build_trackers(standing_pose, [TrackerRole.HIP], user_height=1.70)
    hip = result[0]
    assert np.allclose(hip.position, [0.0, 1.70 * tk.HIP_HEIGHT_RATIO, 0.0], atol=1e-9)


def test_hip_faces_body_forward(standing_pose):
    hip = tk.build_trackers(standing_pose, [TrackerRole.HIP])[0]
    # Skeleton faces +Z, so the device forward must too.
    assert np.dot(device_forward(hip.rotation), [0.0, 0.0, 1.0]) > 0.99


def test_feet_point_along_toes(standing_pose):
    result = tk.build_trackers(standing_pose, [TrackerRole.LEFT_FOOT, TrackerRole.RIGHT_FOOT])
    for foot in result:
        fwd = device_forward(foot.rotation)
        assert np.dot(fwd, [0.0, 0.0, 1.0]) > 0.9  # toes face +Z


def test_foot_position_is_ankle(standing_pose):
    foot = tk.build_trackers(standing_pose, [TrackerRole.LEFT_FOOT], user_height=1.70)[0]
    expected = np.array([0.0, 1.70 * tk.HIP_HEIGHT_RATIO, 0.0]) + np.array([0.10, -0.85, 0.0])
    assert np.allclose(foot.position, expected, atol=1e-9)


def test_knee_forward_matches_bend(standing_pose):
    knee = tk.build_trackers(standing_pose, [TrackerRole.LEFT_KNEE])[0]
    assert np.dot(device_forward(knee.rotation), [0.0, 0.0, 1.0]) > 0.9


def test_low_visibility_drops_only_affected_trackers(standing_pose):
    standing_pose.visibility[tk.LEFT_ANKLE] = 0.1
    result = tk.build_trackers(standing_pose, ALL_ROLES, min_visibility=0.5)
    roles = {t.role for t in result}
    assert TrackerRole.LEFT_FOOT not in roles
    assert TrackerRole.LEFT_KNEE not in roles
    assert TrackerRole.RIGHT_FOOT in roles
    assert TrackerRole.HIP in roles


def test_rotations_are_unit_quaternions(standing_pose):
    for t in tk.build_trackers(standing_pose, ALL_ROLES):
        assert float(np.linalg.norm(t.rotation)) == pytest.approx(1.0, abs=1e-6)


def test_tracker_indices_unique(standing_pose):
    result = tk.build_trackers(standing_pose, ALL_ROLES)
    indices = [t.index for t in result]
    assert len(indices) == len(set(indices))
    assert all(1 <= i <= 8 for i in indices)

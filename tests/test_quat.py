import math

import numpy as np
import pytest

from easyfbt import quat


def test_identity_rotates_nothing():
    v = np.array([1.0, 2.0, 3.0])
    assert np.allclose(quat.rotate_vec(quat.IDENTITY, v), v)


def test_axis_angle_90deg_about_y():
    q = quat.from_axis_angle(np.array([0.0, 1.0, 0.0]), math.pi / 2)
    # +Z rotates to +X under a right-handed +90deg yaw.
    assert np.allclose(quat.rotate_vec(q, np.array([0.0, 0.0, 1.0])), [1.0, 0.0, 0.0], atol=1e-9)


def test_multiply_composes():
    qa = quat.from_axis_angle(np.array([0.0, 1.0, 0.0]), 0.3)
    qb = quat.from_axis_angle(np.array([1.0, 0.0, 0.0]), 0.5)
    v = np.array([0.2, -1.0, 0.7])
    combined = quat.rotate_vec(quat.multiply(qa, qb), v)
    sequential = quat.rotate_vec(qa, quat.rotate_vec(qb, v))
    assert np.allclose(combined, sequential)


def test_from_matrix_roundtrip():
    rng = np.random.default_rng(42)
    for _ in range(50):
        axis = rng.normal(size=3)
        angle = rng.uniform(-math.pi, math.pi)
        q = quat.from_axis_angle(axis, angle)
        m = np.column_stack(
            [
                quat.rotate_vec(q, np.array([1.0, 0.0, 0.0])),
                quat.rotate_vec(q, np.array([0.0, 1.0, 0.0])),
                quat.rotate_vec(q, np.array([0.0, 0.0, 1.0])),
            ]
        )
        q2 = quat.from_matrix(m)
        # q and -q encode the same rotation.
        assert np.allclose(q, q2, atol=1e-6) or np.allclose(q, -q2, atol=1e-6)


def test_look_rotation_faces_forward():
    q = quat.look_rotation(np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0]))
    # Device -Z axis must point along the requested forward (+Z).
    assert np.allclose(quat.rotate_vec(q, np.array([0.0, 0.0, -1.0])), [0.0, 0.0, 1.0], atol=1e-9)


def test_look_rotation_degenerate_inputs():
    assert np.allclose(quat.look_rotation(np.zeros(3), np.array([0.0, 1.0, 0.0])), quat.IDENTITY)
    q = quat.look_rotation(np.array([0.0, 1.0, 0.0]), np.array([0.0, 1.0, 0.0]))
    assert np.isclose(float(np.linalg.norm(q)), 1.0)


def test_to_unity_flips_handedness():
    pos, rot = quat.to_unity(np.array([1.0, 2.0, 3.0]), quat.IDENTITY)
    assert np.allclose(pos, [1.0, 2.0, -3.0])
    assert np.allclose(rot, quat.IDENTITY)
    # Double application restores the original.
    pos2, _rot2 = quat.to_unity(pos * np.array([1, 1, -1]), rot)
    assert np.allclose(pos2, [1.0, 2.0, -3.0])


@pytest.mark.parametrize(
    ("axis", "angle_deg", "expected"),
    [
        ((1, 0, 0), 30.0, (30.0, 0.0, 0.0)),
        ((0, 1, 0), 45.0, (0.0, 45.0, 0.0)),
        ((0, 0, 1), 60.0, (0.0, 0.0, 60.0)),
    ],
)
def test_unity_euler_single_axis(axis, angle_deg, expected):
    q = quat.from_axis_angle(np.array(axis, dtype=float), math.radians(angle_deg))
    assert np.allclose(quat.unity_euler_deg(q), expected, atol=1e-5)


def test_unity_euler_roundtrip_zxy():
    rng = np.random.default_rng(7)
    for _ in range(50):
        pitch, roll = rng.uniform(-80, 80, size=2)
        yaw = rng.uniform(-179, 179)
        qx = quat.from_axis_angle(np.array([1.0, 0.0, 0.0]), math.radians(pitch))
        qy = quat.from_axis_angle(np.array([0.0, 1.0, 0.0]), math.radians(yaw))
        qz = quat.from_axis_angle(np.array([0.0, 0.0, 1.0]), math.radians(roll))
        # Unity order: Z applied first, then X, then Y.
        q = quat.multiply(qy, quat.multiply(qx, qz))
        assert np.allclose(quat.unity_euler_deg(q), [pitch, yaw, roll], atol=1e-4)

"""Minimal quaternion / rotation helpers.

Quaternions are ``numpy`` arrays ``[x, y, z, w]`` describing rotations in the
right-handed, Y-up room space.  Conversion helpers to Unity's left-handed
convention (used by VMT and VRChat OSC trackers) live here as well.
"""

from __future__ import annotations

import math

import numpy as np

IDENTITY = np.array([0.0, 0.0, 0.0, 1.0])


def normalize(q: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(q))
    if n < 1e-12:
        return IDENTITY.copy()
    return q / n


def multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton product a*b (apply b first, then a)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array(
        [
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz,
        ]
    )


def conjugate(q: np.ndarray) -> np.ndarray:
    return np.array([-q[0], -q[1], -q[2], q[3]])


def from_axis_angle(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    n = float(np.linalg.norm(axis))
    if n < 1e-12:
        return IDENTITY.copy()
    half = angle_rad / 2.0
    s = math.sin(half) / n
    return np.array([axis[0] * s, axis[1] * s, axis[2] * s, math.cos(half)])


def rotate_vec(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate vector v by quaternion q."""
    qv = np.array([v[0], v[1], v[2], 0.0])
    return multiply(multiply(q, qv), conjugate(q))[:3]


def from_matrix(m: np.ndarray) -> np.ndarray:
    """Quaternion from a 3x3 rotation matrix (columns = basis vectors)."""
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    return normalize(np.array([x, y, z, w]))


def look_rotation(forward: np.ndarray, up: np.ndarray) -> np.ndarray:
    """Rotation whose -Z axis points along ``forward`` with ``up`` as hint.

    Mirrors the SteamVR convention where a device's forward is -Z.
    Degenerate inputs fall back to the identity rotation.
    """
    f = np.asarray(forward, dtype=float)
    fn = float(np.linalg.norm(f))
    if fn < 1e-9:
        return IDENTITY.copy()
    f = f / fn
    # Device axes: Z = -f, Y ~ up, X = Y x Z = f x up (right-handed).
    r = np.cross(f, np.asarray(up, dtype=float))
    rn = float(np.linalg.norm(r))
    if rn < 1e-9:
        # forward parallel to up; pick an arbitrary orthogonal right axis
        r = np.cross(f, np.array([0.0, 0.0, 1.0]))
        rn = float(np.linalg.norm(r))
        if rn < 1e-9:
            r = np.array([1.0, 0.0, 0.0])
            rn = 1.0
    r = r / rn
    u = np.cross(-f, r)
    m = np.column_stack([r, u, -f])  # -Z forward
    return from_matrix(m)


def to_unity(position: np.ndarray, rotation: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert room-space (right-handed, Y-up) pose to Unity (left-handed, Y-up).

    Standard OpenVR <-> Unity mapping: negate Z of the position, negate X and Y
    of the quaternion vector part.
    """
    pos = np.array([position[0], position[1], -position[2]])
    rot = np.array([-rotation[0], -rotation[1], rotation[2], rotation[3]])
    return pos, rot


def unity_euler_deg(q_unity: np.ndarray) -> np.ndarray:
    """Unity euler angles (degrees, applied Z then X then Y) from a Unity quaternion.

    Matches ``UnityEngine.Quaternion.eulerAngles`` up to angle wrapping;
    VRChat's ``/tracking/trackers`` endpoint expects this convention.
    """
    x, y, z, w = normalize(q_unity)
    # R = Ry(yaw) @ Rx(pitch) @ Rz(roll); extract from the quaternion's matrix.
    sinp = float(np.clip(2 * (w * x - y * z), -1.0, 1.0))
    pitch = math.asin(sinp)
    if abs(sinp) < 0.999999:
        yaw = math.atan2(2 * (x * z + w * y), 1 - 2 * (x * x + y * y))
        roll = math.atan2(2 * (x * y + w * z), 1 - 2 * (x * x + z * z))
    else:  # gimbal lock: pitch = +-90 deg, fold roll into yaw
        yaw = math.atan2(2 * (w * y - x * z), 1 - 2 * (y * y + z * z))
        roll = 0.0
    return np.degrees(np.array([pitch, yaw, roll]))


def yaw_rotation(yaw_deg: float) -> np.ndarray:
    """Rotation about +Y by ``yaw_deg`` degrees."""
    return from_axis_angle(np.array([0.0, 1.0, 0.0]), math.radians(yaw_deg))

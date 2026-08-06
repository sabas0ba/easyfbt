"""Skeleton mapping: MediaPipe pose landmarks -> SteamVR tracker poses.

Coordinate model
----------------

* MediaPipe *world* landmarks are metres with origin at the mid-hip point, in
  camera-aligned axes: +X image-right, +Y down, +Z away from the camera.
* Room space is SteamVR-style: right-handed, +Y up.  A camera's pose in the
  room is its ``position`` plus a ``yaw_deg`` viewing direction (yaw 0 looks
  along -Z).
* v0.1 anchors the skeleton: the mid-hip point is fixed at
  ``hip_height = user_height * 0.53`` above the origin.  Room-scale
  translation of the whole body is not estimated yet (single uncalibrated
  webcams cannot recover absolute depth reliably); VRChat/SteamVR calibration
  absorbs the fixed anchor.
"""

from __future__ import annotations

import numpy as np

from easyfbt import quat
from easyfbt.types import PoseResult, TrackerPose, TrackerRole

# MediaPipe pose landmark indices (33-point topology).
NOSE = 0
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28
LEFT_HEEL = 29
RIGHT_HEEL = 30
LEFT_FOOT_INDEX = 31
RIGHT_FOOT_INDEX = 32

NUM_LANDMARKS = 33

HIP_HEIGHT_RATIO = 0.53

UP = np.array([0.0, 1.0, 0.0])


def camera_basis(yaw_deg: float) -> np.ndarray:
    """3x3 matrix whose columns map camera axes (x-right, y-down, z-depth)
    into room space for a camera with the given yaw."""
    r_yaw = quat.yaw_rotation(yaw_deg)
    d = quat.rotate_vec(r_yaw, np.array([0.0, 0.0, -1.0]))  # viewing direction
    right = quat.rotate_vec(r_yaw, np.array([1.0, 0.0, 0.0]))  # image right
    return np.column_stack([right, -UP, d])


def to_room(world_landmarks: np.ndarray, yaw_deg: float) -> np.ndarray:
    """Rotate hip-centred camera-space landmarks into room orientation."""
    return world_landmarks @ camera_basis(yaw_deg).T


def _mid(landmarks: np.ndarray, a: int, b: int) -> np.ndarray:
    return (landmarks[a] + landmarks[b]) / 2.0


def _segment_rotation(
    top: np.ndarray, bottom: np.ndarray, joint: np.ndarray, fallback_forward: np.ndarray
) -> np.ndarray:
    """Rotation for a limb joint (knee/elbow): up along the limb, forward in
    the bend direction; falls back when the limb is almost straight."""
    up = top - bottom
    bend = joint - (top + bottom) / 2.0
    if float(np.linalg.norm(bend)) < 0.02:  # limb nearly straight
        bend = fallback_forward
    # Remove the component along the limb so forward stays orthogonal.
    up_n = up / max(float(np.linalg.norm(up)), 1e-9)
    forward = bend - np.dot(bend, up_n) * up_n
    return quat.look_rotation(forward, up)


def build_trackers(
    pose: PoseResult,
    roles: list[TrackerRole],
    user_height: float = 1.70,
    min_visibility: float = 0.5,
) -> list[TrackerPose]:
    """Map fused room-oriented landmarks to tracker poses.

    ``pose.world_landmarks`` must already be rotated into room orientation
    (still hip-centred).  Trackers whose defining landmarks fall below
    ``min_visibility`` are omitted so downstream outputs can keep the last
    good pose instead of receiving garbage.
    """
    lm = pose.world_landmarks
    vis = pose.visibility
    anchor = np.array([0.0, user_height * HIP_HEIGHT_RATIO, 0.0])

    def visible(*idx: int) -> bool:
        return all(vis[i] >= min_visibility for i in idx)

    def pos(p: np.ndarray) -> np.ndarray:
        return anchor + p

    body_forward = np.cross(lm[LEFT_HIP] - lm[RIGHT_HIP], UP) * -1.0
    if float(np.linalg.norm(body_forward)) < 1e-6:
        body_forward = np.array([0.0, 0.0, 1.0])

    trackers: list[TrackerPose] = []
    for role in roles:
        if role is TrackerRole.HIP:
            if not visible(LEFT_HIP, RIGHT_HIP, LEFT_SHOULDER, RIGHT_SHOULDER):
                continue
            lateral = lm[LEFT_HIP] - lm[RIGHT_HIP]
            up = _mid(lm, LEFT_SHOULDER, RIGHT_SHOULDER) - _mid(lm, LEFT_HIP, RIGHT_HIP)
            rot = quat.look_rotation(np.cross(lateral, up), up)
            trackers.append(TrackerPose(role, pos(_mid(lm, LEFT_HIP, RIGHT_HIP)), rot))
        elif role is TrackerRole.CHEST:
            if not visible(LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP):
                continue
            lateral = lm[LEFT_SHOULDER] - lm[RIGHT_SHOULDER]
            up = _mid(lm, LEFT_SHOULDER, RIGHT_SHOULDER) - _mid(lm, LEFT_HIP, RIGHT_HIP)
            rot = quat.look_rotation(np.cross(lateral, up), up)
            trackers.append(TrackerPose(role, pos(_mid(lm, LEFT_SHOULDER, RIGHT_SHOULDER)), rot))
        elif role in (TrackerRole.LEFT_KNEE, TrackerRole.RIGHT_KNEE):
            hip, knee, ankle = (
                (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE)
                if role is TrackerRole.LEFT_KNEE
                else (RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE)
            )
            if not visible(hip, knee, ankle):
                continue
            rot = _segment_rotation(lm[hip], lm[ankle], lm[knee], body_forward)
            trackers.append(TrackerPose(role, pos(lm[knee]), rot))
        elif role in (TrackerRole.LEFT_FOOT, TrackerRole.RIGHT_FOOT):
            ankle, heel, toe = (
                (LEFT_ANKLE, LEFT_HEEL, LEFT_FOOT_INDEX)
                if role is TrackerRole.LEFT_FOOT
                else (RIGHT_ANKLE, RIGHT_HEEL, RIGHT_FOOT_INDEX)
            )
            if not visible(ankle, heel, toe):
                continue
            rot = quat.look_rotation(lm[toe] - lm[heel], UP)
            trackers.append(TrackerPose(role, pos(lm[ankle]), rot))
        elif role in (TrackerRole.LEFT_ELBOW, TrackerRole.RIGHT_ELBOW):
            shoulder, elbow, wrist = (
                (LEFT_SHOULDER, LEFT_ELBOW, LEFT_WRIST)
                if role is TrackerRole.LEFT_ELBOW
                else (RIGHT_SHOULDER, RIGHT_ELBOW, RIGHT_WRIST)
            )
            if not visible(shoulder, elbow, wrist):
                continue
            rot = _segment_rotation(lm[shoulder], lm[wrist], lm[elbow], body_forward)
            trackers.append(TrackerPose(role, pos(lm[elbow]), rot))
    return trackers

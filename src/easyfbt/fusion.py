"""Multi-camera fusion.

Each camera produces a hip-centred, room-oriented landmark set (see
:func:`easyfbt.trackers.to_room`).  Fusion is a per-landmark
visibility-weighted average: a camera that sees a limb clearly dominates
cameras where the limb is occluded.  Faces are not averaged -- blending
blendshapes from different viewing angles degrades quality -- instead the
highest-confidence face wins.
"""

from __future__ import annotations

import numpy as np

from easyfbt.types import FaceResult, PoseResult


def fuse_poses(poses: list[PoseResult]) -> PoseResult | None:
    """Fuse per-camera pose results into one. Returns None when empty."""
    poses = [p for p in poses if p is not None]
    if not poses:
        return None
    if len(poses) == 1:
        return poses[0]

    landmarks = np.stack([p.world_landmarks for p in poses])  # (C, 33, 3)
    vis = np.stack([p.visibility for p in poses])  # (C, 33)

    weights = vis.copy()
    totals = weights.sum(axis=0)  # (33,)
    # Landmarks nobody sees: fall back to a plain average to avoid 0/0.
    dead = totals < 1e-6
    weights[:, dead] = 1.0
    totals[dead] = weights.shape[0]

    fused = (landmarks * weights[:, :, None]).sum(axis=0) / totals[:, None]
    return PoseResult(
        world_landmarks=fused,
        visibility=vis.max(axis=0),
        timestamp=max(p.timestamp for p in poses),
    )


def fuse_faces(faces: list[FaceResult]) -> FaceResult | None:
    """Pick the highest-confidence face result. Returns None when empty."""
    faces = [f for f in faces if f is not None]
    if not faces:
        return None
    return max(faces, key=lambda f: f.confidence)

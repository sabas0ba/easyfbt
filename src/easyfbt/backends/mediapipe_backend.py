"""MediaPipe Tasks backends (pose landmarker + face landmarker).

Imported lazily: the rest of the package works (and is tested) without the
``mediapipe`` wheel installed.  Model files are local ``.task`` assets fetched
by ``tools/fetch_models.py``, which verifies pinned sha256 hashes -- nothing
is downloaded implicitly at runtime.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from easyfbt.types import FaceResult, PoseResult

#: Rough full-scale gaze deflection of the ARKit eyeLook* shapes, radians.
GAZE_RANGE_RAD = math.radians(30.0)


def _import_mediapipe():
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
    except ImportError as exc:  # pragma: no cover - exercised only without the wheel
        raise RuntimeError(
            "mediapipe is not installed. Install runtime dependencies with:\n"
            "  pip install --require-hashes -r requirements/runtime.lock"
        ) from exc
    return mp, mp_python, vision


def _check_model(path: str) -> str:
    if not Path(path).is_file():
        raise FileNotFoundError(
            f"model file not found: {path}\n"
            "Fetch verified models with: python tools/fetch_models.py"
        )
    return path


class MediaPipePoseBackend:
    """Body pose via MediaPipe PoseLandmarker (VIDEO mode)."""

    def __init__(self, model_path: str):
        mp, mp_python, vision = _import_mediapipe()
        self._mp = mp
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=_check_model(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

    def process(self, frame_bgr: np.ndarray, timestamp: float) -> PoseResult | None:
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, int(timestamp * 1000))
        if not result.pose_world_landmarks:
            return None
        world = result.pose_world_landmarks[0]
        image_lms = result.pose_landmarks[0] if result.pose_landmarks else None
        return PoseResult(
            world_landmarks=np.array([[p.x, p.y, p.z] for p in world]),
            visibility=np.array([p.visibility if p.visibility is not None else 1.0 for p in world]),
            image_landmarks=(
                np.array([[p.x, p.y] for p in image_lms]) if image_lms is not None else None
            ),
            timestamp=timestamp,
        )

    def close(self) -> None:
        self._landmarker.close()


class MediaPipeFaceBackend:
    """Facial expressions via MediaPipe FaceLandmarker blendshapes."""

    def __init__(self, model_path: str):
        mp, mp_python, vision = _import_mediapipe()
        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=_check_model(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

    def process(self, frame_bgr: np.ndarray, timestamp: float) -> FaceResult | None:
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, int(timestamp * 1000))
        if not result.face_blendshapes:
            return None
        shapes = {c.category_name: float(c.score) for c in result.face_blendshapes[0]}

        def g(name: str) -> float:
            return shapes.get(name, 0.0)

        pitch = (g("eyeLookUpLeft") + g("eyeLookUpRight")) / 2.0 - (
            (g("eyeLookDownLeft") + g("eyeLookDownRight")) / 2.0
        )
        yaw = (g("eyeLookOutLeft") + g("eyeLookInRight")) / 2.0 - (
            (g("eyeLookInLeft") + g("eyeLookOutRight")) / 2.0
        )
        return FaceResult(
            blendshapes=shapes,
            confidence=1.0,
            eye_pitch=pitch * GAZE_RANGE_RAD,
            eye_yaw=yaw * GAZE_RANGE_RAD,
            timestamp=timestamp,
        )

    def close(self) -> None:
        self._landmarker.close()

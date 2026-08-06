"""Pipeline orchestration.

Data flow per iteration::

    cameras (threads) -> latest frames -> pose/face backends -> room transform
      -> multi-camera fusion -> One Euro smoothing -> tracker mapping
      -> UnifiedExpressions mapping -> outputs (VMT / VRChat / VRCFT / JSON)

Everything is injected (frame sources, backends, outputs, clock) so the whole
pipeline runs headless in tests with fakes.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from easyfbt import expressions, fusion, trackers
from easyfbt.backends.base import FaceBackend, PoseBackend
from easyfbt.config import Config
from easyfbt.filters import OneEuroFilter
from easyfbt.outputs.base import Output
from easyfbt.types import FaceResult, PoseResult, TrackingFrame


@dataclass
class CameraUnit:
    """A frame source plus the backends that consume it."""

    source: object  # exposes .latest.get() -> (frame, ts, seq); start(); stop()
    yaw_deg: float = 0.0
    pose_backend: PoseBackend | None = None
    face_backend: FaceBackend | None = None
    last_seq: int = -1


class Pipeline:
    def __init__(
        self,
        config: Config,
        cameras: list[CameraUnit],
        outputs: list[Output],
        clock=time.monotonic,
    ):
        if not cameras:
            raise ValueError("at least one camera unit is required")
        self._config = config
        self._cameras = cameras
        self._outputs = outputs
        self._clock = clock
        #: Serialises step() against live re-configuration from the UI thread.
        self._lock = threading.Lock()
        self._landmark_filter = OneEuroFilter(
            min_cutoff=config.tracking.smoothing_min_cutoff,
            beta=config.tracking.smoothing_beta,
        )
        self._fps = 0.0
        self._last_step: float | None = None
        self.last_pose: PoseResult | None = None
        self.last_face: FaceResult | None = None

    def start(self) -> None:
        for cam in self._cameras:
            cam.source.start()

    def stop(self) -> None:
        for cam in self._cameras:
            cam.source.stop()
        for cam in self._cameras:
            if cam.pose_backend is not None:
                cam.pose_backend.close()
            if cam.face_backend is not None:
                cam.face_backend.close()
        for out in self._outputs:
            out.close()

    def swap_outputs(self, new_outputs: list[Output]) -> None:
        """Replace all output sinks live (closes the old ones)."""
        with self._lock:
            old, self._outputs = self._outputs, new_outputs
        for out in old:
            out.close()

    def set_camera_pose(self, index: int, yaw_deg: float) -> None:
        """Live-update a camera's room orientation."""
        with self._lock:
            self._cameras[index].yaw_deg = yaw_deg

    def apply_tracking_config(self, tracking) -> None:
        """Live-update tracking parameters; resets smoothing if it changed."""
        with self._lock:
            old = self._config.tracking
            smoothing_changed = (
                old.smoothing_min_cutoff != tracking.smoothing_min_cutoff
                or old.smoothing_beta != tracking.smoothing_beta
            )
            self._config.tracking = tracking
            if smoothing_changed:
                self._landmark_filter = OneEuroFilter(
                    min_cutoff=tracking.smoothing_min_cutoff,
                    beta=tracking.smoothing_beta,
                )

    def step(self) -> TrackingFrame:
        """Process the newest frame of every camera and emit one fused frame."""
        with self._lock:
            return self._step_locked()

    def _step_locked(self) -> TrackingFrame:
        now = self._clock()
        poses: list[PoseResult] = []
        faces: list[FaceResult] = []
        for cam in self._cameras:
            frame, ts, seq = cam.source.latest.get()
            if frame is None or seq == cam.last_seq:
                continue  # no new data from this camera
            cam.last_seq = seq
            if cam.pose_backend is not None:
                pose = cam.pose_backend.process(frame, ts)
                if pose is not None:
                    pose.world_landmarks = trackers.to_room(pose.world_landmarks, cam.yaw_deg)
                    poses.append(pose)
            if cam.face_backend is not None:
                face = cam.face_backend.process(frame, ts)
                if face is not None:
                    faces.append(face)

        fused_pose = fusion.fuse_poses(poses)
        fused_face = fusion.fuse_faces(faces)
        if fused_pose is not None:
            fused_pose.world_landmarks = self._landmark_filter.apply(
                fused_pose.world_landmarks, now
            )
            self.last_pose = fused_pose
        if fused_face is not None:
            self.last_face = fused_face

        if self._last_step is not None:
            dt = now - self._last_step
            if dt > 0:
                self._fps = 0.9 * self._fps + 0.1 / dt if self._fps else 1.0 / dt
        self._last_step = now

        tracking = TrackingFrame(timestamp=now, fps=self._fps)
        pose = self.last_pose
        if pose is not None:
            tracking.trackers = trackers.build_trackers(
                pose,
                roles=self._config.tracking.roles,
                user_height=self._config.tracking.user_height,
                min_visibility=self._config.tracking.min_visibility,
            )
        face = self.last_face
        if face is not None:
            tracking.face = face
            tracking.expressions = {
                **expressions.arkit_to_unified(face.blendshapes),
                **expressions.eye_parameters(face.blendshapes),
            }

        for out in self._outputs:
            out.send(tracking)
        return tracking

    def run(self, view=None, max_iterations: int | None = None) -> None:
        """Main loop; blocks until quit (debug window 'q'), Ctrl-C or
        ``max_iterations``."""
        iterations = 0
        self.start()
        try:
            while max_iterations is None or iterations < max_iterations:
                interval = 1.0 / self._config.tracking.target_fps
                started = self._clock()
                tracking = self.step()
                if view is not None:
                    frame, _, _ = self._cameras[0].source.latest.get()
                    if frame is not None and not view.render(
                        frame, self.last_pose, self.last_face, tracking
                    ):
                        break
                iterations += 1
                elapsed = self._clock() - started
                if elapsed < interval:
                    time.sleep(interval - elapsed)
        except KeyboardInterrupt:
            pass
        finally:
            if view is not None:
                view.close()
            self.stop()

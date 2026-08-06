"""OpenCV debug window: skeleton overlay, expression bars, tracker readout."""

from __future__ import annotations

import numpy as np

from easyfbt.types import FaceResult, PoseResult, TrackingFrame

# MediaPipe 33-landmark skeleton edges (subset that reads well on screen).
SKELETON_EDGES = [
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (27, 29),
    (29, 31),
    (27, 31),
    (24, 26),
    (26, 28),
    (28, 30),
    (30, 32),
    (28, 32),
]

_TOP_EXPRESSIONS = 12


class DebugView:
    """Renders per-camera previews; returns False when the user quits."""

    def __init__(self, window_name: str = "easyfbt debug"):
        import cv2

        self._cv2 = cv2
        self._window = window_name
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    def render(
        self,
        frame_bgr: np.ndarray,
        pose: PoseResult | None,
        face: FaceResult | None,
        tracking: TrackingFrame,
    ) -> bool:
        cv2 = self._cv2
        canvas = frame_bgr.copy()
        h, w = canvas.shape[:2]

        if pose is not None and pose.image_landmarks is not None:
            pts = (pose.image_landmarks * np.array([w, h])).astype(int)
            for a, b in SKELETON_EDGES:
                if pose.visibility[a] > 0.5 and pose.visibility[b] > 0.5:
                    cv2.line(canvas, tuple(pts[a]), tuple(pts[b]), (0, 255, 0), 2)
            for i, p in enumerate(pts):
                if pose.visibility[i] > 0.5:
                    cv2.circle(canvas, tuple(p), 3, (0, 128, 255), -1)

        y = 24
        cv2.putText(
            canvas,
            f"fps {tracking.fps:5.1f}  trackers {len(tracking.trackers)}",
            (8, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 0),
            2,
        )
        for t in tracking.trackers:
            y += 20
            px, py, pz = t.position
            cv2.putText(
                canvas,
                f"{t.role.value:12s} ({px:+.2f} {py:+.2f} {pz:+.2f})",
                (8, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (200, 255, 200),
                1,
            )

        if face is not None and tracking.expressions:
            top = sorted(tracking.expressions.items(), key=lambda kv: -kv[1])
            bar_x = w - 240
            by = 24
            for name, value in top[:_TOP_EXPRESSIONS]:
                cv2.rectangle(
                    canvas, (bar_x, by - 10), (bar_x + int(120 * value), by), (255, 128, 0), -1
                )
                cv2.putText(
                    canvas,
                    f"{name} {value:.2f}",
                    (bar_x + 124, by),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    (255, 255, 255),
                    1,
                )
                by += 18

        cv2.imshow(self._window, canvas)
        return cv2.waitKey(1) & 0xFF != ord("q")

    def close(self) -> None:
        self._cv2.destroyWindow(self._window)

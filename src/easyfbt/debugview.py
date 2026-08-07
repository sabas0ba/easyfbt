"""Debug views: skeleton overlay, expression bars, tracker readout.

Two sinks share the same overlay renderer:

* :class:`DebugView` -- local OpenCV window (needs a display);
* :class:`HttpDebugView` -- annotated JPEG + state pushed to a
  :class:`easyfbt.debug_http.DebugHttpServer` (works headless/in containers).

Several views can run at once via :class:`MultiView`.
"""

from __future__ import annotations

import numpy as np

from easyfbt.debug_http import DebugHttpServer
from easyfbt.outputs.udp_json import frame_to_dict
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


def draw_overlay(
    frame_bgr: np.ndarray,
    pose: PoseResult | None,
    face: FaceResult | None,
    tracking: TrackingFrame,
    show_video: bool = True,
) -> np.ndarray:
    """Return the annotated frame; with ``show_video=False`` the overlay is
    drawn on black so the camera image never leaves the process."""
    import cv2

    canvas = frame_bgr.copy() if show_video else np.zeros_like(frame_bgr)
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
        bar_x = max(0, w - 330)
        by = 24
        for name, value in top[:_TOP_EXPRESSIONS]:
            cv2.rectangle(
                canvas,
                (bar_x, by - 10),
                (bar_x + int(100 * max(0.0, min(1.0, value))), by),
                (255, 128, 0),
                -1,
            )
            cv2.putText(
                canvas,
                f"{name} {value:.2f}",
                (bar_x + 106, by),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
            )
            by += 18
    return canvas


class DebugView:
    """Local OpenCV window; render() returns False when the user quits.

    Keys: ``q`` quits, ``v`` toggles the camera video behind the overlay.
    """

    def __init__(self, window_name: str = "easyfbt debug", show_video: bool = True):
        import cv2

        self._cv2 = cv2
        self._window = window_name
        self.show_video = show_video
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    def render(
        self,
        frame_bgr: np.ndarray,
        pose: PoseResult | None,
        face: FaceResult | None,
        tracking: TrackingFrame,
    ) -> bool:
        canvas = draw_overlay(frame_bgr, pose, face, tracking, show_video=self.show_video)
        self._cv2.imshow(self._window, canvas)
        key = self._cv2.waitKey(1) & 0xFF
        if key == ord("v"):
            self.show_video = not self.show_video
        return key != ord("q")

    def close(self) -> None:
        self._cv2.destroyWindow(self._window)


class HttpDebugView:
    """Publishes the annotated preview to a DebugHttpServer (headless)."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8089,
        jpeg_quality: int = 80,
        controller=None,
    ):
        import cv2

        self._cv2 = cv2
        self._quality = jpeg_quality
        self._controller = controller
        self.server = DebugHttpServer(host, port, controller=controller)

    def render(
        self,
        frame_bgr: np.ndarray,
        pose: PoseResult | None,
        face: FaceResult | None,
        tracking: TrackingFrame,
    ) -> bool:
        show = self._controller.show_video if self._controller is not None else True
        canvas = draw_overlay(frame_bgr, pose, face, tracking, show_video=show)
        ok, jpeg = self._cv2.imencode(
            ".jpg", canvas, [int(self._cv2.IMWRITE_JPEG_QUALITY), self._quality]
        )
        if ok:
            self.server.update(jpeg.tobytes(), frame_to_dict(tracking))
        return True

    def close(self) -> None:
        self.server.close()


class MultiView:
    """Fans render() out to several views; stops when any view asks to quit."""

    def __init__(self, views: list):
        self._views = views

    def render(self, frame_bgr, pose, face, tracking) -> bool:
        keep_going = True
        for view in self._views:
            keep_going = view.render(frame_bgr, pose, face, tracking) and keep_going
        return keep_going

    def close(self) -> None:
        for view in self._views:
            view.close()

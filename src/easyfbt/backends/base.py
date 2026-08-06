"""Backend protocols.

Heavy CV dependencies stay behind these interfaces so the whole pipeline can
be unit- and integration-tested with fakes, and alternative backends (e.g.
ONNX-based) can be added without touching the pipeline.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from easyfbt.types import FaceResult, PoseResult


class PoseBackend(Protocol):
    def process(self, frame_bgr: np.ndarray, timestamp: float) -> PoseResult | None:
        """Estimate body pose from a BGR frame; None when no person found."""
        ...

    def close(self) -> None: ...


class FaceBackend(Protocol):
    def process(self, frame_bgr: np.ndarray, timestamp: float) -> FaceResult | None:
        """Estimate facial expressions from a BGR frame; None when no face."""
        ...

    def close(self) -> None: ...

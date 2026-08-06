"""Signal smoothing filters.

The One Euro filter (Casiez et al., CHI 2012) gives low jitter at rest and low
lag during fast motion, which is exactly the trade-off body tracking needs.
Vectorised so one filter instance smooths a whole landmark array.
"""

from __future__ import annotations

import math

import numpy as np


class LowPassFilter:
    """First-order low-pass filter over arbitrary-shaped numpy arrays."""

    def __init__(self) -> None:
        self._state: np.ndarray | None = None

    def apply(self, value: np.ndarray, alpha: np.ndarray | float) -> np.ndarray:
        value = np.asarray(value, dtype=float)
        if self._state is None:
            self._state = value.copy()
        else:
            self._state = alpha * value + (1.0 - alpha) * self._state
        return self._state

    @property
    def state(self) -> np.ndarray | None:
        return self._state


class OneEuroFilter:
    """Vectorised One Euro filter.

    :param min_cutoff: baseline cutoff frequency (Hz); lower = smoother.
    :param beta: speed coefficient; higher = less lag on fast motion.
    :param d_cutoff: cutoff for the derivative estimate (Hz).
    """

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.02, d_cutoff: float = 1.0):
        if min_cutoff <= 0 or d_cutoff <= 0:
            raise ValueError("cutoff frequencies must be positive")
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x = LowPassFilter()
        self._dx = LowPassFilter()
        self._last_time: float | None = None

    @staticmethod
    def _alpha(cutoff: np.ndarray | float, dt: float) -> np.ndarray | float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def apply(self, value: np.ndarray, timestamp: float) -> np.ndarray:
        value = np.asarray(value, dtype=float)
        if self._last_time is None:
            self._last_time = timestamp
            self._dx.apply(np.zeros_like(value), 1.0)
            return self._x.apply(value, 1.0)
        dt = timestamp - self._last_time
        if dt <= 0:
            state = self._x.state
            assert state is not None  # noqa: S101 - invariant: set on first apply
            return state
        self._last_time = timestamp
        prev = self._x.state
        assert prev is not None  # noqa: S101 - invariant: set on first apply
        dx = (value - prev) / dt
        edx = self._dx.apply(dx, self._alpha(self.d_cutoff, dt))
        cutoff = self.min_cutoff + self.beta * np.abs(edx)
        return self._x.apply(value, self._alpha(cutoff, dt))

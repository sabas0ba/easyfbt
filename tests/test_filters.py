import numpy as np
import pytest

from easyfbt.filters import LowPassFilter, OneEuroFilter


def test_low_pass_converges():
    f = LowPassFilter()
    f.apply(np.array([0.0]), 1.0)
    for _ in range(200):
        out = f.apply(np.array([10.0]), 0.5)
    assert out[0] == pytest.approx(10.0, abs=1e-3)


def test_one_euro_first_sample_passthrough():
    f = OneEuroFilter()
    out = f.apply(np.array([1.0, 2.0]), timestamp=0.0)
    assert np.allclose(out, [1.0, 2.0])


def test_one_euro_smooths_noise():
    rng = np.random.default_rng(0)
    f = OneEuroFilter(min_cutoff=0.5, beta=0.0)
    target = 1.0
    outputs = []
    for i in range(1, 300):
        noisy = target + rng.normal(scale=0.1)
        outputs.append(f.apply(np.array([noisy]), timestamp=i / 60.0)[0])
    tail = np.array(outputs[100:])
    # Filtered variance must be well below the raw noise variance.
    assert tail.std() < 0.05
    assert tail.mean() == pytest.approx(target, abs=0.05)


def test_one_euro_tracks_fast_motion():
    f = OneEuroFilter(min_cutoff=1.0, beta=1.0)
    out = 0.0
    for i in range(1, 120):
        t = i / 60.0
        out = f.apply(np.array([t * 5.0]), timestamp=t)[0]  # 5 m/s ramp
    # High beta keeps lag small during fast motion.
    assert out == pytest.approx((119 / 60.0) * 5.0, abs=0.3)


def test_one_euro_ignores_non_monotonic_timestamps():
    f = OneEuroFilter()
    f.apply(np.array([1.0]), timestamp=1.0)
    out = f.apply(np.array([99.0]), timestamp=1.0)  # same timestamp: keep state
    assert out[0] == pytest.approx(1.0)


def test_one_euro_rejects_bad_cutoff():
    with pytest.raises(ValueError):
        OneEuroFilter(min_cutoff=0.0)

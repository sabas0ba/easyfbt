import pytest

from easyfbt.expressions import ARKIT_TO_UNIFIED, arkit_to_unified, eye_parameters


def test_direct_mapping():
    out = arkit_to_unified({"jawOpen": 0.7})
    assert out["JawOpen"] == pytest.approx(0.7)


def test_fan_out_mapping():
    out = arkit_to_unified({"mouthFunnel": 0.5})
    for name in (
        "LipFunnelUpperLeft",
        "LipFunnelUpperRight",
        "LipFunnelLowerLeft",
        "LipFunnelLowerRight",
    ):
        assert out[name] == pytest.approx(0.5)


def test_smile_maps_to_corner_pull_and_slant():
    out = arkit_to_unified({"mouthSmileLeft": 1.0})
    assert out["MouthCornerPullLeft"] == 1.0
    assert out["MouthCornerSlantLeft"] == 1.0


def test_values_clamped_to_unit_range():
    out = arkit_to_unified({"jawOpen": 1.7, "mouthClose": -0.4})
    assert out["JawOpen"] == 1.0
    assert out["MouthClosed"] == 0.0


def test_unknown_and_neutral_keys_ignored():
    assert arkit_to_unified({"_neutral": 0.9, "notAShape": 0.5}) == {}


def test_all_mapping_targets_are_pascal_case():
    for targets in ARKIT_TO_UNIFIED.values():
        for name in targets:
            assert name[0].isupper() and " " not in name


def test_eye_parameters_neutral():
    out = eye_parameters({})
    assert out["EyeLeftX"] == 0.0
    assert out["EyeY"] == 0.0
    assert out["EyeLidLeft"] == pytest.approx(0.75)


def test_eye_parameters_look_left():
    shapes = {"eyeLookOutLeft": 1.0, "eyeLookInRight": 1.0}
    out = eye_parameters(shapes)
    assert out["EyeLeftX"] == pytest.approx(-1.0)
    assert out["EyeRightX"] == pytest.approx(-1.0)
    assert out["EyeX"] == pytest.approx(-1.0)


def test_eye_parameters_blink():
    out = eye_parameters({"eyeBlinkLeft": 1.0})
    assert out["EyeLidLeft"] == pytest.approx(0.0)
    assert out["EyeLidRight"] == pytest.approx(0.75)

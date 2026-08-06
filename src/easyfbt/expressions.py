"""ARKit blendshapes -> VRCFT Unified Expressions conversion.

MediaPipe's face landmarker outputs the 52 ARKit-style blendshapes
(camelCase).  VRCFT's parameter system is built on Unified Expressions (UE)
shape names (PascalCase).  This module applies the standard ARKit->UE mapping
documented by VRCFaceTracking; ARKit shapes that fan out to several UE shapes
(e.g. ``mouthFunnel``) are duplicated to each target.

Eye gaze and eyelid openness are derived as the combined VRCFT parameters
``EyeLeftX/Y``, ``EyeRightX/Y`` (range [-1, 1], +X right, +Y up) and
``EyeLidLeft/Right`` (0 closed, ~0.75 neutral, 1 wide).
"""

from __future__ import annotations

#: ARKit blendshape -> Unified Expressions shape(s).
ARKIT_TO_UNIFIED: dict[str, tuple[str, ...]] = {
    "browDownLeft": ("BrowLowererLeft", "BrowPinchLeft"),
    "browDownRight": ("BrowLowererRight", "BrowPinchRight"),
    "browInnerUp": ("BrowInnerUpLeft", "BrowInnerUpRight"),
    "browOuterUpLeft": ("BrowOuterUpLeft",),
    "browOuterUpRight": ("BrowOuterUpRight",),
    "cheekPuff": ("CheekPuffLeft", "CheekPuffRight"),
    "cheekSquintLeft": ("CheekSquintLeft",),
    "cheekSquintRight": ("CheekSquintRight",),
    "eyeBlinkLeft": ("EyeClosedLeft",),
    "eyeBlinkRight": ("EyeClosedRight",),
    "eyeSquintLeft": ("EyeSquintLeft",),
    "eyeSquintRight": ("EyeSquintRight",),
    "eyeWideLeft": ("EyeWideLeft",),
    "eyeWideRight": ("EyeWideRight",),
    "jawForward": ("JawForward",),
    "jawLeft": ("JawLeft",),
    "jawOpen": ("JawOpen",),
    "jawRight": ("JawRight",),
    "mouthClose": ("MouthClosed",),
    "mouthDimpleLeft": ("MouthDimpleLeft",),
    "mouthDimpleRight": ("MouthDimpleRight",),
    "mouthFrownLeft": ("MouthFrownLeft",),
    "mouthFrownRight": ("MouthFrownRight",),
    "mouthFunnel": (
        "LipFunnelUpperLeft",
        "LipFunnelUpperRight",
        "LipFunnelLowerLeft",
        "LipFunnelLowerRight",
    ),
    "mouthLeft": ("MouthUpperLeft", "MouthLowerLeft"),
    "mouthRight": ("MouthUpperRight", "MouthLowerRight"),
    "mouthLowerDownLeft": ("MouthLowerDownLeft",),
    "mouthLowerDownRight": ("MouthLowerDownRight",),
    "mouthPressLeft": ("MouthPressLeft",),
    "mouthPressRight": ("MouthPressRight",),
    "mouthPucker": (
        "LipPuckerUpperLeft",
        "LipPuckerUpperRight",
        "LipPuckerLowerLeft",
        "LipPuckerLowerRight",
    ),
    "mouthRollLower": ("LipSuckLowerLeft", "LipSuckLowerRight"),
    "mouthRollUpper": ("LipSuckUpperLeft", "LipSuckUpperRight"),
    "mouthShrugLower": ("MouthRaiserLower",),
    "mouthShrugUpper": ("MouthRaiserUpper",),
    "mouthSmileLeft": ("MouthCornerPullLeft", "MouthCornerSlantLeft"),
    "mouthSmileRight": ("MouthCornerPullRight", "MouthCornerSlantRight"),
    "mouthStretchLeft": ("MouthStretchLeft",),
    "mouthStretchRight": ("MouthStretchRight",),
    "mouthUpperUpLeft": ("MouthUpperUpLeft",),
    "mouthUpperUpRight": ("MouthUpperUpRight",),
    "noseSneerLeft": ("NoseSneerLeft",),
    "noseSneerRight": ("NoseSneerRight",),
    "tongueOut": ("TongueOut",),
}


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def arkit_to_unified(blendshapes: dict[str, float]) -> dict[str, float]:
    """Convert ARKit blendshape weights to Unified Expressions weights.

    Unknown ARKit keys (e.g. ``_neutral``) are ignored.  If several sources
    map to the same UE shape the maximum wins.
    """
    out: dict[str, float] = {}
    for arkit_name, value in blendshapes.items():
        targets = ARKIT_TO_UNIFIED.get(arkit_name)
        if not targets:
            continue
        v = _clamp01(value)
        for target in targets:
            out[target] = max(out.get(target, 0.0), v)
    return out


def eye_parameters(blendshapes: dict[str, float]) -> dict[str, float]:
    """Derive VRCFT combined eye parameters from ARKit eye-look shapes."""

    def g(name: str) -> float:
        return _clamp01(blendshapes.get(name, 0.0))

    left_x = g("eyeLookInLeft") - g("eyeLookOutLeft")  # left eye: in = toward nose = +X
    right_x = g("eyeLookOutRight") - g("eyeLookInRight")
    left_y = g("eyeLookUpLeft") - g("eyeLookDownLeft")
    right_y = g("eyeLookUpRight") - g("eyeLookDownRight")
    lid_left = (1.0 - g("eyeBlinkLeft")) * 0.75 + g("eyeWideLeft") * 0.25
    lid_right = (1.0 - g("eyeBlinkRight")) * 0.75 + g("eyeWideRight") * 0.25
    return {
        "EyeLeftX": left_x,
        "EyeLeftY": left_y,
        "EyeRightX": right_x,
        "EyeRightY": right_y,
        "EyeX": (left_x + right_x) / 2.0,
        "EyeY": (left_y + right_y) / 2.0,
        "EyeLidLeft": _clamp01(lid_left),
        "EyeLidRight": _clamp01(lid_right),
    }

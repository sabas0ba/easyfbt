"""Golden-sample tests: a scripted, fully deterministic session is run through
the real pipeline and *every* output packet (VMT / VRChat / VRCFT / UDP JSON)
is decoded and compared against committed golden files.

Regenerate after intentional output changes with:

    pytest tests/test_golden_outputs.py --update-goldens

and review the golden diff like any other code change.
"""

import json
import math
import socket
from pathlib import Path

import numpy as np
import pytest
from tests.conftest import assert_close, standing_landmarks
from tests.fakes import FakeClock, FakeSource, StaticFaceBackend, StaticPoseBackend

from easyfbt.app import CameraUnit, Pipeline
from easyfbt.config import parse_config
from easyfbt.osc import decode_message
from easyfbt.outputs.udp_json import UdpJsonOutput
from easyfbt.outputs.vmt import VmtOutput
from easyfbt.outputs.vrcft import VrcftOutput
from easyfbt.outputs.vrchat import VrchatTrackerOutput

GOLDEN_PATH = Path(__file__).parent / "golden" / "scripted_session.json"
STEPS = 4
TOLERANCE = 1e-3  # absorbs libm/platform float differences, not behaviour changes


def scripted_landmarks(step: int) -> np.ndarray:
    """Standing skeleton, yawing 10 deg per step and raising the left wrist."""
    lm = standing_landmarks()
    theta = math.radians(10.0 * step)
    c, s = math.cos(theta), math.sin(theta)
    rot_y = np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])
    lm = lm @ rot_y.T
    lm[15] = lm[15] + np.array([0.0, 0.12 * step, 0.0])  # LEFT_WRIST raise
    return lm


def scripted_blendshapes(step: int) -> dict[str, float]:
    return {
        "jawOpen": min(1.0, 0.2 * step),
        "mouthSmileLeft": max(0.0, 0.8 - 0.2 * step),
        "mouthSmileRight": max(0.0, 0.7 - 0.2 * step),
        "eyeBlinkLeft": min(1.0, 0.3 * step),
        "eyeLookUpLeft": 0.3,
        "eyeLookUpRight": 0.3,
        "mouthFunnel": 0.1 * step,
    }


def round_floats(value, digits: int = 5):
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, list):
        return [round_floats(v, digits) for v in value]
    if isinstance(value, dict):
        return {k: round_floats(v, digits) for k, v in value.items()}
    return value


@pytest.fixture
def receivers():
    socks = {}
    for name in ("vmt", "vrchat", "vrcft", "udp_json"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(2.0)
        socks[name] = sock
    yield socks
    for sock in socks.values():
        sock.close()


def run_scripted_session(receivers) -> dict:
    config = parse_config({})
    source = FakeSource()
    camera = CameraUnit(source=source, yaw_deg=0.0)
    clock = FakeClock()
    port = {name: sock.getsockname()[1] for name, sock in receivers.items()}
    outputs = [
        VmtOutput("127.0.0.1", port["vmt"]),
        VrchatTrackerOutput("127.0.0.1", port["vrchat"]),
        VrcftOutput("127.0.0.1", port["vrcft"]),
        UdpJsonOutput("127.0.0.1", port["udp_json"]),
    ]
    pipeline = Pipeline(config, [camera], outputs, clock=clock)

    steps = []
    for step in range(STEPS):
        camera.pose_backend = StaticPoseBackend(scripted_landmarks(step))
        camera.face_backend = StaticFaceBackend(
            scripted_blendshapes(step), eye_pitch=0.05, eye_yaw=-0.1
        )
        source.push(clock())
        tracking = pipeline.step()
        clock.tick()

        n_trackers = len(tracking.trackers)
        n_expr = len(tracking.expressions)
        record = {
            "vmt": [receivers["vmt"].recv(4096) for _ in range(n_trackers)],
            "vrchat": [receivers["vrchat"].recv(4096) for _ in range(2 * n_trackers)],
            "vrcft": [receivers["vrcft"].recv(4096) for _ in range(n_expr + 1)],  # +1 eyes
            "udp_json": json.loads(receivers["udp_json"].recv(65536).decode()),
        }
        for osc_name in ("vmt", "vrchat", "vrcft"):
            decoded = []
            for packet in record[osc_name]:
                addr, args = decode_message(packet)
                decoded.append({"addr": addr, "args": round_floats(args)})
            record[osc_name] = decoded
        record["udp_json"] = round_floats(record["udp_json"])
        steps.append(record)
    pipeline.stop()
    return {"steps": steps}


def test_scripted_session_matches_golden(receivers, update_goldens):
    actual = run_scripted_session(receivers)

    if update_goldens:
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(actual, indent=1, sort_keys=True) + "\n")
        pytest.skip(f"golden rewritten: {GOLDEN_PATH}")

    assert GOLDEN_PATH.is_file(), (
        f"golden file missing: {GOLDEN_PATH}; generate it with --update-goldens"
    )
    expected = json.loads(GOLDEN_PATH.read_text())
    assert_close(actual, expected, TOLERANCE)


def test_scripted_session_shape_sanity(receivers):
    """Structural checks that stay valid even when goldens are regenerated."""
    result = run_scripted_session(receivers)
    assert len(result["steps"]) == STEPS
    first = result["steps"][0]

    assert all(m["addr"] == "/VMT/Room/Unity" for m in first["vmt"])
    assert len(first["vmt"][0]["args"]) == 10

    vrchat_addrs = [m["addr"] for m in first["vrchat"]]
    assert "/tracking/trackers/1/position" in vrchat_addrs
    assert "/tracking/trackers/1/rotation" in vrchat_addrs

    vrcft_addrs = {m["addr"] for m in first["vrcft"]}
    assert "/avatar/parameters/v2/JawOpen" in vrcft_addrs
    assert "/tracking/eye/CenterPitchYaw" in vrcft_addrs

    doc = first["udp_json"]
    assert doc["v"] == 1
    assert {t["role"] for t in doc["trackers"]} == {
        "hip",
        "left_foot",
        "right_foot",
        "left_knee",
        "right_knee",
        "chest",
    }

    # The scripted yaw must actually show up over the steps: the hip tracker's
    # rotation at step 3 differs from step 0.
    rot0 = result["steps"][0]["udp_json"]["trackers"][0]["rot"]
    rot3 = result["steps"][3]["udp_json"]["trackers"][0]["rot"]
    assert rot0 != rot3

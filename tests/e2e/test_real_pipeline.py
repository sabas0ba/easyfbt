"""End-to-end tests with the REAL MediaPipe models.

A hash-verified portrait photo is fed through the full pipeline -- real
MediaPipe pose/face backends, real fusion/filtering/mapping, real UDP outputs
on loopback -- and the result is checked functionally and against a tolerant
golden sample.

Prerequisites (both hash-verified):

    pip install --require-hashes -r requirements/runtime.lock
    python tools/fetch_models.py
    python tools/fetch_test_assets.py

Run with:  pytest -m e2e

Model inference is float math on varying CPUs, so the golden comparison uses
a tolerance (E2E_TOLERANCE) rather than exact equality; regenerate the golden
with --update-goldens when outputs change intentionally.
"""

import json
import socket
from pathlib import Path

import pytest
from tests.conftest import assert_close
from tests.fakes import FakeClock

from easyfbt.app import CameraUnit, Pipeline
from easyfbt.capture import LatestFrame
from easyfbt.config import parse_config
from easyfbt.osc import decode_message
from easyfbt.outputs.udp_json import UdpJsonOutput
from easyfbt.outputs.vrcft import VrcftOutput
from easyfbt.outputs.vrchat import VrchatTrackerOutput

pytestmark = pytest.mark.e2e

REPO = Path(__file__).resolve().parent.parent.parent
POSE_MODEL = REPO / "models" / "pose_landmarker_full.task"
FACE_MODEL = REPO / "models" / "face_landmarker.task"
PORTRAIT = Path(__file__).parent / "assets" / "portrait.jpg"
GOLDEN_PATH = Path(__file__).parent / "golden" / "portrait_session.json"

#: Model outputs drift slightly across CPUs / XNNPACK builds.
E2E_TOLERANCE = 0.05

WARMUP_STEPS = 5


def _require(path: Path, hint: str):
    if not path.is_file():
        pytest.skip(f"{path.name} missing; run: python {hint}")


@pytest.fixture(scope="module")
def portrait_frame():
    cv2 = pytest.importorskip("cv2")
    pytest.importorskip("mediapipe")
    _require(POSE_MODEL, "tools/fetch_models.py")
    _require(FACE_MODEL, "tools/fetch_models.py")
    _require(PORTRAIT, "tools/fetch_test_assets.py")
    frame = cv2.imread(str(PORTRAIT))
    assert frame is not None
    return frame


class StillImageSource:
    """Feeds the same frame repeatedly (a person standing still)."""

    def __init__(self, frame):
        self.frame = frame
        self.latest = LatestFrame()

    def start(self):
        pass

    def stop(self):
        pass

    def push(self, ts: float):
        self.latest.put(self.frame, ts)


@pytest.fixture(scope="module")
def receivers():
    socks = {}
    for name in ("vrchat", "vrcft", "udp_json"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(5.0)
        socks[name] = sock
    yield socks
    for sock in socks.values():
        sock.close()


@pytest.fixture(scope="module")
def session_result(portrait_frame, receivers):
    """Run the real pipeline for a few frames; return the final step's data."""
    from easyfbt.backends.mediapipe_backend import MediaPipeFaceBackend, MediaPipePoseBackend
    from easyfbt.types import TrackerRole

    # All 8 roles: the portrait shows only the upper body, so feet/knees must
    # be dropped by visibility gating while hip/chest/elbows survive.
    config = parse_config({"tracking": {"roles": [r.value for r in TrackerRole]}})
    source = StillImageSource(portrait_frame)
    camera = CameraUnit(
        source=source,
        yaw_deg=0.0,
        pose_backend=MediaPipePoseBackend(str(POSE_MODEL)),
        face_backend=MediaPipeFaceBackend(str(FACE_MODEL)),
    )
    port = {name: sock.getsockname()[1] for name, sock in receivers.items()}
    outputs = [
        VrchatTrackerOutput("127.0.0.1", port["vrchat"]),
        VrcftOutput("127.0.0.1", port["vrcft"]),
        UdpJsonOutput("127.0.0.1", port["udp_json"]),
    ]
    clock = FakeClock()
    pipeline = Pipeline(config, [camera], outputs, clock=clock)

    tracking = None
    for _ in range(WARMUP_STEPS):
        for sock in receivers.values():  # drop packets from earlier steps
            sock.setblocking(False)
            try:
                while True:
                    sock.recv(65536)
            except BlockingIOError:
                pass
            sock.settimeout(5.0)
        source.push(clock())
        tracking = pipeline.step()
        clock.tick()

    assert tracking is not None
    result = {
        "udp_json": json.loads(receivers["udp_json"].recv(65536).decode()),
        "vrchat": [
            decode_message(receivers["vrchat"].recv(4096))
            for _ in range(2 * len(tracking.trackers))
        ],
        "vrcft": [
            decode_message(receivers["vrcft"].recv(4096))
            for _ in range(len(tracking.expressions) + 1)
        ],
    }
    pipeline.stop()
    return result


def test_face_detected_with_plausible_expressions(session_result):
    expr = session_result["udp_json"]["expressions"]
    # The portrait is a smiling face with open eyes.
    assert expr["MouthCornerPullLeft"] > 0.5
    assert expr["MouthCornerPullRight"] > 0.5
    assert expr["JawOpen"] < 0.5
    assert expr["EyeClosedLeft"] < 0.5
    # UE blendshapes are [0, 1]; combined gaze parameters (EyeLeftX etc.) are
    # [-1, 1].
    gaze = {"EyeLeftX", "EyeLeftY", "EyeRightX", "EyeRightY", "EyeX", "EyeY"}
    for name, value in expr.items():
        low = -1.0 if name in gaze else 0.0
        assert low <= value <= 1.0, f"{name}={value} out of range"


def test_upper_body_visibility_gating(session_result):
    roles = {t["role"] for t in session_result["udp_json"]["trackers"]}
    # Only the upper body is in frame: legs must be gated out, not hallucinated.
    assert {"hip", "chest", "left_elbow", "right_elbow"} <= roles
    assert not {"left_foot", "right_foot", "left_knee", "right_knee"} & roles


def test_vrchat_packets_wellformed(session_result):
    for addr, args in session_result["vrchat"]:
        assert addr.startswith("/tracking/trackers/")
        assert len(args) == 3
        assert all(isinstance(v, float) for v in args)
        if addr.endswith("/position"):
            assert all(abs(v) < 10.0 for v in args)  # metres, near the origin
        else:
            assert all(abs(v) <= 360.0 for v in args)  # euler degrees


def test_vrcft_parameter_contract(session_result):
    addresses = {addr for addr, _ in session_result["vrcft"]}
    assert "/tracking/eye/CenterPitchYaw" in addresses
    param_addrs = addresses - {"/tracking/eye/CenterPitchYaw"}
    assert param_addrs  # face params present
    assert all(a.startswith("/avatar/parameters/v2/") for a in param_addrs)


def test_matches_golden_sample(session_result, update_goldens):
    doc = session_result["udp_json"]
    if update_goldens:
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        pytest.skip(f"golden rewritten: {GOLDEN_PATH}")
    assert GOLDEN_PATH.is_file(), (
        f"golden file missing: {GOLDEN_PATH}; generate with pytest -m e2e --update-goldens"
    )
    expected = json.loads(GOLDEN_PATH.read_text())
    assert_close(doc, expected, E2E_TOLERANCE)

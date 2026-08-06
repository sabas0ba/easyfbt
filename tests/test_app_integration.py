"""End-to-end pipeline test: fake cameras/backends -> real UDP outputs."""

import json
import socket

import numpy as np
import pytest
from tests.conftest import standing_landmarks

from easyfbt import trackers as tk
from easyfbt.app import CameraUnit, Pipeline
from easyfbt.capture import LatestFrame
from easyfbt.config import parse_config
from easyfbt.osc import decode_message
from easyfbt.outputs.udp_json import UdpJsonOutput
from easyfbt.outputs.vrcft import VrcftOutput
from easyfbt.types import FaceResult, PoseResult


class FakeSource:
    def __init__(self):
        self.latest = LatestFrame()
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def push(self, ts: float):
        self.latest.put(np.zeros((4, 4, 3), dtype=np.uint8), ts)


class FakePoseBackend:
    """Returns the standing skeleton in *camera* space for a yaw-0 camera."""

    def __init__(self):
        room = standing_landmarks()
        # Invert the yaw-0 room transform: camera x = room x, y = -room y,
        # z = -room z, so that to_room() reproduces the standing skeleton.
        self.camera_landmarks = room * np.array([1.0, -1.0, -1.0])
        self.closed = False

    def process(self, frame, timestamp):
        return PoseResult(
            world_landmarks=self.camera_landmarks.copy(),
            visibility=np.ones(tk.NUM_LANDMARKS),
            timestamp=timestamp,
        )

    def close(self):
        self.closed = True


class NoDetectionBackend:
    def process(self, frame, timestamp):
        return None

    def close(self):
        pass


class FakeFaceBackend:
    def __init__(self, jaw=0.5):
        self.jaw = jaw

    def process(self, frame, timestamp):
        return FaceResult(
            blendshapes={"jawOpen": self.jaw, "eyeBlinkLeft": 1.0},
            confidence=0.9,
            timestamp=timestamp,
        )

    def close(self):
        pass


@pytest.fixture
def receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    yield sock
    sock.close()


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def tick(self, dt=1 / 30):
        self.now += dt
        return self.now

    def __call__(self):
        return self.now


def make_pipeline(receiver, outputs=None, cameras=None):
    config = parse_config({})
    clock = FakeClock()
    if cameras is None:
        source = FakeSource()
        cameras = [
            CameraUnit(
                source=source,
                yaw_deg=0.0,
                pose_backend=FakePoseBackend(),
                face_backend=FakeFaceBackend(),
            )
        ]
    if outputs is None:
        outputs = [UdpJsonOutput("127.0.0.1", receiver.getsockname()[1])]
    return Pipeline(config, cameras, outputs, clock=clock), cameras, clock


def test_end_to_end_udp_json(receiver):
    pipeline, cameras, clock = make_pipeline(receiver)
    cameras[0].source.push(clock())
    pipeline.step()
    doc = json.loads(receiver.recv(65536).decode())

    roles = {t["role"] for t in doc["trackers"]}
    assert {"hip", "left_foot", "right_foot", "left_knee", "right_knee", "chest"} == roles
    hip = next(t for t in doc["trackers"] if t["role"] == "hip")
    assert hip["pos"][1] == pytest.approx(1.70 * tk.HIP_HEIGHT_RATIO, abs=1e-3)
    assert doc["expressions"]["JawOpen"] == pytest.approx(0.5)
    assert doc["expressions"]["EyeLidLeft"] == pytest.approx(0.0)  # blink
    pipeline.stop()


def test_end_to_end_vrcft_osc(receiver):
    outputs = [VrcftOutput("127.0.0.1", receiver.getsockname()[1], send_eyes=False)]
    pipeline, cameras, clock = make_pipeline(receiver, outputs=outputs)
    cameras[0].source.push(clock())
    tracking = pipeline.step()

    received = {}
    for _ in range(len(tracking.expressions)):
        addr, args = decode_message(receiver.recv(4096))
        received[addr] = args[0]
    assert received["/avatar/parameters/v2/JawOpen"] == pytest.approx(0.5)
    assert received["/avatar/parameters/v2/EyeClosedLeft"] == pytest.approx(1.0)
    pipeline.stop()


def test_stale_frame_keeps_last_pose(receiver):
    pipeline, cameras, clock = make_pipeline(receiver)
    cameras[0].source.push(clock())
    first = pipeline.step()
    assert first.trackers
    clock.tick()
    second = pipeline.step()  # no new frame pushed: same seq is skipped
    assert len(second.trackers) == len(first.trackers)
    pipeline.stop()


def test_detection_loss_keeps_last_good_pose(receiver):
    pipeline, cameras, clock = make_pipeline(receiver)
    cameras[0].source.push(clock())
    assert pipeline.step().trackers
    cameras[0].pose_backend = NoDetectionBackend()
    clock.tick()
    cameras[0].source.push(clock())
    assert pipeline.step().trackers  # last good pose retained
    pipeline.stop()


def test_two_cameras_fuse(receiver):
    a, b = FakeSource(), FakeSource()
    cameras = [
        CameraUnit(source=a, yaw_deg=0.0, pose_backend=FakePoseBackend()),
        CameraUnit(source=b, yaw_deg=0.0, pose_backend=FakePoseBackend()),
    ]
    pipeline, cameras, clock = make_pipeline(receiver, cameras=cameras)
    a.push(clock())
    b.push(clock())
    tracking = pipeline.step()
    assert tracking.trackers  # identical cameras agree; fusion output intact
    hip = next(t for t in tracking.trackers if t.role.value == "hip")
    assert hip.position[1] == pytest.approx(1.70 * tk.HIP_HEIGHT_RATIO, abs=1e-3)
    pipeline.stop()


def test_lifecycle_start_stop(receiver):
    pipeline, cameras, _clock = make_pipeline(receiver)
    pipeline.start()
    assert cameras[0].source.started
    pipeline.stop()
    assert cameras[0].source.stopped
    assert cameras[0].pose_backend.closed


def test_pipeline_requires_cameras(receiver):
    with pytest.raises(ValueError):
        Pipeline(parse_config({}), [], [])

"""Outputs are exercised over real loopback UDP sockets and decoded back."""

import json
import socket

import numpy as np
import pytest

from easyfbt import osc, quat
from easyfbt.outputs.udp_json import UdpJsonOutput
from easyfbt.outputs.vmt import VmtOutput
from easyfbt.outputs.vrcft import VrcftOutput
from easyfbt.outputs.vrchat import VrchatTrackerOutput
from easyfbt.types import FaceResult, TrackerPose, TrackerRole, TrackingFrame


@pytest.fixture
def receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    yield sock
    sock.close()


def recv_all(sock, count):
    return [sock.recv(4096) for _ in range(count)]


def make_frame() -> TrackingFrame:
    hip = TrackerPose(
        TrackerRole.HIP,
        position=np.array([0.5, 0.9, -1.0]),
        rotation=quat.IDENTITY.copy(),
    )
    foot = TrackerPose(
        TrackerRole.LEFT_FOOT,
        position=np.array([0.2, 0.1, -1.0]),
        rotation=quat.from_axis_angle(np.array([0.0, 1.0, 0.0]), 0.5),
    )
    return TrackingFrame(
        trackers=[hip, foot],
        expressions={"JawOpen": 0.25, "EyeLidLeft": 0.75},
        face=FaceResult(blendshapes={}, eye_pitch=0.1, eye_yaw=-0.2),
        timestamp=12.5,
        fps=30.0,
    )


def test_vmt_output(receiver):
    out = VmtOutput("127.0.0.1", receiver.getsockname()[1])
    out.send(make_frame())
    packets = recv_all(receiver, 2)
    out.close()

    addr, args = osc.decode_message(packets[0])
    assert addr == "/VMT/Room/Unity"
    index, enable, _timeoffset, x, y, z, qx, qy, qz, qw = args
    assert (index, enable) == (1, 1)
    assert (x, y) == (pytest.approx(0.5), pytest.approx(0.9))
    assert z == pytest.approx(1.0)  # Unity conversion flips Z
    assert (qx, qy, qz, qw) == (0.0, 0.0, 0.0, 1.0)


def test_vrchat_output(receiver):
    out = VrchatTrackerOutput("127.0.0.1", receiver.getsockname()[1])
    out.send(make_frame())
    packets = recv_all(receiver, 4)
    out.close()

    addr0, pos = osc.decode_message(packets[0])
    addr1, rot = osc.decode_message(packets[1])
    assert addr0 == "/tracking/trackers/1/position"
    assert addr1 == "/tracking/trackers/1/rotation"
    assert pos == [pytest.approx(0.5), pytest.approx(0.9), pytest.approx(1.0)]
    assert rot == [pytest.approx(0.0), pytest.approx(0.0), pytest.approx(0.0)]
    addr2, _ = osc.decode_message(packets[2])
    assert addr2 == "/tracking/trackers/2/position"


def test_vrcft_output_parameters_and_eyes(receiver):
    out = VrcftOutput("127.0.0.1", receiver.getsockname()[1])
    out.send(make_frame())
    packets = recv_all(receiver, 3)
    out.close()

    decoded = dict((addr, args) for addr, args in (osc.decode_message(p) for p in packets))
    assert decoded["/avatar/parameters/v2/JawOpen"] == [pytest.approx(0.25)]
    assert decoded["/avatar/parameters/v2/EyeLidLeft"] == [pytest.approx(0.75)]
    pitch, yaw = decoded["/tracking/eye/CenterPitchYaw"]
    assert pitch == pytest.approx(-5.7296, abs=1e-3)  # 0.1 rad up -> negative pitch
    assert yaw == pytest.approx(11.459, abs=1e-3)


def test_vrcft_custom_prefix_no_eyes(receiver):
    out = VrcftOutput("127.0.0.1", receiver.getsockname()[1], address_prefix="/ue", send_eyes=False)
    out.send(make_frame())
    packets = recv_all(receiver, 2)
    out.close()
    addresses = {osc.decode_message(p)[0] for p in packets}
    assert addresses == {"/ue/JawOpen", "/ue/EyeLidLeft"}


def test_vrcft_rejects_bad_prefix():
    with pytest.raises(ValueError):
        VrcftOutput(address_prefix="nope")


def test_vrcft_skips_empty_frame(receiver):
    out = VrcftOutput("127.0.0.1", receiver.getsockname()[1])
    out.send(TrackingFrame())
    out.close()
    with pytest.raises(TimeoutError):
        receiver.settimeout(0.2)
        receiver.recv(4096)


def test_udp_json_output(receiver):
    out = UdpJsonOutput("127.0.0.1", receiver.getsockname()[1])
    out.send(make_frame())
    doc = json.loads(receiver.recv(65536).decode())
    out.close()

    assert doc["v"] == 1
    assert doc["t"] == pytest.approx(12.5)
    assert doc["fps"] == pytest.approx(30.0)
    assert doc["trackers"][0]["role"] == "hip"
    assert doc["trackers"][0]["index"] == 1
    assert doc["trackers"][0]["pos"] == [0.5, 0.9, -1.0]
    assert doc["expressions"]["JawOpen"] == pytest.approx(0.25)
    assert doc["eyes"]["pitch"] == pytest.approx(0.1)


def test_missing_receiver_does_not_raise():
    # Port 9 (discard) is almost certainly closed; sendto must not blow up.
    out = UdpJsonOutput("127.0.0.1", 9)
    out.send(make_frame())
    out.close()

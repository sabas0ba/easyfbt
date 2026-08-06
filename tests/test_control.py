"""Controller: validation, hot-apply, restart-required detection, persistence."""

import json
import socket
import tomllib

import pytest
from tests.conftest import standing_landmarks
from tests.fakes import FakeClock, FakeSource, StaticPoseBackend

from easyfbt.app import CameraUnit, Pipeline
from easyfbt.config import parse_config
from easyfbt.config_io import config_to_dict
from easyfbt.control import Controller
from easyfbt.outputs.udp_json import UdpJsonOutput


def make_receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2.0)
    return sock


@pytest.fixture
def rig(tmp_path):
    config = parse_config({})
    source = FakeSource()
    cameras = [
        CameraUnit(source=source, yaw_deg=0.0, pose_backend=StaticPoseBackend(standing_landmarks()))
    ]
    clock = FakeClock()

    receivers = {}

    def outputs_builder(cfg):
        if not cfg.udp_json.enabled:
            return []
        return [UdpJsonOutput(cfg.udp_json.host, cfg.udp_json.port)]

    pipeline = Pipeline(config, cameras, [], clock=clock)
    controller = Controller(config, tmp_path / "config.toml", pipeline, outputs_builder)
    return controller, pipeline, source, clock, receivers


def test_get_config_matches_dict(rig):
    controller = rig[0]
    assert controller.get_config() == config_to_dict(controller.config)


def test_invalid_config_rejected_and_unchanged(rig):
    controller = rig[0]
    before = controller.get_config()
    result = controller.set_config({"tracking": {"target_fps": 0}})
    assert result["ok"] is False
    assert "target_fps" in result["message"]
    assert controller.get_config() == before


def test_unknown_key_rejected(rig):
    controller = rig[0]
    result = controller.set_config({"tracking": {"nope": 1}})
    assert result["ok"] is False


def test_output_toggle_swaps_outputs_live(rig):
    controller, pipeline, source, clock, _ = rig
    receiver = make_receiver()
    try:
        cfg = controller.get_config()
        cfg["output"]["udp_json"]["enabled"] = True
        cfg["output"]["udp_json"]["port"] = receiver.getsockname()[1]
        result = controller.set_config(cfg)
        assert result["ok"] and result["restart_required"] == []

        source.push(clock())
        pipeline.step()
        doc = json.loads(receiver.recv(65536).decode())
        assert doc["v"] == 1  # new sink actually receives frames

        cfg["output"]["udp_json"]["enabled"] = False
        assert controller.set_config(cfg)["ok"]
        clock.tick()
        source.push(clock())
        pipeline.step()
        receiver.settimeout(0.2)
        with pytest.raises(TimeoutError):
            receiver.recv(65536)  # sink removed live
    finally:
        receiver.close()
    pipeline.stop()


def test_camera_yaw_hot_applied(rig):
    controller, pipeline, source, clock, _ = rig
    source.push(clock())
    hip0 = next(t for t in pipeline.step().trackers if t.role.value == "hip")
    fwd0 = hip0.rotation.copy()

    cfg = controller.get_config()
    cfg["camera"][0]["yaw_deg"] = 90.0
    result = controller.set_config(cfg)
    assert result["ok"] and result["restart_required"] == []

    clock.tick()
    source.push(clock())
    hip1 = next(t for t in pipeline.step().trackers if t.role.value == "hip")
    assert not (abs(hip1.rotation - fwd0) < 1e-6).all()  # orientation changed
    pipeline.stop()


def test_tracking_roles_hot_applied(rig):
    controller, pipeline, source, clock, _ = rig
    cfg = controller.get_config()
    cfg["tracking"]["roles"] = ["hip"]
    assert controller.set_config(cfg)["ok"]
    source.push(clock())
    tracking = pipeline.step()
    assert [t.role.value for t in tracking.trackers] == ["hip"]
    pipeline.stop()


def test_restart_required_fields_flagged(rig):
    controller = rig[0]
    cfg = controller.get_config()
    cfg["camera"][0]["device"] = 3
    cfg["models"]["pose_model"] = "elsewhere.task"
    cfg["debug"]["http_port"] = 9999
    result = controller.set_config(cfg)
    assert result["ok"]
    assert "camera[0].device" in result["restart_required"]
    assert "models.pose_model" in result["restart_required"]
    assert "debug.http_port" in result["restart_required"]
    # Desired config is retained so saving persists it.
    assert controller.get_config()["camera"][0]["device"] == 3


def test_camera_count_change_flagged(rig):
    controller = rig[0]
    cfg = controller.get_config()
    cfg["camera"].append({"device": 1})
    result = controller.set_config(cfg)
    assert result["ok"]
    assert any("台数" in r for r in result["restart_required"])


def test_save_persists_toml(rig, tmp_path):
    controller = rig[0]
    cfg = controller.get_config()
    cfg["debug"]["show_video"] = False
    cfg["output"]["vmt"]["enabled"] = True
    result = controller.set_config(cfg, save=True)
    assert result["ok"]
    saved = tomllib.loads(controller.config_path.read_text())
    assert saved["debug"]["show_video"] is False
    assert saved["output"]["vmt"]["enabled"] is True
    assert controller.show_video is False


def test_show_video_hot(rig):
    controller = rig[0]
    assert controller.show_video is True
    cfg = controller.get_config()
    cfg["debug"]["show_video"] = False
    assert controller.set_config(cfg)["ok"]
    assert controller.show_video is False

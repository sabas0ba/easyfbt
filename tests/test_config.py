import tomllib
from pathlib import Path

import pytest

from easyfbt.config import ConfigError, load_config, parse_config
from easyfbt.types import TrackerRole

EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.toml"


def parse(text: str):
    return parse_config(tomllib.loads(text))


def test_defaults():
    cfg = parse("")
    assert len(cfg.cameras) == 1
    assert cfg.cameras[0].device == 0
    assert cfg.vrchat.enabled and cfg.vrchat.port == 9000
    assert cfg.vmt.enabled is False and cfg.vmt.port == 39570
    assert cfg.vrcft.address_prefix == "/avatar/parameters/v2/"


def test_example_config_is_valid():
    cfg = load_config(EXAMPLE)
    assert cfg.cameras[0].position == (0.0, 1.0, 2.0)
    assert TrackerRole.HIP in cfg.tracking.roles


def test_multiple_cameras():
    cfg = parse(
        """
        [[camera]]
        device = 0
        [[camera]]
        device = 2
        yaw_deg = 90.0
        face = false
        """
    )
    assert len(cfg.cameras) == 2
    assert cfg.cameras[1].device == 2
    assert cfg.cameras[1].yaw_deg == 90.0
    assert cfg.cameras[1].face is False


def test_roles_parsed_to_enum():
    cfg = parse('[tracking]\nroles = ["hip", "left_foot"]')
    assert cfg.tracking.roles == [TrackerRole.HIP, TrackerRole.LEFT_FOOT]


def test_unknown_key_rejected():
    with pytest.raises(ConfigError, match="unknown key"):
        parse("[tracking]\nspeed = 3")


def test_unknown_role_rejected():
    with pytest.raises(ConfigError, match="role"):
        parse('[tracking]\nroles = ["left_toe"]')


def test_bad_port_rejected():
    with pytest.raises(ConfigError, match="port"):
        parse("[output.vrchat]\nport = 70000")


def test_bad_camera_position_rejected():
    with pytest.raises(ConfigError, match="position"):
        parse("[[camera]]\nposition = [1.0, 2.0]")


def test_zero_fps_rejected():
    with pytest.raises(ConfigError, match="target_fps"):
        parse("[tracking]\ntarget_fps = 0")


def test_all_tracking_disabled_rejected():
    with pytest.raises(ConfigError, match="at least one"):
        parse("[[camera]]\npose = false\nface = false")


def test_camera_device_url():
    cfg = parse('[[camera]]\ndevice = "http://host.docker.internal:8080/video"')
    assert cfg.cameras[0].device == "http://host.docker.internal:8080/video"


def test_camera_device_bad_type_rejected():
    with pytest.raises(ConfigError, match="device"):
        parse("[[camera]]\ndevice = 1.5")


def test_debug_http_settings():
    cfg = parse('[debug]\nhttp_enabled = true\nhttp_host = "0.0.0.0"\nhttp_port = 9000')
    assert cfg.debug.http_enabled is True
    assert cfg.debug.http_host == "0.0.0.0"
    assert cfg.debug.http_port == 9000


def test_debug_http_defaults_off():
    cfg = parse("")
    assert cfg.debug.http_enabled is False
    assert cfg.debug.http_port == 8089


def test_debug_http_bad_port_rejected():
    with pytest.raises(ConfigError, match="http_port"):
        parse("[debug]\nhttp_port = 0")


def test_container_config_is_valid():
    cfg = load_config(Path(__file__).resolve().parent.parent / "config.container.toml")
    assert cfg.debug.window is False
    assert cfg.debug.http_enabled is True
    assert cfg.vrchat.host == "host.docker.internal"
    assert cfg.models.pose_model.startswith("/app/models/")

import tomllib

import pytest

from easyfbt.config import Config, parse_config
from easyfbt.config_io import config_to_dict, dump_toml, save_config
from easyfbt.types import TrackerRole


def customised_config() -> Config:
    return parse_config(
        {
            "tracking": {
                "target_fps": 25.0,
                "user_height": 1.62,
                "smoothing_beta": 0.05,
                "roles": ["hip", "left_foot", "left_elbow"],
            },
            "camera": [
                {"device": 2, "yaw_deg": 45.0, "position": [1.0, 1.2, -0.5]},
                {"device": "http://cam.local:8080/video", "face": False},
            ],
            "output": {
                "vmt": {"enabled": True, "port": 39571},
                "vrchat": {"enabled": False},
                "vrcft": {"address_prefix": "/ue/", "send_eyes": False},
                "udp_json": {"enabled": True, "host": "192.168.1.5"},
            },
            "models": {"pose_model": "/opt/m/pose.task"},
            "debug": {"window": False, "show_video": False, "http_enabled": True},
        }
    )


def test_roundtrip_through_toml():
    cfg = customised_config()
    reparsed = parse_config(tomllib.loads(dump_toml(cfg)))
    assert config_to_dict(reparsed) == config_to_dict(cfg)


def test_roundtrip_through_dict():
    cfg = customised_config()
    assert config_to_dict(parse_config(config_to_dict(cfg))) == config_to_dict(cfg)


def test_defaults_roundtrip():
    cfg = Config()
    reparsed = parse_config(tomllib.loads(dump_toml(cfg)))
    assert config_to_dict(reparsed) == config_to_dict(cfg)


def test_dict_shape():
    d = config_to_dict(customised_config())
    assert d["tracking"]["roles"] == ["hip", "left_foot", "left_elbow"]
    assert d["camera"][1]["device"] == "http://cam.local:8080/video"
    assert d["output"]["vmt"]["enabled"] is True
    assert d["debug"]["show_video"] is False
    assert isinstance(d["camera"][0]["position"], list)


def test_string_escaping():
    cfg = Config()
    cfg.vrcft.address_prefix = '/we"ird\\path/'
    reparsed = parse_config(tomllib.loads(dump_toml(cfg)))
    assert reparsed.vrcft.address_prefix == '/we"ird\\path/'


def test_roles_preserved_as_enum():
    cfg = customised_config()
    reparsed = parse_config(tomllib.loads(dump_toml(cfg)))
    assert reparsed.tracking.roles == [
        TrackerRole.HIP,
        TrackerRole.LEFT_FOOT,
        TrackerRole.LEFT_ELBOW,
    ]


def test_save_config_atomic(tmp_path):
    path = tmp_path / "sub" / "config.toml"
    cfg = customised_config()
    save_config(cfg, path)
    assert path.is_file()
    reparsed = parse_config(tomllib.loads(path.read_text()))
    assert config_to_dict(reparsed) == config_to_dict(cfg)
    # Overwrite works and leaves no temp files behind.
    save_config(Config(), path)
    assert [p.name for p in path.parent.iterdir()] == ["config.toml"]


def test_dump_rejects_unknown_types():
    from easyfbt.config_io import _value

    with pytest.raises(TypeError):
        _value(object())

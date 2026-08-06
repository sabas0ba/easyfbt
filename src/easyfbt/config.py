"""Configuration loading (TOML via stdlib :mod:`tomllib`, no extra deps)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from easyfbt.types import TrackerRole

DEFAULT_ROLES = [
    TrackerRole.HIP,
    TrackerRole.LEFT_FOOT,
    TrackerRole.RIGHT_FOOT,
    TrackerRole.LEFT_KNEE,
    TrackerRole.RIGHT_KNEE,
    TrackerRole.CHEST,
]


@dataclass
class CameraConfig:
    #: OpenCV capture source: a local device index (0, 1, ...) or a stream
    #: URL string (MJPEG over http://, rtsp://, ...).  URL sources let a
    #: container consume video without host device passthrough.
    device: int | str = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    #: Camera position in room space, metres.
    position: tuple[float, float, float] = (0.0, 1.0, 2.0)
    #: Yaw of the camera's viewing direction in room space, degrees.
    #: 0 means the camera looks along -Z (e.g. placed at +Z, facing a user
    #: at the origin who faces the camera).
    yaw_deg: float = 0.0
    pose: bool = True
    face: bool = True


@dataclass
class TrackingConfig:
    target_fps: float = 30.0
    user_height: float = 1.70  # metres; scales landmark space to room space
    smoothing_min_cutoff: float = 1.0
    smoothing_beta: float = 0.02
    min_visibility: float = 0.5
    roles: list[TrackerRole] = field(default_factory=lambda: list(DEFAULT_ROLES))


@dataclass
class OscOutputConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 9000


@dataclass
class VmtConfig(OscOutputConfig):
    port: int = 39570


@dataclass
class VrchatConfig(OscOutputConfig):
    enabled: bool = True


@dataclass
class VrcftConfig(OscOutputConfig):
    enabled: bool = True
    address_prefix: str = "/avatar/parameters/v2/"
    send_eyes: bool = True


@dataclass
class UdpJsonConfig(OscOutputConfig):
    port: int = 9199


@dataclass
class ModelsConfig:
    pose_model: str = "models/pose_landmarker_full.task"
    face_model: str = "models/face_landmarker.task"


@dataclass
class DebugConfig:
    window: bool = True
    #: Browser-based debug view (MJPEG + JSON state over HTTP).  The one
    #: debug surface that works from inside a container.
    http_enabled: bool = False
    http_host: str = "127.0.0.1"
    http_port: int = 8089


@dataclass
class Config:
    cameras: list[CameraConfig] = field(default_factory=lambda: [CameraConfig()])
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    vmt: VmtConfig = field(default_factory=VmtConfig)
    vrchat: VrchatConfig = field(default_factory=VrchatConfig)
    vrcft: VrcftConfig = field(default_factory=VrcftConfig)
    udp_json: UdpJsonConfig = field(default_factory=UdpJsonConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)


class ConfigError(ValueError):
    pass


def _apply(obj, data: dict, section: str):
    for key, value in data.items():
        if not hasattr(obj, key):
            raise ConfigError(f"unknown key {key!r} in [{section}]")
        setattr(obj, key, value)
    return obj


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    return parse_config(data)


def parse_config(data: dict) -> Config:
    cfg = Config()

    cameras = data.get("camera", [])
    if cameras:
        cfg.cameras = []
        for i, cam in enumerate(cameras):
            c = CameraConfig()
            _apply(c, {k: v for k, v in cam.items() if k != "position"}, f"camera[{i}]")
            if "position" in cam:
                pos = cam["position"]
                if len(pos) != 3:
                    raise ConfigError(f"camera[{i}].position must have 3 elements")
                c.position = (float(pos[0]), float(pos[1]), float(pos[2]))
            cfg.cameras.append(c)
    if not any(c.pose for c in cfg.cameras) and not any(c.face for c in cfg.cameras):
        raise ConfigError("at least one camera must enable pose or face tracking")

    tracking = dict(data.get("tracking", {}))
    if "roles" in tracking:
        try:
            tracking["roles"] = [TrackerRole(r) for r in tracking["roles"]]
        except ValueError as exc:
            raise ConfigError(f"unknown tracker role: {exc}") from exc
    _apply(cfg.tracking, tracking, "tracking")
    if cfg.tracking.target_fps <= 0:
        raise ConfigError("tracking.target_fps must be positive")
    if cfg.tracking.user_height <= 0:
        raise ConfigError("tracking.user_height must be positive")

    outputs = data.get("output", {})
    _apply(cfg.vmt, outputs.get("vmt", {}), "output.vmt")
    _apply(cfg.vrchat, outputs.get("vrchat", {}), "output.vrchat")
    _apply(cfg.vrcft, outputs.get("vrcft", {}), "output.vrcft")
    _apply(cfg.udp_json, outputs.get("udp_json", {}), "output.udp_json")
    for name, out in (
        ("vmt", cfg.vmt),
        ("vrchat", cfg.vrchat),
        ("vrcft", cfg.vrcft),
        ("udp_json", cfg.udp_json),
    ):
        if not 0 < out.port < 65536:
            raise ConfigError(f"output.{name}.port out of range: {out.port}")

    _apply(cfg.models, data.get("models", {}), "models")
    _apply(cfg.debug, data.get("debug", {}), "debug")
    if not 0 < cfg.debug.http_port < 65536:
        raise ConfigError(f"debug.http_port out of range: {cfg.debug.http_port}")
    for i, cam in enumerate(cfg.cameras):
        if not isinstance(cam.device, int | str):
            raise ConfigError(f"camera[{i}].device must be an index or URL string")
    return cfg

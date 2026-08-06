"""CLI entry point: ``python -m easyfbt`` / ``easyfbt``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from easyfbt import __version__
from easyfbt.config import Config, load_config


def build_pipeline(config: Config):
    """Wire real cameras, backends and outputs from the config."""
    from easyfbt.app import CameraUnit, Pipeline
    from easyfbt.backends.mediapipe_backend import MediaPipeFaceBackend, MediaPipePoseBackend
    from easyfbt.capture import CameraSource

    cameras = []
    for cam_cfg in config.cameras:
        cameras.append(
            CameraUnit(
                source=CameraSource(cam_cfg),
                yaw_deg=cam_cfg.yaw_deg,
                pose_backend=(
                    MediaPipePoseBackend(config.models.pose_model) if cam_cfg.pose else None
                ),
                face_backend=(
                    MediaPipeFaceBackend(config.models.face_model) if cam_cfg.face else None
                ),
            )
        )

    outputs = []
    if config.vmt.enabled:
        from easyfbt.outputs.vmt import VmtOutput

        outputs.append(VmtOutput(config.vmt.host, config.vmt.port))
    if config.vrchat.enabled:
        from easyfbt.outputs.vrchat import VrchatTrackerOutput

        outputs.append(VrchatTrackerOutput(config.vrchat.host, config.vrchat.port))
    if config.vrcft.enabled:
        from easyfbt.outputs.vrcft import VrcftOutput

        outputs.append(
            VrcftOutput(
                config.vrcft.host,
                config.vrcft.port,
                config.vrcft.address_prefix,
                config.vrcft.send_eyes,
            )
        )
    if config.udp_json.enabled:
        from easyfbt.outputs.udp_json import UdpJsonOutput

        outputs.append(UdpJsonOutput(config.udp_json.host, config.udp_json.port))

    return Pipeline(config, cameras, outputs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="easyfbt",
        description="Webcam full-body + face tracking for SteamVR/VRChat/VRCFT.",
    )
    parser.add_argument("--version", action="version", version=f"easyfbt {__version__}")
    parser.add_argument(
        "-c", "--config", default="config.toml", help="path to TOML config (default: config.toml)"
    )
    parser.add_argument("--no-window", action="store_true", help="disable the debug window")
    parser.add_argument("--list-cameras", action="store_true", help="probe camera devices and exit")
    args = parser.parse_args(argv)

    if args.list_cameras:
        from easyfbt.capture import list_cameras

        for idx in list_cameras():
            print(f"camera device {idx}")
        return 0

    if not Path(args.config).is_file():
        print(
            f"config not found: {args.config}\n"
            "Copy config.example.toml to config.toml and adjust it.",
            file=sys.stderr,
        )
        return 2
    config = load_config(args.config)

    pipeline = build_pipeline(config)
    views = []
    if config.debug.window and not args.no_window:
        from easyfbt.debugview import DebugView

        views.append(DebugView())
    if config.debug.http_enabled:
        from easyfbt.debugview import HttpDebugView

        http_view = HttpDebugView(config.debug.http_host, config.debug.http_port)
        print(f"debug view: http://{config.debug.http_host}:{http_view.server.port}/")
        views.append(http_view)
    view = None
    if views:
        from easyfbt.debugview import MultiView

        view = views[0] if len(views) == 1 else MultiView(views)
    pipeline.run(view=view)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

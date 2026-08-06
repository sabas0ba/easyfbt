"""Runtime configuration controller behind the settings UI.

Receives a full config dict (same shape as the TOML file / ``GET /config``),
validates it with the normal config parser, hot-applies everything that can
change live and reports the rest as "restart required":

* hot: output sinks (enable/host/port/...), camera position & yaw, tracking
  parameters, ``debug.show_video``
* restart: camera device/resolution/fps/pose/face flags, number of cameras,
  model paths, ``debug.window`` and the HTTP server binding

Saving persists the *desired* config (including restart-required fields) to
the TOML file, so the next launch picks them up.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from easyfbt.config import Config, ConfigError, parse_config
from easyfbt.config_io import config_to_dict, save_config


class Controller:
    def __init__(
        self,
        config: Config,
        config_path: str | Path,
        pipeline=None,
        outputs_builder: Callable[[Config], list] | None = None,
    ):
        self._lock = threading.Lock()
        self.config = config
        self.config_path = Path(config_path)
        self._pipeline = pipeline
        self._outputs_builder = outputs_builder

    @property
    def show_video(self) -> bool:
        return self.config.debug.show_video

    def get_config(self) -> dict:
        with self._lock:
            return config_to_dict(self.config)

    def set_config(self, data: dict, save: bool = False) -> dict:
        """Validate, hot-apply, optionally persist. Returns a result dict."""
        try:
            new = parse_config(data)
        except (ConfigError, TypeError, ValueError) as exc:
            return {"ok": False, "message": str(exc), "restart_required": []}

        with self._lock:
            restart = self._restart_required(self.config, new)
            self._hot_apply(self.config, new)
            self.config = new
            if save:
                save_config(new, self.config_path)

        message = "適用しました" + (f"(保存: {self.config_path.name})" if save else "")
        if restart:
            message += " ※次の項目は再起動後に反映: " + ", ".join(restart)
        return {"ok": True, "message": message, "restart_required": restart}

    @staticmethod
    def _restart_required(old: Config, new: Config) -> list[str]:
        restart = []
        if len(old.cameras) != len(new.cameras):
            restart.append("camera (台数)")
        else:
            for i, (a, b) in enumerate(zip(old.cameras, new.cameras, strict=True)):
                for key in ("device", "width", "height", "fps", "pose", "face"):
                    if getattr(a, key) != getattr(b, key):
                        restart.append(f"camera[{i}].{key}")
        for key in ("pose_model", "face_model"):
            if getattr(old.models, key) != getattr(new.models, key):
                restart.append(f"models.{key}")
        if old.debug.window != new.debug.window:
            restart.append("debug.window")
        for key in ("http_enabled", "http_host", "http_port"):
            if getattr(old.debug, key) != getattr(new.debug, key):
                restart.append(f"debug.{key}")
        return restart

    def _hot_apply(self, old: Config, new: Config) -> None:
        if self._pipeline is not None:
            self._pipeline.apply_tracking_config(new.tracking)
            for i, cam in enumerate(new.cameras[: len(old.cameras)]):
                self._pipeline.set_camera_pose(i, cam.yaw_deg)
        outputs_changed = (
            old.vmt != new.vmt
            or old.vrchat != new.vrchat
            or old.vrcft != new.vrcft
            or old.udp_json != new.udp_json
        )
        if outputs_changed and self._pipeline is not None and self._outputs_builder is not None:
            self._pipeline.swap_outputs(self._outputs_builder(new))

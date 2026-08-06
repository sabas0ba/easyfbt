"""Face tracking output in the VRCFT (VRCFaceTracking) manner.

VRCFT drives avatars by writing Unified Expressions parameters over OSC.
This output emits the same shape names as floats:

* default: ``/avatar/parameters/v2/<Shape>`` to VRChat (port 9000), which
  drives avatars set up with plain float UE parameters directly;
* alternatively point ``address_prefix``/``port`` at a custom receiver (e.g. a
  VRCFT tracking module) to let VRCFT handle parameter packing itself.

Optionally the native VRChat eye endpoint ``/tracking/eye/CenterPitchYaw``
(degrees; pitch positive = looking down) is fed from the estimated gaze.

Note: binary-packed parameters and per-avatar parameter negotiation (which
VRCFT performs against the avatar's OSC config) are out of scope here.
"""

from __future__ import annotations

import math

from easyfbt import osc
from easyfbt.outputs.base import UdpSender
from easyfbt.types import TrackingFrame


class VrcftOutput:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        address_prefix: str = "/avatar/parameters/v2/",
        send_eyes: bool = True,
    ):
        if not address_prefix.startswith("/"):
            raise ValueError("address_prefix must start with '/'")
        self._sender = UdpSender(host, port)
        self._prefix = address_prefix if address_prefix.endswith("/") else address_prefix + "/"
        self._send_eyes = send_eyes

    def send(self, frame: TrackingFrame) -> None:
        if not frame.expressions:
            return
        for name, value in frame.expressions.items():
            self._sender.send(osc.encode_message(self._prefix + name, [float(value)]))
        if self._send_eyes and frame.face is not None:
            pitch_deg = -math.degrees(frame.face.eye_pitch)  # VRChat: positive looks down
            yaw_deg = -math.degrees(frame.face.eye_yaw)  # VRChat: positive looks right
            self._sender.send(
                osc.encode_message("/tracking/eye/CenterPitchYaw", [pitch_deg, yaw_deg])
            )

    def close(self) -> None:
        self._sender.close()

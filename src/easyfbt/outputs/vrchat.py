"""VRChat OSC tracker output (no SteamVR needed).

VRChat natively accepts up to 8 OSC trackers on port 9000:

* ``/tracking/trackers/{1..8}/position``  (x y z, Unity metres)
* ``/tracking/trackers/{1..8}/rotation``  (Unity euler angles, degrees)

The in-game "OSC Trackers" calibration aligns this space with the avatar, so
the fixed hip anchor used by easyfbt works out of the box.
"""

from __future__ import annotations

from easyfbt import osc, quat
from easyfbt.outputs.base import UdpSender
from easyfbt.types import TrackingFrame


class VrchatTrackerOutput:
    def __init__(self, host: str = "127.0.0.1", port: int = 9000):
        self._sender = UdpSender(host, port)

    def send(self, frame: TrackingFrame) -> None:
        for tracker in frame.trackers:
            pos, rot = quat.to_unity(tracker.position, tracker.rotation)
            euler = quat.unity_euler_deg(rot)
            base = f"/tracking/trackers/{tracker.index}"
            self._sender.send(
                osc.encode_message(
                    f"{base}/position", [float(pos[0]), float(pos[1]), float(pos[2])]
                )
            )
            self._sender.send(
                osc.encode_message(
                    f"{base}/rotation", [float(euler[0]), float(euler[1]), float(euler[2])]
                )
            )

    def close(self) -> None:
        self._sender.close()

"""SteamVR output via the VMT (Virtual Motion Tracker) OpenVR driver.

VMT (https://github.com/gpsnmeajp/VirtualMotionTracker) is an existing,
widely-used OpenVR driver that creates virtual trackers from OSC input, which
lets us feed SteamVR without shipping a native C++ driver of our own.

Protocol: ``/VMT/Room/Unity  index(i) enable(i) timeoffset(f) x y z qx qy qz
qw`` on UDP port 39570; coordinates are Unity convention (left-handed, Y-up),
room space (VMT applies its own room calibration on top).
"""

from __future__ import annotations

from easyfbt import osc, quat
from easyfbt.outputs.base import UdpSender
from easyfbt.types import TrackingFrame

TRACKER_ENABLED = 1


class VmtOutput:
    def __init__(self, host: str = "127.0.0.1", port: int = 39570):
        self._sender = UdpSender(host, port)

    def send(self, frame: TrackingFrame) -> None:
        for tracker in frame.trackers:
            pos, rot = quat.to_unity(tracker.position, tracker.rotation)
            msg = osc.encode_message(
                "/VMT/Room/Unity",
                [
                    tracker.index,
                    TRACKER_ENABLED,
                    0.0,  # time offset (seconds)
                    float(pos[0]),
                    float(pos[1]),
                    float(pos[2]),
                    float(rot[0]),
                    float(rot[1]),
                    float(rot[2]),
                    float(rot[3]),
                ],
            )
            self._sender.send(msg)

    def close(self) -> None:
        self._sender.close()

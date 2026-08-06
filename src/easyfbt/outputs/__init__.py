"""Output sinks: SteamVR (VMT), VRChat OSC trackers, VRCFT-style face OSC,
and a generic UDP JSON data interface."""

from easyfbt.outputs.base import Output, UdpSender
from easyfbt.outputs.udp_json import UdpJsonOutput
from easyfbt.outputs.vmt import VmtOutput
from easyfbt.outputs.vrcft import VrcftOutput
from easyfbt.outputs.vrchat import VrchatTrackerOutput

__all__ = [
    "Output",
    "UdpJsonOutput",
    "UdpSender",
    "VmtOutput",
    "VrcftOutput",
    "VrchatTrackerOutput",
]

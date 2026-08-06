"""Generic data interface: one JSON document per UDP datagram.

Meant for external consumers (visualisers, loggers, custom bridges).  Schema:

.. code-block:: json

    {
      "v": 1,
      "t": 1712345678.9,
      "fps": 29.7,
      "trackers": [
        {"role": "hip", "index": 1,
         "pos": [0.0, 0.9, 0.0], "rot": [0.0, 0.0, 0.0, 1.0]}
      ],
      "expressions": {"JawOpen": 0.12},
      "eyes": {"pitch": 0.0, "yaw": 0.0}
    }

Positions are room space (right-handed, Y-up, metres); ``rot`` is a
quaternion ``[x, y, z, w]``.
"""

from __future__ import annotations

import json

from easyfbt.outputs.base import UdpSender
from easyfbt.types import TrackingFrame

SCHEMA_VERSION = 1


def frame_to_dict(frame: TrackingFrame) -> dict:
    doc: dict = {
        "v": SCHEMA_VERSION,
        "t": frame.timestamp,
        "fps": round(frame.fps, 2),
        "trackers": [
            {
                "role": t.role.value,
                "index": t.index,
                "pos": [round(float(x), 5) for x in t.position],
                "rot": [round(float(x), 5) for x in t.rotation],
            }
            for t in frame.trackers
        ],
        "expressions": {k: round(float(v), 4) for k, v in frame.expressions.items()},
    }
    if frame.face is not None:
        doc["eyes"] = {
            "pitch": round(float(frame.face.eye_pitch), 4),
            "yaw": round(float(frame.face.eye_yaw), 4),
        }
    return doc


class UdpJsonOutput:
    def __init__(self, host: str = "127.0.0.1", port: int = 9199):
        self._sender = UdpSender(host, port)

    def send(self, frame: TrackingFrame) -> None:
        self._sender.send(json.dumps(frame_to_dict(frame), separators=(",", ":")).encode("utf-8"))

    def close(self) -> None:
        self._sender.close()

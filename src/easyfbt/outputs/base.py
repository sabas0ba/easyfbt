"""Output protocol and shared UDP plumbing."""

from __future__ import annotations

import socket
from typing import Protocol

from easyfbt.types import TrackingFrame


class UdpSender:
    """Small connectionless UDP sender (stdlib only)."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, data: bytes) -> None:
        try:
            self._sock.sendto(data, (self.host, self.port))
        except OSError:
            # A missing receiver must never take down the tracking loop.
            pass

    def close(self) -> None:
        self._sock.close()


class Output(Protocol):
    """One sink for tracking frames."""

    def send(self, frame: TrackingFrame) -> None: ...

    def close(self) -> None: ...

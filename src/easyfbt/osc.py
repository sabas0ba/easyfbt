"""Minimal OSC 1.0 message/bundle encoder (and decoder for tests).

Implemented in-house on top of :mod:`struct` to avoid a third-party
dependency; the subset covers everything VMT, VRChat and VRCFT-style
receivers need (``i``, ``f``, ``s``, ``b``, ``T``, ``F``, ``d``).
"""

from __future__ import annotations

import struct

_IMMEDIATELY = b"\x00\x00\x00\x00\x00\x00\x00\x01"


def _pad(data: bytes) -> bytes:
    """Pad to a 4-byte boundary with NULs (strings always get >=1 NUL)."""
    return data + b"\x00" * (-len(data) % 4)


def _encode_string(value: str) -> bytes:
    return _pad(value.encode("utf-8") + b"\x00")


def encode_message(address: str, args: list) -> bytes:
    """Encode a single OSC message.

    Python types map to OSC types: ``bool``→T/F, ``int``→i, ``float``→f,
    ``str``→s, ``bytes``→b.  Use :class:`Double` to force a 64-bit float.
    """
    if not address.startswith("/"):
        raise ValueError(f"OSC address must start with '/': {address!r}")
    tags = ","
    payload = b""
    for arg in args:
        if isinstance(arg, bool):  # must precede int check
            tags += "T" if arg else "F"
        elif isinstance(arg, int):
            tags += "i"
            payload += struct.pack(">i", arg)
        elif isinstance(arg, Double):
            tags += "d"
            payload += struct.pack(">d", arg.value)
        elif isinstance(arg, float):
            tags += "f"
            payload += struct.pack(">f", arg)
        elif isinstance(arg, str):
            tags += "s"
            payload += _encode_string(arg)
        elif isinstance(arg, bytes):
            tags += "b"
            payload += struct.pack(">i", len(arg)) + _pad(arg)
        else:
            raise TypeError(f"unsupported OSC argument type: {type(arg)!r}")
    return _encode_string(address) + _encode_string(tags) + payload


def encode_bundle(messages: list[bytes], timetag: bytes = _IMMEDIATELY) -> bytes:
    """Encode encoded messages into an OSC bundle with the given timetag."""
    out = _encode_string("#bundle") + timetag
    for msg in messages:
        out += struct.pack(">i", len(msg)) + msg
    return out


class Double:
    """Wrapper to send a float as OSC type ``d`` (64-bit)."""

    __slots__ = ("value",)

    def __init__(self, value: float):
        self.value = float(value)


def decode_message(data: bytes) -> tuple[str, list]:
    """Decode a single OSC message (used by tests and the debug tooling)."""
    address, rest = _read_string(data)
    tags, rest = _read_string(rest)
    if not tags.startswith(","):
        raise ValueError("missing OSC type tag string")
    args: list = []
    for tag in tags[1:]:
        if tag == "i":
            args.append(struct.unpack(">i", rest[:4])[0])
            rest = rest[4:]
        elif tag == "f":
            args.append(struct.unpack(">f", rest[:4])[0])
            rest = rest[4:]
        elif tag == "d":
            args.append(struct.unpack(">d", rest[:8])[0])
            rest = rest[8:]
        elif tag == "s":
            s, rest = _read_string(rest)
            args.append(s)
        elif tag == "b":
            n = struct.unpack(">i", rest[:4])[0]
            args.append(rest[4 : 4 + n])
            rest = rest[4 + (-(-n // 4) * 4) :]
        elif tag == "T":
            args.append(True)
        elif tag == "F":
            args.append(False)
        else:
            raise ValueError(f"unsupported OSC type tag: {tag!r}")
    return address, args


def _read_string(data: bytes) -> tuple[str, bytes]:
    end = data.index(b"\x00")
    consumed = (end + 4) // 4 * 4
    return data[:end].decode("utf-8"), data[consumed:]

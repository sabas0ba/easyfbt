import struct

import pytest

from easyfbt import osc


def test_message_golden_bytes():
    # Known-good encoding: address + type tags + one float, all 4-byte padded.
    data = osc.encode_message("/a", [1.5])
    assert data == b"/a\x00\x00,f\x00\x00" + struct.pack(">f", 1.5)


def test_address_padding_multiple_of_four():
    for address in ("/a", "/ab", "/abc", "/abcd"):
        data = osc.encode_message(address, [])
        assert len(data) % 4 == 0
        assert data.startswith(address.encode())


def test_int_float_string_roundtrip():
    addr, args = osc.decode_message(
        osc.encode_message("/test/msg", [3, -1, 2.25, "hello", True, False])
    )
    assert addr == "/test/msg"
    assert args == [3, -1, 2.25, "hello", True, False]


def test_double_argument():
    _addr, args = osc.decode_message(osc.encode_message("/d", [osc.Double(1.1)]))
    assert args == [pytest.approx(1.1)]


def test_blob_argument():
    _addr, args = osc.decode_message(osc.encode_message("/b", [b"\x01\x02\x03"]))
    assert args == [b"\x01\x02\x03"]


def test_vmt_style_message():
    data = osc.encode_message("/VMT/Room/Unity", [1, 1, 0.0, 0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0])
    addr, args = osc.decode_message(data)
    assert addr == "/VMT/Room/Unity"
    assert args[0] == 1 and args[1] == 1
    assert args[3] == pytest.approx(0.1)
    assert args[9] == pytest.approx(1.0)


def test_bundle_contains_messages():
    m1 = osc.encode_message("/x", [1])
    m2 = osc.encode_message("/y", [2.0])
    bundle = osc.encode_bundle([m1, m2])
    assert bundle.startswith(b"#bundle\x00")
    assert m1 in bundle and m2 in bundle


def test_rejects_bad_address():
    with pytest.raises(ValueError):
        osc.encode_message("no-slash", [])


def test_rejects_unknown_type():
    with pytest.raises(TypeError):
        osc.encode_message("/x", [object()])

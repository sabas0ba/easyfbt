"""DebugHttpServer is stdlib-only, so it is tested with real HTTP clients."""

import http.client
import json
import threading

import pytest

from easyfbt.debug_http import DebugHttpServer

FAKE_JPEG = b"\xff\xd8\xfa\xceJPEGDATA\xff\xd9"


@pytest.fixture
def server():
    srv = DebugHttpServer("127.0.0.1", 0)  # port 0: let the OS pick
    yield srv
    srv.close()


def get(srv, path, timeout=3.0):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()
    finally:
        conn.close()


def test_index_page(server):
    status, headers, body = get(server, "/")
    assert status == 200
    assert "text/html" in headers["Content-Type"]
    assert b"/stream" in body


def test_frame_before_first_update_is_503(server):
    status, _, _ = get(server, "/frame")
    assert status == 503


def test_frame_returns_latest_jpeg(server):
    server.update(FAKE_JPEG, {"fps": 30.0})
    status, headers, body = get(server, "/frame")
    assert status == 200
    assert headers["Content-Type"] == "image/jpeg"
    assert body == FAKE_JPEG


def test_state_returns_latest_json(server):
    server.update(FAKE_JPEG, {"v": 1, "expressions": {"JawOpen": 0.5}})
    status, headers, body = get(server, "/state")
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body) == {"v": 1, "expressions": {"JawOpen": 0.5}}


def test_unknown_path_404(server):
    status, _, _ = get(server, "/nope")
    assert status == 404


def test_stream_delivers_multipart_frames(server):
    server.update(FAKE_JPEG, {})
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5.0)
    try:
        conn.request("GET", "/stream")
        resp = conn.getresponse()
        assert resp.status == 200
        assert "multipart/x-mixed-replace" in resp.getheader("Content-Type")

        # Push a second frame from another thread so the stream has content.
        second = FAKE_JPEG + b"2"
        threading.Timer(0.05, server.update, args=(second, {})).start()

        chunk = b""
        while chunk.count(b"--easyfbtframe") < 2 and len(chunk) < 65536:
            data = resp.fp.read1(4096)
            if not data:
                break
            chunk += data
        assert b"--easyfbtframe" in chunk
        assert b"Content-Type: image/jpeg" in chunk
        assert FAKE_JPEG in chunk
    finally:
        conn.close()


def test_update_is_visible_across_threads(server):
    results = []

    def reader():
        results.append(server.wait_frame(seen_seq=-1, timeout=3.0))

    t = threading.Thread(target=reader)
    t.start()
    server.update(FAKE_JPEG, {})
    t.join(timeout=5.0)
    assert results and results[0] is not None
    jpeg, seq = results[0]
    assert jpeg == FAKE_JPEG
    assert seq >= 1


def test_close_unblocks_waiters(server):
    done = threading.Event()

    def waiter():
        server.wait_frame(seen_seq=-1, timeout=10.0)
        done.set()

    t = threading.Thread(target=waiter)
    t.start()
    server.close()
    assert done.wait(timeout=5.0)

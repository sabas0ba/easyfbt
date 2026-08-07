"""DebugHttpServer is stdlib-only, so it is tested with real HTTP clients."""

import http.client
import json
import threading

import pytest

from easyfbt.config import parse_config
from easyfbt.control import Controller
from easyfbt.debug_http import DebugHttpServer

FAKE_JPEG = b"\xff\xd8\xfa\xceJPEGDATA\xff\xd9"


@pytest.fixture
def server():
    srv = DebugHttpServer("127.0.0.1", 0)  # port 0: let the OS pick
    yield srv
    srv.close()


@pytest.fixture
def control_server(tmp_path):
    controller = Controller(parse_config({}), tmp_path / "config.toml")
    srv = DebugHttpServer("127.0.0.1", 0, controller=controller)
    yield srv, controller
    srv.close()


def get(srv, path, timeout=3.0):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()
    finally:
        conn.close()


def post(srv, path, body: bytes, timeout=3.0):
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=timeout)
    try:
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        return resp.status, resp.read()
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


def test_config_endpoint_404_without_controller(server):
    status, _, _ = get(server, "/config")
    assert status == 404


def test_config_get_returns_full_config(control_server):
    srv, controller = control_server
    status, _headers, body = get(srv, "/config")
    assert status == 200
    doc = json.loads(body)
    assert doc == controller.get_config()
    assert doc["output"]["vrchat"]["port"] == 9000


def test_config_post_applies(control_server):
    srv, controller = control_server
    cfg = controller.get_config()
    cfg["output"]["vrchat"]["enabled"] = False
    cfg["debug"]["show_video"] = False
    status, body = post(srv, "/config", json.dumps(cfg).encode())
    assert status == 200
    result = json.loads(body)
    assert result["ok"] is True
    assert controller.config.vrchat.enabled is False
    assert controller.show_video is False
    assert not controller.config_path.exists()  # no save requested


def test_config_post_with_save_writes_file(control_server):
    srv, controller = control_server
    cfg = controller.get_config()
    cfg["output"]["vmt"]["enabled"] = True
    status, _body = post(srv, "/config?save=1", json.dumps(cfg).encode())
    assert status == 200
    assert controller.config_path.is_file()
    assert "enabled = true" in controller.config_path.read_text().split("[output.vmt]")[1]


def test_config_post_invalid_returns_400(control_server):
    srv, controller = control_server
    cfg = controller.get_config()
    cfg["output"]["vrchat"]["port"] = 99999
    status, body = post(srv, "/config", json.dumps(cfg).encode())
    assert status == 400
    assert json.loads(body)["ok"] is False
    assert controller.config.vrchat.port == 9000  # unchanged


def test_config_post_bad_json_returns_400(control_server):
    srv, _ = control_server
    status, _ = post(srv, "/config", b"{nope")
    assert status == 400


def test_post_unknown_path_404(control_server):
    srv, _ = control_server
    status, _ = post(srv, "/elsewhere", b"{}")
    assert status == 404


def test_index_serves_control_panel(control_server):
    srv, _ = control_server
    status, headers, body = get(srv, "/")
    assert status == 200
    assert "text/html" in headers["Content-Type"]
    for marker in (b"/stream", b"/config", b"topView", b"isoView"):
        assert marker in body


def test_close_unblocks_waiters(server):
    done = threading.Event()

    def waiter():
        server.wait_frame(seen_seq=-1, timeout=10.0)
        done.set()

    t = threading.Thread(target=waiter)
    t.start()
    server.close()
    assert done.wait(timeout=5.0)

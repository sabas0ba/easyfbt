"""Browser-based debug view: an MJPEG/JSON HTTP server (stdlib only).

Inside a container there is no display for the OpenCV window, so this serves
the same annotated preview over HTTP instead:

* ``/``        -- tiny HTML page embedding the stream
* ``/stream``  -- ``multipart/x-mixed-replace`` MJPEG stream
* ``/frame``   -- latest annotated frame as a single JPEG
* ``/state``   -- latest tracking frame as JSON (same schema as udp_json)

The server only *reads* pipeline state pushed via :meth:`DebugHttpServer.update`;
it never controls tracking, so a slow or hostile client cannot stall the loop.
Bind it to 127.0.0.1 (or a published container port) -- it is a debug tool,
not an authenticated API.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_INDEX_HTML = b"""<!doctype html>
<html><head><title>easyfbt debug</title>
<style>body{background:#111;color:#eee;font-family:sans-serif;text-align:center}
img{max-width:96vw;max-height:80vh}</style></head>
<body><h3>easyfbt debug</h3><img src="/stream" alt="debug stream">
<p><a href="/state" style="color:#8cf">/state</a>
<a href="/frame" style="color:#8cf">/frame</a></p></body></html>
"""

_BOUNDARY = b"easyfbtframe"


class DebugHttpServer:
    """Threaded HTTP server publishing the latest debug frame and state."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8089):
        self._cond = threading.Condition()
        self._jpeg: bytes | None = None
        self._state: dict = {}
        self._seq = 0
        self._closed = False

        publisher = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):  # quiet: tracking loop owns stdout
                pass

            def do_GET(self):
                if self.path == "/":
                    self._send(200, "text/html; charset=utf-8", _INDEX_HTML)
                elif self.path == "/frame":
                    jpeg = publisher.latest_jpeg()
                    if jpeg is None:
                        self._send(503, "text/plain", b"no frame yet\n")
                    else:
                        self._send(200, "image/jpeg", jpeg)
                elif self.path == "/state":
                    body = json.dumps(publisher.latest_state()).encode()
                    self._send(200, "application/json", body)
                elif self.path == "/stream":
                    self._stream()
                else:
                    self._send(404, "text/plain", b"not found\n")

            def _send(self, code: int, ctype: str, body: bytes):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _stream(self):
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    f"multipart/x-mixed-replace; boundary={_BOUNDARY.decode()}",
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seq = -1
                try:
                    while True:
                        frame = publisher.wait_frame(seq, timeout=2.0)
                        if frame is None:
                            if publisher.closed:
                                return
                            continue  # timeout: keep waiting
                        jpeg, seq = frame
                        self.wfile.write(
                            b"--" + _BOUNDARY + b"\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                        )
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                except (BrokenPipeError, ConnectionResetError):
                    return

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="debug-http", daemon=True
        )
        self._thread.start()

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def closed(self) -> bool:
        return self._closed

    def update(self, jpeg: bytes, state: dict) -> None:
        with self._cond:
            self._jpeg = jpeg
            self._state = state
            self._seq += 1
            self._cond.notify_all()

    def latest_jpeg(self) -> bytes | None:
        with self._cond:
            return self._jpeg

    def latest_state(self) -> dict:
        with self._cond:
            return self._state

    def wait_frame(self, seen_seq: int, timeout: float) -> tuple[bytes, int] | None:
        """Block until a frame newer than ``seen_seq`` exists (or timeout)."""
        with self._cond:
            if self._seq == seen_seq or self._jpeg is None:
                self._cond.wait(timeout)
            if self._seq == seen_seq or self._jpeg is None:
                return None
            return self._jpeg, self._seq

    def close(self) -> None:
        self._closed = True
        with self._cond:
            self._cond.notify_all()
        self._httpd.shutdown()
        self._httpd.server_close()

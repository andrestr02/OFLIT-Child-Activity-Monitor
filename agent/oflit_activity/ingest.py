"""Loopback-only HTTP ingestion endpoint for browser-extension events.

Hard constraints, enforced here regardless of what the extension sends:

* binds to a loopback address only (config default 127.0.0.1) — never 0.0.0.0;
* rejects anything but ``POST /event``;
* caps the request body (``max_payload_bytes``) before reading it;
* parses JSON defensively and hands the payload to a supplied ``ingest_fn``
  which performs validation, sensitive-field rejection, and authoritative
  user attribution.

The server never trusts the client. It returns terse JSON and minimal
information, and it never blocks the browser for long (short socket timeouts).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_handler(ingest_fn, config, logger=None):
    max_bytes = config.max_payload_bytes
    expected_token = config.ingest_token

    class Handler(BaseHTTPRequestHandler):
        server_version = "OFLITActivity/0.1"

        # Silence default stderr logging; route through our logger.
        def log_message(self, fmt, *args):  # noqa: A003
            if logger:
                logger("ingest: " + (fmt % args))

        def _reply(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            # This endpoint is for the managed extension only; do not invite
            # cross-origin browser callers.
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):  # noqa: N802
            if self.path == "/healthz":
                return self._reply(200, {"status": "ok"})
            return self._reply(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if self.path != "/event":
                return self._reply(404, {"error": "not found"})

            # Optional cheap marker (NOT a security boundary; see SECURITY.md).
            if expected_token:
                got = self.headers.get("X-OFLIT-Token", "")
                if got != expected_token:
                    return self._reply(403, {"error": "forbidden"})

            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._reply(411, {"error": "length required"})
            if length <= 0:
                return self._reply(400, {"error": "empty body"})
            if length > max_bytes:
                return self._reply(413, {"error": "payload too large"})

            raw = self.rfile.read(length)
            if len(raw) != length:
                return self._reply(400, {"error": "short read"})

            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._reply(400, {"error": "invalid json"})

            try:
                accepted, reason = ingest_fn(payload)
            except Exception as exc:  # noqa: BLE001 - never crash the listener
                if logger:
                    logger(f"ingest handler error: {exc}")
                return self._reply(500, {"error": "internal"})

            if accepted:
                return self._reply(202, {"status": "accepted"})
            return self._reply(422, {"status": "rejected", "reason": reason})

    return Handler


class IngestServer:
    def __init__(self, ingest_fn, config, logger=None):
        host = config.listen_host
        # Defence in depth: refuse to bind anything non-loopback.
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise ValueError(f"refusing non-loopback listen host: {host!r}")
        handler = make_handler(ingest_fn, config, logger)
        self.httpd = ThreadingHTTPServer((host, config.listen_port), handler)
        self.httpd.timeout = 5
        self._thread = None

    @property
    def port(self):
        return self.httpd.server_address[1]

    def start(self):
        self._thread = threading.Thread(
            target=self.httpd.serve_forever, name="oflit-ingest", daemon=True
        )
        self._thread.start()

    def stop(self):
        try:
            self.httpd.shutdown()
        except Exception:  # noqa: BLE001
            pass
        self.httpd.server_close()

import json
import unittest
import urllib.error
import urllib.request

import _support  # noqa: F401
from oflit_activity.config import Config
from oflit_activity.ingest import IngestServer


class TestIngestServer(unittest.TestCase):
    def setUp(self):
        self.received = []

        def ingest_fn(payload):
            self.received.append(payload)
            if payload.get("event_type") == "bad":
                return False, "rejected reason"
            return True, "accepted"

        # port 0 -> ephemeral free port
        self.cfg = Config(listen_host="127.0.0.1", listen_port=0,
                          max_payload_bytes=1024, ingest_token="")
        self.server = IngestServer(ingest_fn, self.cfg)
        self.server.start()
        self.base = f"http://127.0.0.1:{self.server.port}"

    def tearDown(self):
        self.server.stop()

    def _post(self, path, data, headers=None):
        req = urllib.request.Request(
            self.base + path, data=data, method="POST",
            headers=headers or {"Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=5)

    def test_refuses_non_loopback_bind(self):
        with self.assertRaises(ValueError):
            IngestServer(lambda p: (True, ""),
                         Config(listen_host="0.0.0.0", listen_port=0))

    def test_healthz(self):
        resp = urllib.request.urlopen(self.base + "/healthz", timeout=5)
        self.assertEqual(resp.status, 200)

    def test_valid_event_accepted(self):
        body = json.dumps({"event_type": "submitted_search"}).encode()
        resp = self._post("/event", body)
        self.assertEqual(resp.status, 202)
        self.assertEqual(len(self.received), 1)

    def test_rejected_event_returns_422(self):
        body = json.dumps({"event_type": "bad"}).encode()
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/event", body)
        self.assertEqual(ctx.exception.code, 422)
        ctx.exception.close()

    def test_oversized_payload_rejected(self):
        body = b"x" * 5000
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/event", body)
        self.assertEqual(ctx.exception.code, 413)
        ctx.exception.close()
        self.assertEqual(len(self.received), 0)

    def test_bad_json_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/event", b"{not json")
        self.assertEqual(ctx.exception.code, 400)
        ctx.exception.close()

    def test_wrong_path_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/nope", b"{}")
        self.assertEqual(ctx.exception.code, 404)
        ctx.exception.close()


class TestIngestToken(unittest.TestCase):
    def test_token_enforced(self):
        cfg = Config(listen_host="127.0.0.1", listen_port=0, ingest_token="secret")
        server = IngestServer(lambda p: (True, ""), cfg)
        server.start()
        base = f"http://127.0.0.1:{server.port}"
        try:
            # no token -> 403
            req = urllib.request.Request(base + "/event", data=b"{}", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, 403)
            ctx.exception.close()
            # correct token -> 202
            req = urllib.request.Request(
                base + "/event", data=b"{}", method="POST",
                headers={"X-OFLIT-Token": "secret"})
            resp = urllib.request.urlopen(req, timeout=5)
            self.assertEqual(resp.status, 202)
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()

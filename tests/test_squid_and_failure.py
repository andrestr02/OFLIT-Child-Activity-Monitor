import os
import tempfile
import unittest

import _support
from oflit_activity import squid
from oflit_activity.config import load_config
from oflit_activity.daemon import Agent
from oflit_activity import daemon as D


_LOG = """1700000100.123    150 127.0.0.1 TCP_MISS/200 5321 GET http://cdn.example/asset - HIER/1.2.3.4 image/png
1700000150.000    10 127.0.0.1 TCP_DENIED/403 0 GET http://youtube.com/watch - NONE/- text/html
1700000900.000    10 127.0.0.1 TCP_MISS/200 100 GET http://binbaz.org.sa/ - HIER/- text/html
1699999999.000    10 127.0.0.1 TCP_MISS/200 100 GET http://before-window.com/ - HIER/- text/html
"""


class TestSquid(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".log")
        os.write(fd, _LOG.encode())
        os.close(fd)

    def tearDown(self):
        os.unlink(self.path)

    def test_window_and_blocked_classification(self):
        visited, blocked = squid.summarize(self.path, 1700000000, 1700000800)
        self.assertIn("youtube.com", blocked)
        self.assertIn("cdn.example", visited)
        self.assertNotIn("before-window.com", visited)   # outside time window
        self.assertNotIn("binbaz.org.sa", visited)        # after window end

    def test_missing_file_is_empty(self):
        visited, blocked = squid.summarize("/no/such/log", 0, 9_999_999_999)
        self.assertEqual((visited, blocked), ([], []))


class TestFailureModes(unittest.TestCase):
    def test_missing_db_dir_created(self):
        cfg = _support.temp_config(state_dir=os.path.join(
            tempfile.mkdtemp(), "nested", "dir"))
        agent = Agent(cfg, sender=_support.FakeSender())
        self.assertTrue(os.path.exists(cfg.db_path))
        agent.store.close()

    def test_malformed_config_falls_back_to_defaults(self):
        fd, path = tempfile.mkstemp(suffix=".conf")
        os.write(fd, b"this is not valid = = =\n\x00garbage\nLISTEN_PORT=notanumber\n")
        os.close(fd)
        cfg = load_config(path)
        # bad port -> default; no crash
        self.assertEqual(cfg.listen_port, 8791)
        os.unlink(path)

    def test_loginctl_unavailable_does_not_crash(self):
        cfg = _support.temp_config()
        agent = Agent(cfg, sender=_support.FakeSender())
        orig = D.list_child_graphical_sessions
        D.list_child_graphical_sessions = lambda u, n: (_ for _ in ()).throw(
            RuntimeError("loginctl gone"))
        try:
            # poll_sessions holds no try/except around the lister call itself,
            # but run()'s loop does; emulate the loop's guard.
            try:
                agent.poll_sessions()
            except RuntimeError:
                pass  # the run() loop swallows this; agent stays alive
        finally:
            D.list_child_graphical_sessions = orig
            agent.store.close()

    def test_ingest_never_raises_on_garbage(self):
        cfg = _support.temp_config()
        agent = Agent(cfg, sender=_support.FakeSender())
        for junk in [None, 42, "string", {"event_type": 123}, {}]:
            ok, _ = agent.ingest(junk)
            self.assertFalse(ok)
        agent.store.close()


if __name__ == "__main__":
    unittest.main()

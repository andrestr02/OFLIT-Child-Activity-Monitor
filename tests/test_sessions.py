import unittest

import _support  # noqa: F401
from oflit_activity import sessions as S


# Synthetic loginctl output modeled on the real oflitlab-i3 output.
_LIST = """ 1 1000 andrestr02 -     5512   manager -    no -
78 1000 andrestr02 -     615548 user    -    no -
88 1003 ibrohim    seat0 705186 user    tty2 no -
89 1003 ibrohim    -     705271 manager -    no -
"""

_SHOW = {
    "1": "Name=andrestr02\nClass=manager\nType=\nRemote=no\nActive=no\nTimestamp=Sun 2026-09-28 09:00:00 WIB\n",
    "78": "Name=andrestr02\nClass=user\nType=wayland\nRemote=no\nActive=yes\nTimestamp=Sun 2026-09-28 09:00:00 WIB\n",
    "88": "Name=ibrohim\nClass=user\nType=wayland\nRemote=no\nActive=yes\nTimestamp=Sun 2026-09-28 10:10:00 WIB\n",
    "89": "Name=ibrohim\nClass=manager\nType=\nRemote=no\nActive=no\nTimestamp=Sun 2026-09-28 10:10:00 WIB\n",
}


class TestSessionDetection(unittest.TestCase):
    def setUp(self):
        self._orig = S._run

        def fake_run(cmd, timeout=8):
            if cmd[:2] == ["loginctl", "list-sessions"]:
                return 0, _LIST, ""
            if cmd[:2] == ["loginctl", "show-session"]:
                return 0, _SHOW.get(cmd[2], ""), ""
            return 1, "", "?"

        S._run = fake_run

    def tearDown(self):
        S._run = self._orig

    def test_only_monitored_graphical_user_sessions(self):
        out = S.list_child_graphical_sessions(("ibrohim",), 1_700_000_000)
        # ibrohim's user/wayland session only (not the manager scope).
        self.assertEqual(len(out), 1)
        sess = next(iter(out.values()))
        self.assertEqual(sess.username, "ibrohim")
        self.assertEqual(sess.logind_id, "88")

    def test_non_monitored_user_ignored(self):
        # andrestr02 has a graphical session but is not monitored.
        out = S.list_child_graphical_sessions(("ibrohim",), 1_700_000_000)
        self.assertNotIn("andrestr02", [s.username for s in out.values()])

    def test_stable_session_id(self):
        out = S.list_child_graphical_sessions(("ibrohim",), 1_700_000_000)
        sid = next(iter(out))
        self.assertTrue(sid.startswith("ibrohim-88-"))

    def test_loginctl_failure_is_empty(self):
        S._run = lambda cmd, timeout=8: (1, "", "boom")
        out = S.list_child_graphical_sessions(("ibrohim",), 1_700_000_000)
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()

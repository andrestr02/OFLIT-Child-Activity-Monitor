import unittest

import _support
from oflit_activity.daemon import Agent
from oflit_activity import daemon as D


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.cfg = _support.temp_config()
        self.clock = _support.Clock()
        self.sender = _support.FakeSender()
        self.agent = Agent(self.cfg, sender=self.sender, clock=self.clock)
        self._orig = D.list_child_graphical_sessions
        self.state = {}
        D.list_child_graphical_sessions = lambda users, now: dict(self.state)

    def tearDown(self):
        D.list_child_graphical_sessions = self._orig
        self.agent.store.close()

    def _login(self, user="hudzaifah"):
        s = _support.session(user, "88", self.clock.t)
        self.state[s.session_id] = s
        self.agent.poll_sessions()
        return s

    def _logout(self):
        self.state.clear()
        self.agent.poll_sessions()

    def test_full_session_one_report(self):
        self._login()
        self.clock.advance(60)
        self.assertEqual(self.agent.ingest({
            "event_type": "submitted_search", "source": "browser_extension",
            "site": "google.com", "content": "pecahan", "submitted": True})[0], True)
        self.clock.advance(2000)
        self._logout()
        self.agent.tick_delivery()
        self.assertEqual(len(self.sender.sent), 1)
        self.assertIn("hudzaifah", self.sender.sent[0])

    def test_event_without_session_rejected(self):
        ok, reason = self.agent.ingest({
            "event_type": "submitted_search", "source": "browser_extension",
            "site": "google.com", "content": "x", "submitted": True})
        self.assertFalse(ok)
        self.assertEqual(reason, "no active child session")

    def test_forged_username_overridden(self):
        self._login("hudzaifah")
        self.clock.advance(10)
        self.agent.ingest({
            "event_type": "submitted_prompt", "source": "browser_extension",
            "site": "chatgpt.com", "content": "hi", "submitted": True,
            "username": "azzahra"})
        evs = self.agent.store.events_for_session(
            list(self.state)[0])
        prompts = [e for e in evs if e["event_type"] == "submitted_prompt"]
        self.assertEqual(prompts[0]["username"], "hudzaifah")

    def test_draft_never_stored(self):
        self._login()
        self.agent.ingest({
            "event_type": "submitted_prompt", "source": "browser_extension",
            "site": "chatgpt.com", "content": "unsent draft", "submitted": False})
        evs = self.agent.store.events_for_session(list(self.state)[0])
        self.assertFalse(any(e["content"] == "unsent draft" for e in evs))

    def test_idempotent_no_duplicate_report(self):
        self._login()
        self.clock.advance(100)
        self._logout()
        self.agent.poll_sessions()  # extra polls must not re-finalize
        self.agent.poll_sessions()
        self.agent.tick_delivery()
        self.assertEqual(len(self.sender.sent), 1)

    def test_chrome_close_is_not_session_end(self):
        # Chrome closing does not remove the logind session; no report yet.
        self._login()
        self.clock.advance(30)
        # session still present -> poll again, no logout report
        self.agent.poll_sessions()
        self.agent.tick_delivery()
        self.assertEqual(len(self.sender.sent), 0)

    def test_telegram_retry_then_success(self):
        self.sender = _support.FakeSender(fail_times=2)
        self.agent.sender = self.sender
        self._login()
        self.clock.advance(100)
        self._logout()
        self.agent.tick_delivery()   # fail 1
        self.assertEqual(len(self.sender.sent), 0)
        self.agent.tick_delivery()   # fail 2
        self.agent.tick_delivery()   # success
        self.assertEqual(len(self.sender.sent), 1)
        # no duplicate on further ticks
        self.agent.tick_delivery()
        self.assertEqual(len(self.sender.sent), 1)

    def test_pending_report_survives_restart(self):
        self._login()
        self.clock.advance(100)
        self._logout()
        # Telegram down: report stays pending in DB.
        self.agent.sender = _support.FakeSender(fail_times=99)
        self.agent.tick_delivery()
        self.agent.store.close()
        # New agent instance = simulated restart, same DB.
        agent2 = Agent(self.cfg, sender=_support.FakeSender(), clock=self.clock)
        agent2.tick_delivery()
        # report should now be delivered exactly once
        self.assertEqual(len(agent2.sender.sent), 1)
        agent2.store.close()

    def test_shutdown_with_active_session_produces_report(self):
        self._login()
        self.clock.advance(500)
        self.agent.finalize_all_open("shutdown")
        self.agent.tick_delivery()
        self.assertEqual(len(self.sender.sent), 1)
        self.assertIn("shutdown", self.sender.sent[0])


if __name__ == "__main__":
    unittest.main()

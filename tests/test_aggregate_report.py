import unittest

import _support  # noqa: F401
from oflit_activity.db import Store
from oflit_activity.aggregate import build_summary
from oflit_activity import report, model


class TestAggregateReport(unittest.TestCase):
    def setUp(self):
        self.cfg = _support.temp_config()
        self.store = Store(self.cfg.db_path)
        self.store.open_session("s1", "hudzaifah", "oflitlab-i3", 1_700_000_000)

    def tearDown(self):
        self.store.close()

    def _ev(self, etype, content, evidence, epoch, site="", trunc=0):
        row = {"schema_version": 1, "username": "hudzaifah", "device": "oflitlab-i3",
               "event_type": etype, "source": "browser_extension", "site": site,
               "evidence": evidence, "content": content, "content_truncated": trunc,
               "client_timestamp": ""}
        self.store.insert_event(row, "s1", epoch)

    def test_summary_and_report_wording(self):
        self._ev("submitted_search", "qowaidul fiqhiyyah",
                 model.EVIDENCE_DIRECT_USER_ACTION, 1_700_000_100, "google.com")
        self._ev("submitted_prompt", "Apa itu pecahan campuran?",
                 model.EVIDENCE_DIRECT_USER_ACTION, 1_700_000_200, "chatgpt.com")
        self._ev("navigation", "binbaz.org.sa",
                 model.EVIDENCE_VISITED_RESOURCE, 1_700_000_300)
        self._ev("app_started", "Google Chrome",
                 model.EVIDENCE_PROCESS_RUNNING, 1_700_000_050)
        self.store.close_session("s1", 1_700_002_700, "session ended")

        srow = self.store.get_session("s1")
        evs = self.store.events_for_session("s1")
        summary = build_summary(srow, evs, net=(["cdn.example"], ["youtube.com"]))
        text = report.render_telegram(summary, "Asia/Jakarta")

        self.assertIn("hudzaifah", text)
        self.assertIn('Google Search: "qowaidul fiqhiyyah"', text)
        self.assertIn("ChatGPT prompt submitted", text)
        self.assertIn("Apa itu pecahan campuran?", text)
        self.assertIn("visited: binbaz.org.sa", text)      # visited resource wording
        self.assertIn("Google Chrome", text)
        self.assertIn("blocked request observed: youtube.com", text)  # network wording
        self.assertIn("network observation: cdn.example", text)
        self.assertIn("Durasi", text)
        # honesty: never claims "membuka youtube"
        self.assertNotIn("membuka youtube", text.lower())

    def test_truncation_marker_in_report(self):
        self._ev("submitted_search", "a very long query cut off",
                 model.EVIDENCE_DIRECT_USER_ACTION, 1_700_000_100, "google.com", trunc=1)
        self.store.close_session("s1", 1_700_000_500, "ended")
        srow = self.store.get_session("s1")
        evs = self.store.events_for_session("s1")
        text = report.render_telegram(build_summary(srow, evs))
        self.assertIn("[…]", text)


if __name__ == "__main__":
    unittest.main()

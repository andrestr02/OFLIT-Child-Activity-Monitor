import os
import stat
import unittest

import _support  # noqa: F401
from oflit_activity.db import Store


class TestSchemaAndStore(unittest.TestCase):
    def setUp(self):
        self.cfg = _support.temp_config()
        self.store = Store(self.cfg.db_path)

    def tearDown(self):
        self.store.close()

    def test_schema_version_recorded(self):
        self.assertEqual(self.store._current_version(), 1)

    def test_migration_idempotent(self):
        self.store.migrate()
        self.store.migrate()
        self.assertEqual(self.store._current_version(), 1)

    def test_db_not_world_readable(self):
        mode = stat.S_IMODE(os.stat(self.cfg.db_path).st_mode)
        self.assertEqual(mode & stat.S_IROTH, 0, "DB must not be world-readable")

    def test_session_open_close_idempotent(self):
        self.store.open_session("s1", "hudzaifah", "i3", 1000)
        self.assertTrue(self.store.close_session("s1", 2000, "ended"))
        # second close is a no-op
        self.assertFalse(self.store.close_session("s1", 3000, "again"))
        row = self.store.get_session("s1")
        self.assertEqual(row["logout_epoch"], 2000)

    def test_event_insert_and_query(self):
        self.store.open_session("s1", "hudzaifah", "i3", 1000)
        row = {"schema_version": 1, "username": "hudzaifah", "device": "i3",
               "event_type": "submitted_search", "source": "browser_extension",
               "site": "google.com", "evidence": "direct_user_action",
               "content": "x", "content_truncated": 0, "client_timestamp": ""}
        self.store.insert_event(row, "s1", 1500)
        evs = self.store.events_for_session("s1")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["username"], "hudzaifah")

    def test_outbox_idempotent_on_session(self):
        self.store.open_session("s1", "hudzaifah", "i3", 1000)
        self.assertTrue(self.store.enqueue_report("r1", "s1", "hello"))
        # same session again -> ignored
        self.assertFalse(self.store.enqueue_report("r2", "s1", "world"))
        rows = self.store.conn.execute("SELECT COUNT(*) c FROM outbox").fetchone()
        self.assertEqual(rows["c"], 1)

    def test_report_delivery_state_transitions(self):
        self.store.open_session("s1", "hudzaifah", "i3", 1000)
        self.store.enqueue_report("r1", "s1", "hello")
        self.store.mark_report_attempt("r1", "boom", max_retries=3)
        row = self.store.conn.execute(
            "SELECT * FROM outbox WHERE report_id='r1'").fetchone()
        self.assertEqual(row["attempt_count"], 1)
        self.assertEqual(row["delivery_state"], "retry")
        self.store.mark_report_sent("r1")
        row = self.store.conn.execute(
            "SELECT * FROM outbox WHERE report_id='r1'").fetchone()
        self.assertEqual(row["delivery_state"], "sent")

    def test_retention_purges_old_events(self):
        self.store.open_session("s1", "hudzaifah", "i3", 1000)
        old = {"schema_version": 1, "username": "hudzaifah", "device": "i3",
               "event_type": "submitted_search", "source": "browser_extension",
               "site": "google.com", "evidence": "direct_user_action",
               "content": "old", "content_truncated": 0, "client_timestamp": ""}
        import time
        self.store.insert_event(old, "s1", int(time.time()) - 40 * 86400)
        self.store.insert_event(dict(old, content="new"), "s1", int(time.time()))
        purged = self.store.purge_older_than(14)
        self.assertEqual(purged, 1)
        remaining = self.store.events_for_session("s1")
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["content"], "new")


if __name__ == "__main__":
    unittest.main()

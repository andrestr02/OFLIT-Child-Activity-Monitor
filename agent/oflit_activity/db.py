"""SQLite persistence for the OFLIT Child Activity Monitor.

Small, reliable, stdlib-only. Holds a schema-version table and a simple
forward-only migration strategy, the event store, session records, and the
durable report outbox used for idempotent Telegram delivery.

File permissions are set restrictively on creation (0640, root:root at
install time) so a child cannot read, tamper with, or forge into the store.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

from . import SCHEMA_VERSION

# Ordered migrations. Each entry is (target_version, list_of_SQL_statements).
_MIGRATIONS = [
    (
        1,
        [
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                username     TEXT NOT NULL,
                device       TEXT NOT NULL,
                login_epoch  INTEGER NOT NULL,
                logout_epoch INTEGER,
                end_reason   TEXT,
                report_state TEXT NOT NULL DEFAULT 'open',
                created_at   INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS events (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                schema_version    INTEGER NOT NULL,
                session_id        TEXT,
                username          TEXT NOT NULL,
                device            TEXT NOT NULL,
                event_type        TEXT NOT NULL,
                source            TEXT NOT NULL,
                site              TEXT,
                evidence          TEXT NOT NULL,
                content           TEXT,
                content_truncated INTEGER NOT NULL DEFAULT 0,
                client_timestamp  TEXT,
                event_epoch       INTEGER NOT NULL,
                created_at        INTEGER NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_events_epoch ON events(event_epoch)",
            """
            CREATE TABLE IF NOT EXISTS outbox (
                report_id     TEXT PRIMARY KEY,
                session_id    TEXT NOT NULL UNIQUE,
                payload       TEXT NOT NULL,
                delivery_state TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_attempt_at INTEGER,
                last_error    TEXT,
                created_at    INTEGER NOT NULL
            )
            """,
        ],
    ),
]


def _now() -> int:
    return int(time.time())


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        newly_created = not self.path.exists()
        # check_same_thread=False lets the ingest threads and the main loop
        # share one connection; callers must serialize writes with a lock
        # (the daemon does — see daemon.py). SQLite itself is serialized via
        # busy_timeout below.
        self.conn = sqlite3.connect(
            str(self.path), timeout=15, check_same_thread=False
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=10000")
        if newly_created:
            # Restrictive perms on first creation. Install-time chown handles
            # ownership; here we ensure the mode is never world-readable.
            try:
                os.chmod(self.path, 0o640)
            except OSError:
                pass
        self.migrate()

    # -- schema ------------------------------------------------------------
    def _current_version(self) -> int:
        try:
            cur = self.conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            )
            row = cur.fetchone()
            return int(row["value"]) if row else 0
        except sqlite3.OperationalError:
            return 0

    def migrate(self) -> None:
        current = self._current_version()
        for target, statements in _MIGRATIONS:
            if target <= current:
                continue
            with self.conn:
                for sql in statements:
                    self.conn.execute(sql)
                self.conn.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(target),),
                )
        # Sanity: never leave the DB claiming a version we don't understand.
        assert self._current_version() <= SCHEMA_VERSION

    # -- sessions ----------------------------------------------------------
    def open_session(self, session_id, username, device, login_epoch) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO sessions"
                "(session_id, username, device, login_epoch, report_state, created_at)"
                " VALUES(?,?,?,?, 'open', ?)",
                (session_id, username, device, int(login_epoch), _now()),
            )

    def close_session(self, session_id, logout_epoch, end_reason) -> bool:
        """Mark a session closed. Returns True if this call performed the
        transition (idempotent: a second call returns False)."""
        with self.conn:
            cur = self.conn.execute(
                "UPDATE sessions SET logout_epoch=?, end_reason=? "
                "WHERE session_id=? AND logout_epoch IS NULL",
                (int(logout_epoch), end_reason, session_id),
            )
            return cur.rowcount > 0

    def get_session(self, session_id):
        cur = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id=?", (session_id,)
        )
        return cur.fetchone()

    def open_sessions(self):
        cur = self.conn.execute(
            "SELECT * FROM sessions WHERE logout_epoch IS NULL ORDER BY login_epoch"
        )
        return cur.fetchall()

    def mark_reported(self, session_id) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE sessions SET report_state='reported' WHERE session_id=?",
                (session_id,),
            )

    # -- events ------------------------------------------------------------
    def insert_event(self, row: dict, session_id, event_epoch=None) -> int:
        event_epoch = int(event_epoch if event_epoch is not None else _now())
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO events(
                    schema_version, session_id, username, device, event_type,
                    source, site, evidence, content, content_truncated,
                    client_timestamp, event_epoch, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row["schema_version"], session_id, row["username"], row["device"],
                    row["event_type"], row["source"], row.get("site"), row["evidence"],
                    row.get("content"), row.get("content_truncated", 0),
                    row.get("client_timestamp"), event_epoch, _now(),
                ),
            )
            return cur.lastrowid

    def events_for_session(self, session_id):
        cur = self.conn.execute(
            "SELECT * FROM events WHERE session_id=? ORDER BY event_epoch, id",
            (session_id,),
        )
        return cur.fetchall()

    # -- outbox ------------------------------------------------------------
    def enqueue_report(self, report_id, session_id, payload) -> bool:
        """Insert a report for delivery. Idempotent on session_id: a second
        enqueue for the same session is a no-op (returns False)."""
        with self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO outbox"
                "(report_id, session_id, payload, delivery_state, created_at)"
                " VALUES(?,?,?, 'pending', ?)",
                (report_id, session_id, payload, _now()),
            )
            return cur.rowcount > 0

    def pending_reports(self, max_retries: int):
        cur = self.conn.execute(
            "SELECT * FROM outbox WHERE delivery_state IN ('pending','retry') "
            "AND attempt_count < ? ORDER BY created_at",
            (max_retries,),
        )
        return cur.fetchall()

    def mark_report_sent(self, report_id) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE outbox SET delivery_state='sent', last_attempt_at=? "
                "WHERE report_id=?",
                (_now(), report_id),
            )

    def mark_report_attempt(self, report_id, error, max_retries) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE outbox SET attempt_count=attempt_count+1, last_attempt_at=?, "
                "last_error=?, delivery_state=CASE WHEN attempt_count+1 >= ? "
                "THEN 'failed' ELSE 'retry' END WHERE report_id=?",
                (_now(), str(error)[:500], max_retries, report_id),
            )

    # -- retention ---------------------------------------------------------
    def purge_older_than(self, retention_days: int) -> int:
        cutoff = _now() - retention_days * 86400
        with self.conn:
            cur = self.conn.execute(
                "DELETE FROM events WHERE event_epoch < ?", (cutoff,)
            )
            self.conn.execute(
                "DELETE FROM outbox WHERE delivery_state='sent' AND created_at < ?",
                (cutoff,),
            )
            # Keep closed+reported session rows for the same window, then drop.
            self.conn.execute(
                "DELETE FROM sessions WHERE logout_epoch IS NOT NULL "
                "AND logout_epoch < ? AND report_state='reported'",
                (cutoff,),
            )
            return cur.rowcount

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

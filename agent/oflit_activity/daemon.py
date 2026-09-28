"""The OFLIT Child Activity Monitor agent daemon.

Ties the pieces together:

* runs the loopback ingestion server and attributes every accepted event to
  the *authoritative* active child session (never the extension's claim);
* polls systemd-logind for child graphical sessions, opening a session (and a
  ``session_login`` event) on appearance and, after a debounce grace period,
  closing it (``session_logout``) on disappearance;
* on session close, aggregates the session, optionally folds in coarse Squid
  network observations, renders the final report, and enqueues it once in the
  durable outbox (idempotent: one session -> one report);
* attempts Telegram delivery of pending outbox reports each tick;
* enforces retention.

FAIL OPEN: every step is wrapped so a monitoring failure never propagates. The
agent is never a dependency for child login or logout.
"""

from __future__ import annotations

import signal
import threading
import time
import uuid

from . import model
from . import SCHEMA_VERSION
from .aggregate import build_summary
from .apps import running_apps_for_user
from .db import Store
from .ingest import IngestServer
from .report import render_telegram
from .sessions import list_child_graphical_sessions
from . import squid as squid_mod
from .telegram import HttpTelegramSender, deliver_pending


class Agent:
    def __init__(self, config, store=None, sender=None, logger=None, clock=time.time):
        self.config = config
        self.store = store or Store(config.db_path)
        self.sender = sender or HttpTelegramSender(config.telegram_env_path)
        self.log = logger or (lambda msg: None)
        self.clock = clock
        self._lock = threading.Lock()
        # session_id -> GraphicalSession currently active (last poll).
        self._active = {}
        # session_id -> epoch when it was first seen gone (for grace debounce).
        self._pending_end = {}
        self._server = None
        self._stop = threading.Event()

    # -- ingestion ---------------------------------------------------------
    def _current_session_for(self, claimed_user):
        """Choose the authoritative session for an incoming event."""
        active = self._active
        if not active:
            return None
        if len(active) == 1:
            return next(iter(active.values()))
        # Multiple active monitored sessions: prefer one matching the claimed
        # username; otherwise the most recently logged in.
        for sess in active.values():
            if sess.username == claimed_user:
                return sess
        return max(active.values(), key=lambda s: s.login_epoch)

    def ingest(self, payload):
        """Validate, attribute, and store one event. Returns (accepted, reason)."""
        try:
            event = model.validate_event(
                payload,
                max_content_chars=self.config.max_content_chars,
                schema_version=SCHEMA_VERSION,
            )
        except model.RejectedEvent as exc:
            self.log(f"event rejected: {exc}")
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001
            self.log(f"event validation error: {exc}")
            return False, "validation error"

        with self._lock:
            sess = self._current_session_for(event.username)
            if sess is None:
                return False, "no active child session"
            # Authoritative attribution — override any claimed identity.
            event.username = sess.username
            event.device = self.config.device
            event.session_id = sess.session_id
            row = event.to_row()
            try:
                self.store.insert_event(row, sess.session_id, int(self.clock()))
            except Exception as exc:  # noqa: BLE001
                self.log(f"event store failed: {exc}")
                return False, "store error"
        return True, "accepted"

    # -- session lifecycle -------------------------------------------------
    def _record_session_event(self, sess, event_type, epoch):
        row = model.Event(
            schema_version=1,
            event_type=event_type,
            source=model.SOURCE_AGENT,
            site="",
            evidence=model.EVIDENCE_DIRECT_USER_ACTION,
            username=sess.username,
            device=self.config.device,
            session_id=sess.session_id,
        ).to_row()
        try:
            self.store.insert_event(row, sess.session_id, int(epoch))
        except Exception as exc:  # noqa: BLE001
            self.log(f"session event store failed: {exc}")

    def _sample_apps(self, sess, epoch):
        try:
            labels = running_apps_for_user(sess.username)
        except Exception as exc:  # noqa: BLE001
            self.log(f"app sample failed: {exc}")
            return
        for label in labels:
            row = model.Event(
                schema_version=1,
                event_type=model.EV_APP_STARTED,
                source=model.SOURCE_AGENT,
                site="",
                evidence=model.EVIDENCE_PROCESS_RUNNING,
                content=label,
                username=sess.username,
                device=self.config.device,
                session_id=sess.session_id,
            ).to_row()
            try:
                self.store.insert_event(row, sess.session_id, int(epoch))
            except Exception as exc:  # noqa: BLE001
                self.log(f"app event store failed: {exc}")

    def _finalize_session(self, sess, logout_epoch, reason):
        """Close a session and enqueue exactly one final report."""
        transitioned = self.store.close_session(sess.session_id, logout_epoch, reason)
        if not transitioned:
            # Already closed (e.g. after agent restart) — do not duplicate.
            return
        self._record_session_event(sess, model.EV_SESSION_LOGOUT, logout_epoch)

        session_row = self.store.get_session(sess.session_id)
        events = self.store.events_for_session(sess.session_id)

        net = (None, None)
        if self.config.squid_enabled:
            try:
                net = squid_mod.summarize(
                    self.config.squid_access_log,
                    session_row["login_epoch"],
                    logout_epoch,
                )
            except Exception as exc:  # noqa: BLE001
                self.log(f"squid summarize failed: {exc}")

        summary = build_summary(session_row, events, net=net)
        try:
            text = render_telegram(summary, self.config.timezone)
        except Exception as exc:  # noqa: BLE001
            self.log(f"report render failed: {exc}")
            return

        report_id = uuid.uuid4().hex
        # Idempotent on session_id: OR IGNORE means a re-close never re-queues.
        enqueued = self.store.enqueue_report(report_id, sess.session_id, text)
        if enqueued:
            self.store.mark_reported(sess.session_id)
            self.log(f"queued report for session {sess.session_id}")

    def poll_sessions(self):
        now = int(self.clock())
        with self._lock:
            current = list_child_graphical_sessions(self.config.monitored_users, now)

            # New sessions.
            for sid, sess in current.items():
                if sid not in self._active:
                    self.store.open_session(
                        sid, sess.username, self.config.device, sess.login_epoch
                    )
                    self._record_session_event(sess, model.EV_SESSION_LOGIN, sess.login_epoch)
                    self.log(f"session opened: {sid}")
                self._pending_end.pop(sid, None)

            # Sessions that disappeared -> start/continue grace timer.
            for sid, sess in list(self._active.items()):
                if sid not in current:
                    first_gone = self._pending_end.setdefault(sid, now)
                    if now - first_gone >= self.config.session_end_grace_seconds:
                        self._finalize_session(sess, now, "session ended")
                        self._pending_end.pop(sid, None)

            # Sample apps for still-active sessions.
            for sess in current.values():
                self._sample_apps(sess, now)

            # Update active set: keep sessions still within grace as "active"
            # only for finalization bookkeeping; drop finalized ones.
            still = dict(current)
            for sid in list(self._pending_end.keys()):
                if sid in self._active and sid not in still:
                    still[sid] = self._active[sid]
            self._active = still

    def finalize_all_open(self, reason):
        """On shutdown, close any still-open child sessions so a shutdown with
        an active child session still produces a report."""
        now = int(self.clock())
        with self._lock:
            for sess in list(self._active.values()):
                self._finalize_session(sess, now, reason)
            self._active = {}
            self._pending_end = {}

    # -- delivery / retention ---------------------------------------------
    def tick_delivery(self):
        if not self.config.telegram_enabled:
            return
        with self._lock:
            deliver_pending(
                self.store, self.sender, self.config.telegram_max_retries, self.log
            )

    def tick_retention(self):
        with self._lock:
            try:
                self.store.purge_older_than(self.config.retention_days)
            except Exception as exc:  # noqa: BLE001
                self.log(f"retention purge failed: {exc}")

    # -- run loop ----------------------------------------------------------
    def start_server(self):
        self._server = IngestServer(self.ingest, self.config, self.log)
        self._server.start()
        self.log(f"ingest listening on {self.config.listen_host}:{self._server.port}")

    def run(self, poll_interval=5, retention_interval=3600):
        self.start_server()

        def _handle_signal(signum, frame):  # noqa: ARG001
            self.log(f"signal {signum} received; finalizing open sessions")
            self._stop.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _handle_signal)
            except (ValueError, OSError):
                pass  # not in main thread (tests) — fine

        last_retention = 0
        try:
            while not self._stop.is_set():
                try:
                    self.poll_sessions()
                    self.tick_delivery()
                    now = int(self.clock())
                    if now - last_retention >= retention_interval:
                        self.tick_retention()
                        last_retention = now
                except Exception as exc:  # noqa: BLE001 - loop must never die
                    self.log(f"poll loop error: {exc}")
                self._stop.wait(poll_interval)
        finally:
            # Best-effort: flush reports for sessions still open at shutdown.
            self.finalize_all_open("agent shutdown")
            self.tick_delivery()
            if self._server:
                self._server.stop()
            self.store.close()
            self.log("agent stopped")

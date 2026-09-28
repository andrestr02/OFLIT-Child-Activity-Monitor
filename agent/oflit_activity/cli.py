"""``child-activity`` CLI — read-only reporting over the local store.

Subcommands:
  status            live view of currently active child session(s)
  report SESSION    render the summary for a session id (or 'last')
  sessions          list recent sessions
  outbox            show delivery queue state
  flush             attempt Telegram delivery of pending reports now
  purge             apply retention now

Intended to run as an administrator (the DB is root-readable only).
"""

from __future__ import annotations

import argparse
import sys
import time

from .aggregate import build_summary
from .config import load_config
from .db import Store
from .report import render_status, render_telegram
from .telegram import HttpTelegramSender, deliver_pending


def _load(args):
    config = load_config(args.config)
    store = Store(config.db_path)
    return config, store


def cmd_status(config, store, args):
    rows = store.open_sessions()
    if not rows:
        print("Tidak ada sesi anak aktif.")
        return 0
    for srow in rows:
        events = store.events_for_session(srow["session_id"])
        summary = build_summary(srow, events)
        print(render_status(summary, active=True, timezone=config.timezone))
    return 0


def cmd_report(config, store, args):
    session_id = args.session
    if session_id == "last":
        rows = store.conn.execute(
            "SELECT session_id FROM sessions ORDER BY login_epoch DESC LIMIT 1"
        ).fetchall()
        if not rows:
            print("Belum ada sesi.")
            return 1
        session_id = rows[0]["session_id"]
    srow = store.get_session(session_id)
    if not srow:
        print(f"Sesi tidak ditemukan: {session_id}")
        return 1
    events = store.events_for_session(session_id)
    summary = build_summary(srow, events)
    print(render_telegram(summary, timezone=config.timezone))
    return 0


def cmd_sessions(config, store, args):
    rows = store.conn.execute(
        "SELECT session_id, username, login_epoch, logout_epoch, report_state "
        "FROM sessions ORDER BY login_epoch DESC LIMIT ?",
        (args.limit,),
    ).fetchall()
    for r in rows:
        state = "aktif" if not r["logout_epoch"] else r["report_state"]
        print(f"{r['session_id']}  {r['username']:12} {state}")
    return 0


def cmd_outbox(config, store, args):
    rows = store.conn.execute(
        "SELECT report_id, session_id, delivery_state, attempt_count, last_error "
        "FROM outbox ORDER BY created_at DESC LIMIT ?",
        (args.limit,),
    ).fetchall()
    for r in rows:
        print(
            f"{r['report_id'][:8]}  {r['session_id']:28} {r['delivery_state']:8} "
            f"attempts={r['attempt_count']}  {r['last_error'] or ''}"
        )
    return 0


def cmd_flush(config, store, args):
    sender = HttpTelegramSender(config.telegram_env_path)
    if not sender.configured():
        print("Telegram belum terkonfigurasi (telegram.env).")
        return 1
    stats = deliver_pending(store, sender, config.telegram_max_retries, print)
    print(f"sent={stats['sent']} failed={stats['failed']}")
    return 0


def cmd_purge(config, store, args):
    n = store.purge_older_than(config.retention_days)
    print(f"purged {n} event(s) older than {config.retention_days}d")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="child-activity")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    r = sub.add_parser("report")
    r.add_argument("session", nargs="?", default="last")
    s = sub.add_parser("sessions")
    s.add_argument("--limit", type=int, default=20)
    o = sub.add_parser("outbox")
    o.add_argument("--limit", type=int, default=20)
    sub.add_parser("flush")
    sub.add_parser("purge")
    return p


_DISPATCH = {
    "status": cmd_status,
    "report": cmd_report,
    "sessions": cmd_sessions,
    "outbox": cmd_outbox,
    "flush": cmd_flush,
    "purge": cmd_purge,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    config, store = _load(args)
    try:
        return _DISPATCH[args.cmd](config, store, args)
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())

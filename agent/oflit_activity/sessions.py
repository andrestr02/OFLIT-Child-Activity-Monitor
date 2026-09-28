"""Graphical child-session tracking via systemd-logind.

Mirrors the detection approach already used by ``oflit-child-time-limit``'s
enforcer (``loginctl list-sessions`` + ``loginctl show-session``), so the two
systems agree on what a "child graphical session" is. We only ever consider
usernames explicitly configured as monitored; system/service/SSH sessions are
ignored.

A stable ``session_id`` is derived from the logind session id plus the login
timestamp, so one logind session maps to exactly one activity session (and
therefore exactly one final report), and a reused numeric id after reboot does
not collide with a prior session.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

GRAPHICAL_TYPES = ("wayland", "x11")


@dataclass(frozen=True)
class GraphicalSession:
    logind_id: str
    username: str
    session_id: str      # stable, agent-level id
    login_epoch: int


def _run(cmd, timeout=8):
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return 1, "", "loginctl unavailable"


def _show_session(logind_id):
    rc, out, _ = _run(
        [
            "loginctl", "show-session", logind_id,
            "-p", "Type", "-p", "Class", "-p", "Name",
            "-p", "Active", "-p", "Remote", "-p", "Timestamp",
        ]
    )
    if rc != 0:
        return {}
    info = {}
    for line in out.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            info[key.strip()] = value.strip()
    return info


def _timestamp_epoch(info) -> int:
    # logind exposes a monotonic and a realtime timestamp; TimestampMonotonic
    # is not wall-clock. We derive login epoch from "Timestamp=" (a human
    # string) when possible, else fall back to now via the caller.
    ts = info.get("Timestamp", "")
    # Format e.g. "Sun 2026-09-28 10:10:00 WIB". Parse best-effort.
    import time
    for fmt in ("%a %Y-%m-%d %H:%M:%S %Z", "%a %Y-%m-%d %H:%M:%S"):
        try:
            return int(time.mktime(time.strptime(ts, fmt)))
        except (ValueError, OverflowError):
            continue
    return 0


def list_child_graphical_sessions(monitored_users, now_epoch) -> dict:
    """Return {session_id: GraphicalSession} for currently active graphical
    sessions owned by monitored users."""
    rc, out, _ = _run(["loginctl", "list-sessions", "--no-legend"])
    result = {}
    if rc != 0:
        return result
    monitored = set(monitored_users)
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        logind_id = parts[0]
        info = _show_session(logind_id)
        username = info.get("Name", "")
        if username not in monitored:
            continue
        if info.get("Class") != "user":
            continue
        if info.get("Type") not in GRAPHICAL_TYPES:
            continue
        if info.get("Remote") == "yes":
            continue
        login_epoch = _timestamp_epoch(info) or now_epoch
        session_id = f"{username}-{logind_id}-{login_epoch}"
        result[session_id] = GraphicalSession(
            logind_id=logind_id,
            username=username,
            session_id=session_id,
            login_epoch=login_epoch,
        )
    return result

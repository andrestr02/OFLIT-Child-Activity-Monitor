"""Squid access-log observation — NETWORK_OBSERVATION evidence only.

Opt-in and honestly labeled. A proxy log line proves a request crossed the
proxy; it does NOT prove a human opened that site (it may be an embedded
resource, a preload, a background request, or third-party content). Everything
this module produces is therefore evidence-level ``network_observation`` and is
worded as "network observation" / "blocked request observed" downstream, never
"the child opened X".

On this device the proxy runs on loopback and does not distinguish per-user
traffic, so observations are correlated to a session only by time window and
are reported as coarse, device-level network context.
"""

from __future__ import annotations

import re

# Common Squid native log format:
#   time elapsed client action/status bytes method URL ...
# We parse defensively and tolerate format variations.
_LINE = re.compile(
    r"^(?P<ts>\d+(?:\.\d+)?)\s+\S+\s+\S+\s+(?P<action>\S+)\s+\d+\s+\S+\s+(?P<url>\S+)"
)

# Actions that indicate a denied/blocked request.
_BLOCKED_MARKERS = ("DENIED", "BLOCK", "TCP_DENIED", "TCP_BLOCK")


def _host(url: str) -> str:
    url = re.sub(r"^[a-z]+://", "", url or "")
    host = url.split("/", 1)[0].split(":", 1)[0]
    return host.lower()


def read_observations(access_log_path, since_epoch, until_epoch, limit=5000):
    """Yield (host, blocked_bool, epoch) for log lines in a time window.

    Reads the file read-only; missing/unreadable file yields nothing (fail
    open — network observation is never required for core monitoring).
    """
    try:
        f = open(access_log_path, "r", errors="replace")
    except (FileNotFoundError, PermissionError, IsADirectoryError, OSError):
        return
    count = 0
    with f:
        for line in f:
            m = _LINE.match(line)
            if not m:
                continue
            try:
                ts = float(m.group("ts"))
            except ValueError:
                continue
            if ts < since_epoch or ts > until_epoch:
                continue
            action = m.group("action").upper()
            blocked = any(mk in action for mk in _BLOCKED_MARKERS)
            host = _host(m.group("url"))
            if not host:
                continue
            yield host, blocked, int(ts)
            count += 1
            if count >= limit:
                return


def summarize(access_log_path, since_epoch, until_epoch):
    """Return ({visited_hosts}, {blocked_hosts}) as sorted lists, deduped."""
    visited, blocked = set(), set()
    for host, is_blocked, _ in read_observations(
        access_log_path, since_epoch, until_epoch
    ):
        if is_blocked:
            blocked.add(host)
        else:
            visited.add(host)
    # A host that was ever blocked is reported as blocked (more conservative).
    visited -= blocked
    return sorted(visited), sorted(blocked)

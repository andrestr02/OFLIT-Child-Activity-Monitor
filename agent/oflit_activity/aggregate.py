"""Session aggregation: turn a session's raw events into a structured summary.

The summary preserves evidence levels so the report layer can word each item
honestly (direct user action vs. visited resource vs. network observation).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import model


@dataclass
class SessionSummary:
    session_id: str
    username: str
    device: str
    login_epoch: int
    logout_epoch: int
    end_reason: str = ""
    google_searches: list = field(default_factory=list)   # [(epoch, text, trunc)]
    chatgpt_prompts: list = field(default_factory=list)    # [(epoch, text, trunc)]
    visited: list = field(default_factory=list)            # [(epoch, host)]
    apps: list = field(default_factory=list)               # [label]
    net_visited: list = field(default_factory=list)        # [host]
    net_blocked: list = field(default_factory=list)        # [host]

    @property
    def duration_seconds(self) -> int:
        if self.logout_epoch and self.login_epoch:
            return max(0, self.logout_epoch - self.login_epoch)
        return 0


def build_summary(session_row, event_rows, net=None) -> SessionSummary:
    net = net or (None, None)
    summary = SessionSummary(
        session_id=session_row["session_id"],
        username=session_row["username"],
        device=session_row["device"],
        login_epoch=session_row["login_epoch"],
        logout_epoch=session_row["logout_epoch"] or 0,
        end_reason=session_row["end_reason"] or "",
    )
    seen_apps = set()
    for ev in event_rows:
        etype = ev["event_type"]
        epoch = ev["event_epoch"]
        content = ev["content"] or ""
        trunc = bool(ev["content_truncated"])
        if etype == model.EV_SUBMITTED_SEARCH:
            summary.google_searches.append((epoch, content, trunc))
        elif etype == model.EV_SUBMITTED_PROMPT:
            summary.chatgpt_prompts.append((epoch, content, trunc))
        elif etype == model.EV_NAVIGATION:
            host = model.normalize_site(content)
            if host:
                summary.visited.append((epoch, host))
        elif etype == model.EV_APP_STARTED:
            if content and content not in seen_apps:
                seen_apps.add(content)
                summary.apps.append(content)
    if net[0]:
        summary.net_visited = list(net[0])
    if net[1]:
        summary.net_blocked = list(net[1])
    return summary

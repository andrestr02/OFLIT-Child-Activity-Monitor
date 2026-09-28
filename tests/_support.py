"""Shared test bootstrap: make the agent package importable and provide fakes.

All fixtures here are SYNTHETIC. No real child data, no production Telegram.
"""

import os
import sys
import tempfile

_AGENT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"
)
if _AGENT not in sys.path:
    sys.path.insert(0, _AGENT)

from oflit_activity.config import Config  # noqa: E402
from oflit_activity import sessions as S  # noqa: E402


class Clock:
    def __init__(self, t=1_700_000_000):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds
        return self.t


class FakeSender:
    """Captures messages instead of hitting Telegram. Optionally fails N times
    to exercise retry/idempotency paths."""

    def __init__(self, fail_times=0):
        self.sent = []
        self.fail_times = fail_times
        self.attempts = 0

    def configured(self):
        return True

    def send(self, text):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise RuntimeError("simulated network failure")
        self.sent.append(text)
        return True


def temp_config(**overrides):
    d = tempfile.mkdtemp(prefix="oflit-test-")
    base = dict(
        monitored_users=("hudzaifah", "azzahra", "ibrohim"),
        device="oflitlab-i3",
        observer="oflitlab-i3",
        state_dir=d,
        telegram_enabled=True,
        session_end_grace_seconds=0,
        max_content_chars=200,
    )
    base.update(overrides)
    return Config(**base)


def session(username="hudzaifah", logind_id="88", login_epoch=1_700_000_000):
    sid = f"{username}-{logind_id}-{login_epoch}"
    return S.GraphicalSession(logind_id, username, sid, login_epoch)

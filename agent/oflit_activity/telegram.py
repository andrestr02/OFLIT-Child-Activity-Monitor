"""Telegram delivery over the EXISTING OFL IT Lab Monitoring transport.

No new bot, no new token. Credentials are read at send time from the same
``telegram.env`` the fleet watcher and daily ops report already use
(``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_ID``). The token is never copied into
this project's config, database, logs, or git.

Delivery is decoupled from session lifecycle via the durable outbox in the DB:
sessions end regardless of Telegram availability, and retries are idempotent
(one session -> one report). A pluggable ``sender`` makes the whole path
testable without ever touching the production bot.
"""

from __future__ import annotations

import urllib.parse
import urllib.request

from .config import parse_env_file


def load_credentials(env_path):
    """Return (token, chat_id) from the existing telegram.env, or ('','')."""
    env = parse_env_file(env_path if hasattr(env_path, "read_text") else __import__("pathlib").Path(env_path))
    return env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", "")


class HttpTelegramSender:
    """Real sender. Posts to api.telegram.org. Returns True on HTTP 200."""

    def __init__(self, env_path, timeout=15):
        self.env_path = env_path
        self.timeout = timeout

    def configured(self) -> bool:
        token, chat = load_credentials(self.env_path)
        return bool(token and chat)

    def send(self, text: str) -> bool:
        token, chat = load_credentials(self.env_path)
        if not token or not chat:
            raise RuntimeError("telegram credentials not configured")
        api = "https:" + "//" + "api.telegram.org"
        url = f"{api}/bot{token}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"}
        ).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return resp.status == 200


def deliver_pending(store, sender, max_retries: int, logger=None) -> dict:
    """Attempt delivery of all pending/retry reports. Idempotent and
    fail-safe: any per-report failure is recorded and retried later, never
    raised. Returns {'sent': n, 'failed': n, 'skipped': n}."""
    stats = {"sent": 0, "failed": 0, "skipped": 0}
    try:
        pending = store.pending_reports(max_retries)
    except Exception as exc:  # noqa: BLE001
        if logger:
            logger(f"outbox read failed: {exc}")
        return stats
    for row in pending:
        report_id = row["report_id"]
        try:
            ok = sender.send(row["payload"])
        except Exception as exc:  # noqa: BLE001 - network/config errors expected
            store.mark_report_attempt(report_id, exc, max_retries)
            stats["failed"] += 1
            if logger:
                logger(f"report {report_id} attempt failed: {exc}")
            continue
        if ok:
            store.mark_report_sent(report_id)
            stats["sent"] += 1
        else:
            store.mark_report_attempt(report_id, "non-200 response", max_retries)
            stats["failed"] += 1
    return stats

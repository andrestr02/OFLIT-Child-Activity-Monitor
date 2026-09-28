"""Configuration loading for the OFLIT Child Activity Monitor agent.

Configuration is intentionally simple: a ``key=value`` file (same dialect as
the existing OFL runtime configs). No secrets live here — the Telegram token
is read separately from the existing ``/etc/ofl-ai-lab/telegram.env`` at
delivery time and is never copied into this project's config or database.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Default install locations. Overridable via env for tests / non-root runs.
DEFAULT_CONFIG_PATH = Path(
    os.environ.get("OFLIT_ACTIVITY_CONFIG", "/etc/oflit-activity/agent.conf")
)
DEFAULT_STATE_DIR = Path(
    os.environ.get("OFLIT_ACTIVITY_STATE_DIR", "/var/lib/oflit-activity")
)
# The existing OFL IT Lab Monitoring Telegram credentials. Reused, never
# duplicated, never committed. Same file the fleet watcher / ops report use.
DEFAULT_TELEGRAM_ENV = Path(
    os.environ.get("OFLIT_ACTIVITY_TELEGRAM_ENV", "/etc/ofl-ai-lab/telegram.env")
)

# Hard safety ceilings. These are floors/caps the config cannot exceed, so a
# misconfigured file can never turn the monitor into a bulk recorder.
MAX_CONTENT_CHARS_CEILING = 2000
DEFAULT_CONTENT_CHARS = 500


def _coerce_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def parse_env_file(path: Path) -> dict:
    """Parse a ``key=value`` file. Missing file -> empty dict (fail open)."""
    values: dict = {}
    try:
        text = path.read_text()
    except (FileNotFoundError, PermissionError, IsADirectoryError):
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass
class Config:
    # Child usernames this agent is allowed to monitor. Anything not listed
    # here is ignored entirely (no events, no sessions, no reports).
    monitored_users: tuple = ()
    device: str = "unknown-device"
    observer: str = "unknown-device"
    timezone: str = "Asia/Jakarta"

    # Loopback-only ingestion endpoint.
    listen_host: str = "127.0.0.1"
    listen_port: int = 8791

    # A cheap shared marker the extension echoes back. NOT a security boundary
    # against the child (who owns the browser); it only filters stray local
    # noise. See docs/SECURITY.md.
    ingest_token: str = ""

    # Payload / content limits.
    max_payload_bytes: int = 16 * 1024
    max_content_chars: int = DEFAULT_CONTENT_CHARS

    # Retention (days) for stored events. Conservative default; owner-tunable.
    retention_days: int = 14

    # Network observation (Squid) — opt-in, coarse, honestly labeled.
    squid_enabled: bool = False
    squid_access_log: str = "/var/log/squid/access.log"

    # Delivery.
    telegram_enabled: bool = True
    telegram_env_path: str = str(DEFAULT_TELEGRAM_ENV)
    telegram_max_retries: int = 8

    # Session-end debounce: how long a child session must be gone before we
    # consider it ended (guards against transient logind flaps). Seconds.
    session_end_grace_seconds: int = 20

    state_dir: str = str(DEFAULT_STATE_DIR)

    raw: dict = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return Path(self.state_dir) / "activity.db"

    def is_monitored(self, username: str) -> bool:
        return username in self.monitored_users


def load_config(path: Path = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = parse_env_file(path)

    users = tuple(
        u for u in (raw.get("MONITORED_USERS", "").replace(",", " ").split()) if u
    )

    def _int(key: str, default: int) -> int:
        try:
            return int(raw.get(key, default))
        except (TypeError, ValueError):
            return default

    max_chars = min(
        _int("MAX_CONTENT_CHARS", DEFAULT_CONTENT_CHARS), MAX_CONTENT_CHARS_CEILING
    )

    return Config(
        monitored_users=users,
        device=raw.get("DEVICE", "unknown-device"),
        observer=raw.get("OBSERVER", raw.get("DEVICE", "unknown-device")),
        timezone=raw.get("TIMEZONE", "Asia/Jakarta"),
        listen_host=raw.get("LISTEN_HOST", "127.0.0.1"),
        listen_port=_int("LISTEN_PORT", 8791),
        ingest_token=raw.get("INGEST_TOKEN", ""),
        max_payload_bytes=_int("MAX_PAYLOAD_BYTES", 16 * 1024),
        max_content_chars=max(1, max_chars),
        retention_days=max(1, _int("RETENTION_DAYS", 14)),
        squid_enabled=_coerce_bool(raw.get("SQUID_ENABLED"), False),
        squid_access_log=raw.get("SQUID_ACCESS_LOG", "/var/log/squid/access.log"),
        telegram_enabled=_coerce_bool(raw.get("TELEGRAM_ENABLED", "true"), True),
        telegram_env_path=raw.get("TELEGRAM_ENV_PATH", str(DEFAULT_TELEGRAM_ENV)),
        telegram_max_retries=_int("TELEGRAM_MAX_RETRIES", 8),
        session_end_grace_seconds=_int("SESSION_END_GRACE_SECONDS", 20),
        state_dir=raw.get("STATE_DIR", str(DEFAULT_STATE_DIR)),
        raw=raw,
    )

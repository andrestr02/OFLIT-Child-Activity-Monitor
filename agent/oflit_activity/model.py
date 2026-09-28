"""Event model, validation, evidence classification, and sensitive-field
rejection for the OFLIT Child Activity Monitor.

This is the privacy heart of the system. Every event that reaches the store
passes through :func:`validate_event`, which:

* accepts only known event types from known sources on supported sites;
* **rejects** anything flagged as sensitive (passwords, tokens, cookies,
  payment data, unsent drafts) — these are dropped and never stored;
* truncates content to a bounded length and marks truncation explicitly;
* assigns an evidence level so downstream reports never overstate what a
  signal actually proves.

None of this is a keylogger: there is no keystroke event type, and free-form
content is only accepted for the explicit *submitted* event types below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------

# Evidence levels — ordered weakest-claim to strongest is NOT the point;
# the point is honest wording downstream. See docs/PRIVACY.md.
EVIDENCE_DIRECT_USER_ACTION = "direct_user_action"
EVIDENCE_VISITED_RESOURCE = "visited_resource"
EVIDENCE_NETWORK_OBSERVATION = "network_observation"
EVIDENCE_PROCESS_RUNNING = "process_running"
EVIDENCE_FOREGROUND_APP = "foreground_application"

EVIDENCE_LEVELS = frozenset(
    {
        EVIDENCE_DIRECT_USER_ACTION,
        EVIDENCE_VISITED_RESOURCE,
        EVIDENCE_NETWORK_OBSERVATION,
        EVIDENCE_PROCESS_RUNNING,
        EVIDENCE_FOREGROUND_APP,
    }
)

# Event types the system understands. Note there is deliberately no
# "keystroke", "clipboard", "screenshot", or "form_field" type.
EV_SUBMITTED_SEARCH = "submitted_search"      # a search actually submitted
EV_SUBMITTED_PROMPT = "submitted_prompt"      # a chat prompt actually sent
EV_NAVIGATION = "navigation"                  # a page the tab actually loaded
EV_APP_STARTED = "app_started"                # a process observed running
EV_NETWORK = "network_observation"            # a proxy log line
EV_SESSION_LOGIN = "session_login"
EV_SESSION_LOGOUT = "session_logout"

EVENT_TYPES = frozenset(
    {
        EV_SUBMITTED_SEARCH,
        EV_SUBMITTED_PROMPT,
        EV_NAVIGATION,
        EV_APP_STARTED,
        EV_NETWORK,
        EV_SESSION_LOGIN,
        EV_SESSION_LOGOUT,
    }
)

# Event types that may carry free-form user text (the only ones).
CONTENT_BEARING = frozenset({EV_SUBMITTED_SEARCH, EV_SUBMITTED_PROMPT})

# Sources.
SOURCE_EXTENSION = "browser_extension"
SOURCE_AGENT = "agent"
SOURCE_SQUID = "squid"
SOURCES = frozenset({SOURCE_EXTENSION, SOURCE_AGENT, SOURCE_SQUID})

# Sites the extension is allowed to report submitted content for. Anything
# else is dropped even if the extension sends it.
SUPPORTED_SITES = frozenset({"google.com", "chatgpt.com"})

# Which (site, event_type) pairs a browser-extension event may claim.
_EXTENSION_ALLOWED = {
    ("google.com", EV_SUBMITTED_SEARCH),
    ("google.com", EV_NAVIGATION),
    ("chatgpt.com", EV_SUBMITTED_PROMPT),
    ("chatgpt.com", EV_NAVIGATION),
}

# Default evidence per event type.
_DEFAULT_EVIDENCE = {
    EV_SUBMITTED_SEARCH: EVIDENCE_DIRECT_USER_ACTION,
    EV_SUBMITTED_PROMPT: EVIDENCE_DIRECT_USER_ACTION,
    EV_NAVIGATION: EVIDENCE_VISITED_RESOURCE,
    EV_APP_STARTED: EVIDENCE_PROCESS_RUNNING,
    EV_NETWORK: EVIDENCE_NETWORK_OBSERVATION,
    EV_SESSION_LOGIN: EVIDENCE_DIRECT_USER_ACTION,
    EV_SESSION_LOGOUT: EVIDENCE_DIRECT_USER_ACTION,
}

# ---------------------------------------------------------------------------
# Sensitive-field defence
# ---------------------------------------------------------------------------

# If the extension ever tags a field as sensitive, or the field type looks
# like a credential, we drop it. This is defence in depth: the extension is
# *also* built to never send these, but the agent must not rely on that.
_SENSITIVE_FLAGS = frozenset(
    {
        "password",
        "credential",
        "token",
        "secret",
        "cookie",
        "session",
        "auth",
        "otp",
        "2fa",
        "cc",
        "credit-card",
        "creditcard",
        "card-number",
        "cardnumber",
        "cvv",
        "cvc",
        "payment",
        "draft",  # unsent text must never arrive; belt and braces
    }
)

# HTML input types that must never be captured.
_SENSITIVE_INPUT_TYPES = frozenset({"password"})

# Heuristic content patterns that indicate a secret slipped through. When any
# match, the event is rejected outright (we do not try to redact-and-keep).
_SENSITIVE_CONTENT_PATTERNS = [
    re.compile(r"\b\d{13,19}\b"),                       # long digit runs (PANs)
    re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b"),  # JWT-like
    re.compile(r"\b(sk|pk|ghp|xox[baprs]|AKIA|EAA)[A-Za-z0-9_-]{16,}\b"),  # API/token prefixes
    re.compile(r"(?i)\bpassword\s*[:=]"),
]


class RejectedEvent(Exception):
    """Raised when an event must not be stored. Message is the reason."""


@dataclass
class Event:
    schema_version: int
    event_type: str
    source: str
    site: str
    evidence: str
    content: str = ""
    content_truncated: bool = False
    username: str = ""       # authoritative value is set by the agent
    device: str = ""
    session_id: str = ""
    client_timestamp: str = ""
    extra: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "source": self.source,
            "site": self.site,
            "evidence": self.evidence,
            "content": self.content,
            "content_truncated": 1 if self.content_truncated else 0,
            "username": self.username,
            "device": self.device,
            "session_id": self.session_id,
            "client_timestamp": self.client_timestamp,
        }


def _looks_sensitive_flag(value) -> bool:
    if not value:
        return False
    text = str(value).lower()
    return any(flag in text for flag in _SENSITIVE_FLAGS)


def reject_sensitive(payload: dict, content: str) -> None:
    """Raise :class:`RejectedEvent` if the payload looks sensitive.

    Fails safe: when in doubt, reject.
    """
    # 1. Explicit sensitivity flags from the extension.
    if payload.get("sensitive") is True:
        raise RejectedEvent("explicitly flagged sensitive")

    # 2. Input type / field name heuristics.
    input_type = str(payload.get("input_type", "")).lower()
    if input_type in _SENSITIVE_INPUT_TYPES:
        raise RejectedEvent(f"sensitive input_type={input_type!r}")

    for key in ("field", "field_name", "input_name", "autocomplete"):
        if _looks_sensitive_flag(payload.get(key)):
            raise RejectedEvent(f"sensitive field descriptor {key!r}")

    # 3. Unsent drafts must never be stored.
    if payload.get("submitted") is False:
        raise RejectedEvent("content not submitted (draft)")

    # 4. Content heuristics.
    if content:
        for pat in _SENSITIVE_CONTENT_PATTERNS:
            if pat.search(content):
                raise RejectedEvent("content matched sensitive pattern")


def classify_evidence(event_type: str, requested: str = "") -> str:
    """Return an evidence level, never trusting a stronger claim than the
    event type structurally supports."""
    default = _DEFAULT_EVIDENCE.get(event_type, EVIDENCE_NETWORK_OBSERVATION)
    if not requested or requested not in EVIDENCE_LEVELS:
        return default
    # A source may only *weaken* (never strengthen) the default claim. E.g. a
    # network observation can never be promoted to direct_user_action.
    _rank = {
        EVIDENCE_DIRECT_USER_ACTION: 4,
        EVIDENCE_FOREGROUND_APP: 3,
        EVIDENCE_VISITED_RESOURCE: 2,
        EVIDENCE_PROCESS_RUNNING: 1,
        EVIDENCE_NETWORK_OBSERVATION: 0,
    }
    return requested if _rank[requested] <= _rank[default] else default


def _sanitize_content(content: str, max_chars: int) -> tuple:
    """Collapse whitespace and truncate. Returns (content, truncated)."""
    if content is None:
        return "", False
    # Strip control characters (keeps the log readable and prevents log
    # injection into the Telegram message).
    content = "".join(ch for ch in str(content) if ch >= " " or ch == "\n")
    content = re.sub(r"[ \t]+", " ", content).strip()
    if len(content) > max_chars:
        return content[:max_chars].rstrip(), True
    return content, False


def normalize_site(site: str) -> str:
    """Reduce a hostname to its supported registrable form."""
    site = (site or "").strip().lower()
    site = re.sub(r"^https?://", "", site)
    site = site.split("/", 1)[0].split(":", 1)[0]
    if site.startswith("www."):
        site = site[4:]
    # Map known subdomains to their supported registrable domain.
    if site.endswith("google.com"):
        return "google.com"
    if site.endswith("chatgpt.com") or site.endswith("chat.openai.com"):
        return "chatgpt.com"
    return site


def validate_event(payload: dict, *, max_content_chars: int, schema_version: int) -> Event:
    """Validate and normalize a raw ingestion payload into an :class:`Event`.

    Raises :class:`RejectedEvent` for anything that must not be stored.
    The caller (agent) is responsible for overriding ``username`` with the
    authoritative active-session owner — the value here is advisory only.
    """
    if not isinstance(payload, dict):
        raise RejectedEvent("payload is not an object")

    event_type = str(payload.get("event_type", "")).strip()
    if event_type not in EVENT_TYPES:
        raise RejectedEvent(f"unknown event_type {event_type!r}")

    source = str(payload.get("source", "")).strip()
    if source not in SOURCES:
        raise RejectedEvent(f"unknown source {source!r}")

    site = normalize_site(payload.get("site", ""))

    # Extension events are only allowed for supported (site, type) pairs.
    if source == SOURCE_EXTENSION:
        if site not in SUPPORTED_SITES:
            raise RejectedEvent(f"unsupported site {site!r}")
        if (site, event_type) not in _EXTENSION_ALLOWED:
            raise RejectedEvent(f"disallowed extension pair {site}/{event_type}")

    raw_content = payload.get("content", "") or ""
    content = ""
    truncated = False

    if event_type in CONTENT_BEARING:
        # Sensitive-field defence runs BEFORE we keep any content.
        reject_sensitive(payload, str(raw_content))
        content, truncated = _sanitize_content(raw_content, max_content_chars)
        if not content:
            raise RejectedEvent("empty submitted content")
    else:
        # Non-content events must not smuggle free text through.
        if event_type == EV_NAVIGATION:
            # Keep only a URL/host, not arbitrary content.
            content, truncated = _sanitize_content(
                payload.get("url", "") or raw_content, max_content_chars
            )
        elif event_type == EV_APP_STARTED:
            content, truncated = _sanitize_content(raw_content, 200)
        elif event_type == EV_NETWORK:
            content, truncated = _sanitize_content(raw_content, 200)
        # session_login / session_logout carry no content.

    evidence = classify_evidence(event_type, str(payload.get("evidence", "")))

    return Event(
        schema_version=schema_version,
        event_type=event_type,
        source=source,
        site=site,
        evidence=evidence,
        content=content,
        content_truncated=truncated,
        username=str(payload.get("username", "")).strip(),  # advisory only
        device=str(payload.get("device", "")).strip(),
        session_id=str(payload.get("session_id", "")).strip(),
        client_timestamp=str(payload.get("timestamp", "")).strip(),
    )

# Architecture

## Components

1. **Chrome managed extension** (`extension/`, MV3)
   - Content-script adapters run only on `https://www.google.com/search*` and
     `https://chatgpt.com/*`.
   - `adapters/google.js` reads the submitted query from the results-page URL
     (`/search?q=`) — landing there *is* proof of submission, and the URL is far
     more stable than DOM scraping.
   - `adapters/chatgpt.js` records the composer text only on an explicit send
     gesture (Enter without Shift, or a send-button click), using resilient
     selectors and a `MutationObserver` to re-bind; it fails safe if selectors
     break.
   - `common/redact.js` drops sensitive fields and secret-looking text *in the
     page*, before anything leaves the browser.
   - `common/client.js` forwards completed events to the background worker.
   - `background.js` owns the single loopback host permission and POSTs to the
     agent. Endpoint/token come from `chrome.storage.managed` (no hard-coding).

2. **Local agent** (`agent/oflit_activity/`, stdlib-only Python 3)
   - `ingest.py` — loopback-only HTTP server (`127.0.0.1:8791`), method/path
     allowlist, payload-size cap, defensive JSON parsing.
   - `model.py` — event validation, evidence classification, sensitive-field
     rejection, content sanitization/truncation.
   - `sessions.py` — child graphical-session detection via `loginctl`
     (mirrors `oflit-child-time-limit`'s enforcer: Class=user, Type∈{wayland,x11}).
   - `apps.py` — best-effort application observation (process presence only).
   - `squid.py` — optional coarse network observation from the Squid access log.
   - `db.py` — SQLite store: schema meta, sessions, events, outbox; migrations,
     retention.
   - `aggregate.py` / `report.py` — session summary and OFL-style rendering.
   - `telegram.py` — delivery over the existing transport + idempotent outbox.
   - `daemon.py` — orchestrator loop and lifecycle; `cli.py` — the reporting CLI.

## Data flow and attribution

Events arrive from the extension with an *advisory* username. The agent
**overrides** it with the owner of the active graphical child session found via
logind, so a page (or a forged localhost request) cannot attribute activity to
another user. If there is no active monitored session, the event is rejected.

## Session lifecycle

- **Login**: a monitored graphical session appears in logind → the agent opens
  a session row and records a `session_login` event. `session_id =
  <user>-<logind_id>-<login_epoch>` is stable across restarts and reboots.
- **During**: submitted-content events are attributed and stored; running apps
  are sampled each poll.
- **End**: the session disappears from logind and stays gone for
  `SESSION_END_GRACE_SECONDS` (debounce), OR the agent receives SIGTERM
  (logout/shutdown). The agent closes the session (`session_logout`), aggregates,
  renders the report, and enqueues it **once** (idempotent on `session_id`).
  Closing Chrome, locking the screen, or a brief network drop is **not** a
  session end.

## Delivery

The final report is written to a durable `outbox` table, then delivered to the
existing OFL IT Lab Monitoring Telegram bot. Delivery is decoupled from the
session lifecycle: sessions end regardless of Telegram availability, retries are
bounded and idempotent, and a pending report survives an agent restart.

## Fail-open principle

Every monitoring step is wrapped so failure cannot propagate. The agent is a
standalone `multi-user.target` service that nothing in the login path depends
on; if it crashes or is stopped, children log in, use the computer, and log out
exactly as before.

# OFLIT Child Activity Monitor

A privacy-bounded activity monitor for OFLIT child devices. It gives a
parent/admin a trustworthy picture of what a child *actually did* on the
computer — submitted searches, submitted ChatGPT prompts, applications used,
session times — and delivers a per-session summary over the existing OFL IT Lab
Monitoring Telegram transport.

It is deliberately **not** a keylogger and **not** a credential-stealing
surveillance tool. See [Privacy boundary](#privacy-boundary).

## Purpose

- Show reliable evidence of a child's computer activity per graphical session.
- Distinguish *what the child did* (submitted a search) from *what merely
  crossed the network* (a proxy log line), and word reports honestly.
- Send one final summary per session to the existing OFL monitoring Telegram
  bot, reusing the transport the lab already runs.

## Non-goals

This system will **never**:

- log arbitrary keystrokes;
- record passwords, credentials, tokens, cookies, session or payment data;
- record unsent drafts (typed-then-deleted text);
- capture clipboard contents, take continuous screenshots, or record the screen;
- store browser credentials or extract ChatGPT/session secrets;
- intercept TLS to read encrypted traffic;
- replace or interfere with [OFLIT Child Time Limit](https://github.com/andrestr02/oflit-child-time-limit).

## Architecture

```text
Chrome managed extension (google.com / chatgpt.com)
   │  submitted content only, sensitive fields dropped in-page
   ▼
local agent  http://127.0.0.1:8791/event   (loopback only)
   │  validate → reject sensitive → attribute to active child session
   ▼
SQLite event store (/var/lib/oflit-activity, root:root 0640)
   │  session correlation via systemd-logind
   ▼
session aggregation → final report
   │  durable outbox (idempotent: one session → one report)
   ▼
existing OFL IT Lab Monitoring Telegram transport
```

Details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Supported sites

| Site | Captured | Evidence |
|------|----------|----------|
| `google.com` (`/search`) | the query, only once actually submitted (read from the results URL) | direct user action |
| `chatgpt.com` | the prompt, only on an explicit Send/Enter gesture | direct user action |

Browser history and Squid logs may be used as *secondary* evidence, labeled as
"visited resource" and "network observation" respectively — never as a claim
that the child opened a site.

## Installation

Agent (run as root on the target device):

```bash
sudo bash deploy/install.sh
# then review /etc/oflit-activity/agent.conf (MONITORED_USERS, INGEST_TOKEN)
```

Chrome extension: install via managed policy — see
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). The installer does **not** modify
Chrome, child-time-limit, Squid, or Tailscale.

## CLI

```bash
child-activity status            # live view of active child session(s)
child-activity report last       # render the most recent session summary
child-activity sessions          # list recent sessions
child-activity outbox            # Telegram delivery queue state
child-activity flush             # attempt delivery of pending reports now
child-activity purge             # apply retention now
```

## Privacy boundary

Only *submitted* content is ever recorded, and only from the two supported
sites. Sensitive fields are dropped twice — once in the browser
(`extension/common/redact.js`) and again in the agent (`model.reject_sensitive`).
The agent never trusts the username the extension claims; it binds every event
to the owner of the active graphical child session. Default retention is 14
days. Full details in [docs/PRIVACY.md](docs/PRIVACY.md) and
[docs/SECURITY.md](docs/SECURITY.md).

## Development & testing

Stdlib-only Python 3 agent; dependency-free MV3 extension. Run everything:

```bash
tests/run_tests.sh
```

See [docs/TESTING.md](docs/TESTING.md).

## Limitations

- ChatGPT prompt capture depends on the site's DOM; if it changes, the adapter
  fails safe (stops capturing) rather than capturing the wrong thing.
- Application monitoring reports processes *running* under the session, not
  which window is foreground (no reliable privilege-free Wayland foreground API).
- Squid network observation is coarse and device-level (the loopback proxy does
  not distinguish per-user traffic); it is off by default and clearly labeled.

## License

MIT — see [LICENSE](LICENSE).

# Security

## Threat model

| Threat | Mitigation |
|--------|------------|
| Child tampers with / disables the extension | Force-installed via Chrome managed policy; loss of the extension degrades gracefully (agent still records sessions/apps). The extension is not a trust boundary. |
| Child forges localhost HTTP events | Agent overrides the claimed username with the active-session owner; a child can at most inject events for *their own* session. Events without an active monitored session are rejected. |
| Child kills the agent process | `Restart=always`; on restart, open sessions are reconciled and pending reports (durable outbox) are re-delivered without duplication. |
| Child deletes / edits the logs | DB is `root:root 0640` in a `0750` root-owned dir; a child user cannot read, modify, or delete it. |
| Malformed / oversized payload | Size cap enforced before read; defensive JSON parse; unknown types/sources/sites rejected. |
| Symlink attack on state dir | State dir created `root:root 0750`; agent runs sandboxed with `ReadWritePaths` limited to it. |
| World-readable activity logs | Enforced `0640` on DB creation + install-time ownership; a unit test asserts non-world-readable. |
| Privilege escalation via the agent | `NoNewPrivileges`, empty `CapabilityBoundingSet`/`AmbientCapabilities`, `SystemCallFilter=@system-service`, `MemoryDenyWriteExecute`, restricted address families and namespaces. |
| Service running as root unnecessarily | Root is required only for the root-owned DB, cross-user process sampling, and reading the root-owned Squid log; everything else is stripped via systemd hardening. |
| Browser DOM drift (ChatGPT) | Adapter uses resilient selector fallbacks + `MutationObserver`; if it cannot find the composer/send control it simply stops capturing (fail-safe), never captures the wrong element. |
| Agent restart mid-session | Sessions are keyed by a stable id; `close_session`/`enqueue_report` are idempotent, so no duplicate reports. |
| Telegram/network outage | Reports persist in the outbox and retry; never blocks logout. |

## The ingest token is not a secret

`INGEST_TOKEN` (agent) / `token` (managed policy) is a cheap marker to filter
stray localhost traffic. It is **not** a security boundary against the child,
who owns the browser and can read the managed policy. The real integrity
boundary is server-side: authoritative user attribution, validation,
sensitive-field rejection, size limits, and the root-owned store.

## Loopback only

The ingestion server refuses to bind anything but a loopback address
(`ingest.IngestServer` raises otherwise). Nothing is exposed to the LAN,
Tailscale, or the internet.

## Secrets and Git

No Telegram token is ever stored in this project — it is read at send time from
the existing `/etc/ofl-ai-lab/telegram.env`. `.gitignore` blocks `*.env`,
`*.db`, real logs, and local config. The final-review checklist
([docs/TESTING.md](TESTING.md)) verifies the tree is clean before handoff.

## Systems this project must not break

`oflit-child-time-limit`, `/etc/child-time-*.conf`, PAM/GDM configuration,
Squid policy, Tailscale, and child quotas/access windows are **read-only** from
this project's perspective. The installer touches only `/opt`,
`/etc/oflit-activity`, `/var/lib/oflit-activity`, and its own systemd unit.

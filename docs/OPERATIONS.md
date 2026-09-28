# Operations

## Service

```bash
systemctl status oflit-activity-agent
systemctl restart oflit-activity-agent
journalctl -u oflit-activity-agent -f       # live logs (no content is logged)
```

The agent logs lifecycle events and errors to journald. It never logs captured
content.

## Everyday commands

```bash
child-activity status         # who is active now + recent activity
child-activity sessions       # recent sessions and their report state
child-activity report last    # full summary for the latest session
child-activity report <id>    # summary for a specific session id
child-activity outbox         # delivery queue: pending / retry / sent / failed
child-activity flush          # force a delivery attempt now
child-activity purge          # apply retention now
```

## Configuration

`/etc/oflit-activity/agent.conf` (root:root 0640). Change a value, then
`systemctl restart oflit-activity-agent`. Key settings:

- `MONITORED_USERS` — only these users are tracked.
- `RETENTION_DAYS` — event retention (default 14).
- `SQUID_ENABLED` — enable coarse network observation (default off).
- `TELEGRAM_ENABLED` / `TELEGRAM_ENV_PATH` — delivery over the existing OFL
  transport. Credentials are NOT stored here.

## Telegram delivery

Reports are queued in the durable outbox and delivered to the existing OFL IT
Lab Monitoring bot (same `telegram.env` as the fleet watcher / ops report). If
Telegram is unreachable, reports stay `pending`/`retry` and are re-sent
automatically; check with `child-activity outbox`.

## Health checks

```bash
curl -s http://127.0.0.1:8791/healthz     # -> {"status":"ok"}
ss -ltn | grep 8791                        # must show 127.0.0.1 only
```

## Backups

Back up `/var/lib/oflit-activity/activity.db` (contains submitted content —
treat as sensitive, keep off Git and off shared storage). Retention keeps it
bounded.

## Interaction with other systems

This agent is independent of child-time-limit, GDM, Squid, and Tailscale. If
the agent is stopped or fails, child login/logout and time limits are
unaffected.

# Deployment

Target device: `oflitlab-i3` (Ubuntu 26.04, GNOME/Wayland, Chrome, Squid,
systemd-logind). All commands run as root on the target.

## 1. Agent

```bash
git clone <repo> oflit-child-activity-monitor
cd oflit-child-activity-monitor
sudo bash deploy/install.sh
```

The installer is idempotent (safe to re-run for upgrades): it installs code to
`/opt/oflit-child-activity-monitor`, config to `/etc/oflit-activity/agent.conf`
(preserved if present), state to `/var/lib/oflit-activity` (DB preserved on
upgrade), links `child-activity`, installs+enables the systemd unit, and backs
up any existing unit. It does **not** touch Chrome, child-time-limit, Squid, or
Tailscale.

Then edit `/etc/oflit-activity/agent.conf`:

- `MONITORED_USERS=azzahra hudzaifah ibrohim`
- `INGEST_TOKEN=<pick a value>` (also set it in the Chrome policy below)

and `systemctl restart oflit-activity-agent`.

## 2. Chrome extension (managed)

The extension is force-installed via Chrome enterprise policy so the child
cannot remove it.

1. Package/host the `extension/` directory as an installable extension and note
   its extension ID (via the Chrome Web Store private listing, or a
   self-hosted `.crx` + `update_url`, per your Chrome management setup).
2. Copy `deploy/chrome-policy/oflit-activity-managed.json.template`, replace
   `__EXTENSION_ID__` and `__INGEST_TOKEN__`, and install it where Chrome reads
   managed policy on this host (e.g. `/etc/opt/chrome/policies/managed/` — note
   this directory does not exist yet on the target and must be created).
3. Restart Chrome. Confirm the extension is force-installed and that
   `endpoint`/`token` arrive via `chrome.storage.managed`.

Minimum permissions: the extension requests only the loopback host permission
and content scripts on `google.com/search*` and `chatgpt.com/*`.

## 3. Verify

```bash
systemctl status oflit-activity-agent
curl -s http://127.0.0.1:8791/healthz        # {"status":"ok"}
ss -ltn | grep 8791                           # 127.0.0.1 only
child-activity status
```

## Live acceptance

Use a **synthetic test child session** (never a real child's private data):

1. Log in as a monitored test user (graphical session).
2. Open Chrome; submit a synthetic Google query → `child-activity status` shows
   it as a submitted search.
3. Submit a synthetic ChatGPT prompt → appears as a submitted prompt.
4. Type but do NOT send a draft → it must NOT appear.
5. A password field → must NOT appear.
6. Log out (or let child-time-limit end the session) → one final Telegram
   report arrives; `child-activity outbox` shows `sent`.
7. Restart the agent mid-session → no duplicate report; pending reports persist.
8. Confirm `child-time-limit` is unaffected and Chrome remains usable.

If live ChatGPT automation is impractical, the deterministic extension tests
(`tests/extension`) stand in for steps 3–5.

## Upgrade

Re-run `sudo bash deploy/install.sh`. The DB and config are preserved.

## Rollback / uninstall

```bash
sudo bash deploy/uninstall.sh            # keep the activity DB + config
sudo bash deploy/uninstall.sh --purge    # also delete state + config
```

Remove the Chrome managed-policy file separately. A backed-up prior systemd
unit (`*.bak-*`) can be restored if needed.

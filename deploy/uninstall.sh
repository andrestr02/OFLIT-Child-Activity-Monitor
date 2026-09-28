#!/usr/bin/env bash
#
# uninstall.sh — remove the OFLIT Child Activity Monitor agent.
#
# By default the activity database is PRESERVED (rename with --purge to also
# delete stored events). Never touches child-time-limit, GDM, Squid, Tailscale,
# or the shared /etc/ofl-ai-lab/telegram.env.
#
#   sudo bash deploy/uninstall.sh            # keep data
#   sudo bash deploy/uninstall.sh --purge    # also delete /var/lib/oflit-activity
#
set -euo pipefail

PREFIX=/opt/oflit-child-activity-monitor
CONFIG_DIR=/etc/oflit-activity
STATE_DIR=/var/lib/oflit-activity
UNIT=/etc/systemd/system/oflit-activity-agent.service
PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1

if [[ "${EUID}" -ne 0 ]]; then
  echo "uninstall.sh must run as root" >&2
  exit 1
fi

echo "==> Stopping + disabling agent"
systemctl disable --now oflit-activity-agent.service 2>/dev/null || true
rm -f "${UNIT}"
systemctl daemon-reload

echo "==> Removing code + CLI symlink"
rm -f /usr/local/sbin/child-activity
rm -rf "${PREFIX}"

if [[ "${PURGE}" -eq 1 ]]; then
  echo "==> Purging state + config (requested)"
  rm -rf "${STATE_DIR}" "${CONFIG_DIR}"
else
  echo "==> Preserving ${STATE_DIR} and ${CONFIG_DIR} (use --purge to remove)"
fi

echo "Done. Chrome managed policy (if installed) must be removed separately."

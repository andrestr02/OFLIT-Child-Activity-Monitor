#!/usr/bin/env bash
#
# install.sh — idempotent installer for the OFLIT Child Activity Monitor agent.
#
# Installs the agent to /opt, config to /etc/oflit-activity, state to
# /var/lib/oflit-activity, and the systemd unit. Safe to re-run (upgrade):
# preserves the activity database and existing config. Never touches
# child-time-limit, GDM, Squid policy, or Tailscale.
#
# Run as root:  sudo bash deploy/install.sh
#
set -euo pipefail

PREFIX=/opt/oflit-child-activity-monitor
CONFIG_DIR=/etc/oflit-activity
STATE_DIR=/var/lib/oflit-activity
UNIT=/etc/systemd/system/oflit-activity-agent.service
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "install.sh must run as root" >&2
  exit 1
fi

echo "==> Installing agent code to ${PREFIX}"
install -d -m 0755 "${PREFIX}/bin" "${PREFIX}/oflit_activity" "${PREFIX}/docs"
install -m 0755 "${REPO_ROOT}/agent/bin/oflit-activity-agent" "${PREFIX}/bin/"
install -m 0755 "${REPO_ROOT}/agent/bin/child-activity" "${PREFIX}/bin/"
install -m 0644 "${REPO_ROOT}"/agent/oflit_activity/*.py "${PREFIX}/oflit_activity/"
install -m 0644 "${REPO_ROOT}"/docs/*.md "${PREFIX}/docs/" 2>/dev/null || true

echo "==> Linking CLI to /usr/local/sbin/child-activity"
ln -sf "${PREFIX}/bin/child-activity" /usr/local/sbin/child-activity

echo "==> Preparing state dir ${STATE_DIR} (root:root, 0750)"
install -d -m 0750 -o root -g root "${STATE_DIR}"

echo "==> Config ${CONFIG_DIR}"
install -d -m 0750 "${CONFIG_DIR}"
if [[ -f "${CONFIG_DIR}/agent.conf" ]]; then
  echo "    existing agent.conf preserved"
else
  install -m 0640 "${REPO_ROOT}/deploy/config/agent.conf.example" \
    "${CONFIG_DIR}/agent.conf"
  echo "    installed default agent.conf — review MONITORED_USERS / INGEST_TOKEN"
fi

echo "==> Backing up + installing systemd unit"
if [[ -f "${UNIT}" ]]; then
  cp -a "${UNIT}" "${UNIT}.bak-$(date +%Y%m%d-%H%M%S)"
fi
install -m 0644 "${REPO_ROOT}/systemd/oflit-activity-agent.service" "${UNIT}"

echo "==> Reloading systemd + enabling agent"
systemctl daemon-reload
systemctl enable oflit-activity-agent.service
systemctl restart oflit-activity-agent.service

echo
echo "Installed. Verify:"
echo "  systemctl status oflit-activity-agent"
echo "  child-activity status"
echo
echo "NOTE: The Chrome extension must be installed separately via managed"
echo "policy (see docs/DEPLOYMENT.md). This installer does NOT modify Chrome,"
echo "child-time-limit, Squid, or Tailscale."

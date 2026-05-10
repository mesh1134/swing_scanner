#!/usr/bin/env bash
set -euo pipefail

if ! id -u swing >/dev/null 2>&1; then
  echo "ERROR: Linux user 'swing' does not exist. Create it before installing units."
  exit 1
fi

if [[ ! -f /etc/swing-scanner.env ]]; then
  echo "ERROR: Missing /etc/swing-scanner.env (required by EnvironmentFile)."
  exit 1
fi

if [[ ! -f /opt/swing_scanner/watchlist.txt ]]; then
  echo "ERROR: Missing /opt/swing_scanner/watchlist.txt (required by ExecStart)."
  exit 1
fi

sudo chown root:root /etc/swing-scanner.env
sudo chmod 600 /etc/swing-scanner.env

sudo install -m 0644 deploy/systemd/swing-scanner.service /etc/systemd/system/swing-scanner.service
sudo install -m 0644 deploy/systemd/swing-scanner.timer /etc/systemd/system/swing-scanner.timer
sudo systemctl daemon-reload
sudo systemctl enable --now swing-scanner.timer
sudo systemctl list-timers swing-scanner.timer --no-pager

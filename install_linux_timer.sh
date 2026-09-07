#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

sudo tee /etc/systemd/system/jlc-autosign.service > /dev/null <<EOF
[Unit]
Description=JLC Auto Sign

[Service]
Type=oneshot
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/.venv/bin/python $PROJECT_DIR/main.py
EOF

sudo tee /etc/systemd/system/jlc-autosign.timer > /dev/null <<EOF
[Unit]
Description=Run JLC Auto Sign at a random time after midnight

[Timer]
OnCalendar=*-*-* 00:01:00
RandomizedDelaySec=59min
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now jlc-autosign.timer

#!/usr/bin/env bash
set -e

sudo systemctl disable --now jlc-autosign.timer
sudo rm -f /etc/systemd/system/jlc-autosign.service
sudo rm -f /etc/systemd/system/jlc-autosign.timer
sudo systemctl daemon-reload

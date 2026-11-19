#!/usr/bin/env bash
#
# restart-kanata.sh
#
# Validate ~/.config/kanata/config.kbd and restart the kanata user service.
# Kanata reads the config from that path directly, so no copying is needed.
#
# Usage: ~/.config/kanata/restart-kanata.sh
set -euo pipefail

CONFIG="$HOME/.config/kanata/config.kbd"

echo ">> Validating $CONFIG"
kanata --check --cfg "$CONFIG"

echo ">> Restarting kanata user service"
systemctl --user restart kanata

echo ">> Status"
systemctl --user --no-pager --lines=5 status kanata

#!/usr/bin/env bash
#
# setup-kanata.sh
#
# Grants the current user exactly the permissions kanata needs to run, without
# the blanket `input` group membership that Omarchy deliberately removed.
#
# WHY THIS EXISTS
# ---------------------------------------------------------------------------
# Omarchy's migration 1787865477.sh removes the user from the `input` group.
# Membership of `input` gives raw read/write access to every /dev/input/event*
# node, so any process running as the user could capture keystrokes (keylogging)
# and synthesize input. Omarchy considers that a needlessly broad grant and
# drops it unless xpadneo-dkms or ydotool is installed.
#
# kanata legitimately needs keyboard access, but it is not on Omarchy's keep
# list, so upgrading Omarchy strips the group and kanata fails with:
#   "No keyboard devices were found."
#
# Rather than re-join `input` (fragile: re-stripped on any fresh install, and it
# reopens the keylogging risk Omarchy closed), this script creates a dedicated
# `kanata` group and points a udev rule at it. Omarchy never touches a group
# named `kanata` and never overwrites /etc/udev/rules.d/, so this survives
# future upgrades AND fresh installs.
#
# USAGE
# ---------------------------------------------------------------------------
#   bash ~/.config/kanata/setup-kanata.sh
#
# Idempotent: safe to re-run. Then log out and back in so the new group applies
# to your session, and enable/start the service:
#   systemctl --user enable --now kanata
#
# SET -euo pipefail
set -euo pipefail

GROUP="kanata"
RULE_FILE="/etc/udev/rules.d/99-kanata.rules"
USER_SERVICE="$HOME/.config/systemd/user/kanata.service"

die() { echo "ERROR: $*" >&2; exit 1; }

# Raise privileges only for the few root steps, not the whole script.
run_root() {
  if [[ $EUID -eq 0 ]]; then
    "$@"
  elif command -v sudo &>/dev/null; then
    sudo "$@"
  elif command -v pkexec &>/dev/null; then
    pkexec "$@"
  else
    die "run this script as root, or install sudo/pkexec"
  fi
}

echo ">> Creating group '$GROUP'"
run_root groupadd -f "$GROUP"

echo ">> Installing udev rule: $RULE_FILE"
run_root tee "$RULE_FILE" >/dev/null <<EOF
# Grant only kanata's group read access to physical keyboards, and write access
# to /dev/uinput so it can create the remapped virtual device.
KERNEL=="event*", SUBSYSTEM=="input", ENV{ID_INPUT_KEYBOARD}=="1", GROUP="kanata", MODE="0660"
KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="kanata", MODE="0660", OPTIONS+="static_node=uinput"
EOF

echo ">> Reloading udev rules"
run_root udevadm control --reload-rules
run_root udevadm trigger --subsystem-match=input

echo ">> Adding current user to group '$GROUP'"
if id -nG | grep -qw "$GROUP"; then
  echo "   (already a member)"
else
  run_root usermod -aG "$GROUP" "$USER"
  echo "   Added. Log out and back in for it to take effect."
fi

echo ">> Enabling kanata user service"
if [[ -f $USER_SERVICE ]]; then
  systemctl --user enable kanata &>/dev/null || true
else
  echo "   No user service found at $USER_SERVICE (skipping)."
fi

echo
echo "Done. Next steps:"
echo "  1. Log out and back in (group membership applies to new sessions only)."
echo "  2. Start kanata:   systemctl --user start kanata"
echo "  3. Verify:         systemctl --user status kanata"
echo "  4. Sanity check:   kanata --list   # should list your keyboard"
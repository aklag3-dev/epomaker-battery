#!/usr/bin/env bash
# EPOMAKER Battery installer — remove everything this toolkit installed.
# Use --with-udev to also remove the system udev rules (asks for password).
set -euo pipefail

DEST="$HOME/.local/share/epomaker-battery"
AUTOSTART="$HOME/.config/autostart"
WITH_UDEV=0
[ "${1:-}" = "--with-udev" ] && WITH_UDEV=1

echo "== EPOMAKER Battery uninstaller =="

# Stop running applet/watcher (only ones launched from DEST)
for script in battery-tray.py battery-watch.py; do
  pids=$(pgrep -u "$(id -u)" -f "$DEST/$script" || true)
  [ -n "$pids" ] && kill $pids 2>/dev/null || true
done
echo "[1/4] Stopped running applet/watcher"

# Autostart entries (only ours, verified by content)
for name in epomaker-battery-tray.desktop epomaker-battery-watch.desktop; do
  f="$AUTOSTART/$name"
  if [ -f "$f" ] && grep -q "epomaker-battery" "$f"; then rm "$f"; fi
done
echo "[2/4] Removed autostart entries"

# Data dir + installed logo icons
rm -rf "$DEST"
for size in 16x16 24x24 32x32 48x48; do
  rm -f "$HOME/.local/share/icons/hicolor/$size/apps/epomaker-applet.png"
done
echo "[3/4] Removed app files and icon"

if [ "$WITH_UDEV" = 1 ]; then
  RULE_TOOL=""
  if [ "$(id -u)" -eq 0 ]; then
    rm -f /etc/udev/rules.d/99-epomaker.rules /etc/udev/rules.d/98-bt-power.rules
    udevadm control --reload-rules 2>/dev/null || true
    udevadm trigger --action=add 2>/dev/null || true
    echo "[4/4] Removed system udev rules"
  else
    sudo -n true 2>/dev/null && RULE_TOOL="sudo"
    [ -z "$RULE_TOOL" ] && command -v pkexec >/dev/null 2>&1 && RULE_TOOL="pkexec"
    if [ -n "$RULE_TOOL" ]; then
      $RULE_TOOL rm -f /etc/udev/rules.d/99-epomaker.rules /etc/udev/rules.d/98-bt-power.rules
      $RULE_TOOL udevadm control --reload-rules
      $RULE_TOOL udevadm trigger --action=add
      echo "[4/4] Removed system udev rules"
    else
      echo "[4/4] Could not get root — remove rules manually:"
      echo "        sudo rm /etc/udev/rules.d/9*-epomaker.rules /etc/udev/rules.d/98-bt-power.rules && sudo udevadm control --reload-rules"
    fi
  fi
else
  echo "[4/4] Left system udev rules untouched (add --with-udev to remove them too)"
fi

echo
echo "Note: if you installed via the .deb package instead, run: sudo apt purge epomaker-battery"

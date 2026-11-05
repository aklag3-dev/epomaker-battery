#!/usr/bin/env bash
# EPOMAKER Battery — user installer (no root needed for the applet itself).
# Copies the applet into ~/.local/share/epomaker-battery and registers it to
# start at login via XDG autostart. Optionally installs udev rules (root)
# if you also want to use the VIA keyboard configurator in a browser.
#
# Usage:
#   ./install.sh                 # applet only, zero sudo
#   ./install.sh --with-udev     # also install udev rules (asks for password)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
DEST="$HOME/.local/share/epomaker-battery"
AUTOSTART="$HOME/.config/autostart"
WITH_UDEV=0
[ "${1:-}" = "--with-udev" ] && WITH_UDEV=1

echo "== EPOMAKER Battery installer =="
echo

# 1. Files ------------------------------------------------------------
mkdir -p "$DEST"
cp "$SCRIPT_DIR/app/battery-tray.py" "$SCRIPT_DIR/app/battery-watch.py" "$DEST/"
mkdir -p "$DEST/assets"
cp -r "$SCRIPT_DIR/app/assets/." "$DEST/assets/"
chmod +x "$DEST"/*.py
echo "[1/4] Installed app files into $DEST"

# 2. Autostart --------------------------------------------------------
mkdir -p "$AUTOSTART"
for name in tray watch; do
  script="battery-tray.py"; [ "$name" = watch ] && script="battery-watch.py"
  cat > "$AUTOSTART/epomaker-battery-$name.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=EPOMAKER Battery ($name)
Comment=Keyboard battery tray applet and notifications
Exec=/usr/bin/env python3 $DEST/$script
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
done
echo "[2/4] Registered to start at login (log out/in to activate)"

# 3. Dependency check -------------------------------------------------
warn() { echo "        ! $1"; }
command -v upower >/dev/null || warn "upower not found — install it:
          apt install upower   |   dnf install upower   |   pacman -S upower"
if ! python3 -c "import gi" 2>/dev/null; then
  warn "python3-gi (GTK bindings) missing — the tools need it:
          apt install python3-gi   |   dnf install python3-gi   |   pacman -S python-gobject"
elif ! python3 -c "
import gi
gi.require_version('Gtk','3.0')
gi.require_version('AppIndicator3','0.1')
" 2>/dev/null && ! python3 -c "
import gi
gi.require_version('Gtk','3.0')
gi.require_version('AyatanaAppIndicator3','0.1')
" 2>/dev/null; then
  warn "Tray icon support (AppIndicator) missing — install ONE of:
          apt install gir1.2-ayatanaappindicator3-0.1
          apt install gir1.2-appindicator3-0.1
          (GNOME desktops also need the 'AppIndicator and KStatusNotifierItem' shell extension)"
fi
echo "[3/4] Dependency check done (warnings above are fixable; battery watcher needs python3-gi + upower)"

# 4. Optional udev rules ----------------------------------------------
# Privilege helper: direct when already root, else sudo (non-interactive ok)
# or pkexec (GUI prompt). Containers/minimal images often lack sudo entirely.
RULE_TOOL=""
if [ "$(id -u)" -eq 0 ]; then
  RULE_TOOL=""  # run commands directly
  AS_ROOT=1
elif sudo -n true 2>/dev/null; then
  RULE_TOOL="sudo"; AS_ROOT=0
elif command -v pkexec >/dev/null 2>&1; then
  RULE_TOOL="pkexec"; AS_ROOT=0
else
  AS_ROOT=0
fi

if [ "$WITH_UDEV" = 1 ]; then
  if ! command -v udevadm >/dev/null 2>&1 && [ ! -d /etc/udev ]; then
    warn "This system has no udev (headless container/minimal image?) — skipping rules."
    echo "[4/4] Skipped udev rules (not applicable here)"
  elif [ "$AS_ROOT" = 1 ]; then
    mkdir -p /etc/udev/rules.d
    cp "$SCRIPT_DIR/rules/99-epomaker.rules" "$SCRIPT_DIR/rules/98-bt-power.rules" /etc/udev/rules.d/
    udevadm control --reload-rules 2>/dev/null
    udevadm trigger --action=add 2>/dev/null || true
    echo "[4/4] udev rules installed (VIA configurator access + Bluetooth sleep fix)"
  elif [ -n "$RULE_TOOL" ]; then
    $RULE_TOOL cp "$SCRIPT_DIR/rules/99-epomaker.rules" "$SCRIPT_DIR/rules/98-bt-power.rules" /etc/udev/rules.d/
    $RULE_TOOL udevadm control --reload-rules
    $RULE_TOOL udevadm trigger --action=add
    echo "[4/4] udev rules installed (VIA configurator access + Bluetooth sleep fix)"
  else
    warn "No sudo/pkexec available — skip for now, run later:
          sudo cp $SCRIPT_DIR/rules/*.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger --action=add"
  fi
else
  echo "[4/4] Skipped udev rules (only needed for the VIA web configurator; the battery applet does NOT need them)"
fi

# 5. Start right now (only inside a graphical session — headless SSH/CI
#    containers would core-dump on the tray icon) ----------------------
if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  for script in battery-tray.py battery-watch.py; do
    pgrep -u "$(id -u)" -f "$DEST/$script" >/dev/null 2>&1 || \
      nohup python3 "$DEST/$script" >/dev/null 2>&1 &
  done
else
  echo "Note: no graphical session detected — the applet will start at your next login."
fi
echo
echo "Done — the battery icon should appear in your taskbar within ~30 seconds."
echo "Your keyboard must be PAIRED over Bluetooth for its battery to show up."
echo "Remove everything later with: ./uninstall.sh"

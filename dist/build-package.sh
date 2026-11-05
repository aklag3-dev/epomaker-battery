#!/usr/bin/env bash
# Build shareable EPOMAKER Battery packages from the canonical sources:
#   ../battery/*.py + assets, ../setup/*.rules, install.sh/uninstall.sh/README-user.md
# Outputs into dist/out/:
#   epomaker-battery_1.0.1-1_all.deb        (apt/double-click, Ubuntu/Debian/Mint)
#   epomaker-battery-1.0.1.tar.gz           (./install.sh, any distro)
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

VERSION=1.0.1
PKG=epomaker-battery
OUT=out
ROOT="$(pwd)/.."

command -v dpkg-deb >/dev/null || { echo "dpkg-deb required (dpkg package)"; exit 1; }
rm -rf "$OUT/build" "$OUT/$PKG-$VERSION" "$OUT/$PKG.deb" "$OUT/${PKG}_${VERSION}-1_all.deb" "$OUT/${PKG}-${VERSION}.tar.gz"
mkdir -p "$OUT"

# ---------- shared app payload ----------
APPFILES="$OUT/build/appfiles"
mkdir -p "$APPFILES/assets"
cp "$ROOT/battery/battery-tray.py" "$ROOT/battery/battery-watch.py" "$APPFILES/"
cp "$ROOT/battery/assets/epomaker-applet.png" "$APPFILES/assets/"
cp "$ROOT/setup/99-epomaker.rules" "$ROOT/setup/98-bt-power.rules" "$OUT/build/"

# ---------- .deb ----------
DEB="$OUT/build/deb"
mkdir -p "$DEB/DEBIAN" \
         "$DEB/usr/share/epomaker-battery/assets" \
         "$DEB/etc/udev/rules.d" \
         "$DEB/etc/xdg/autostart"
cp "$APPFILES/battery-tray.py" "$APPFILES/battery-watch.py" "$DEB/usr/share/epomaker-battery/"
cp "$APPFILES/assets/epomaker-applet.png" "$DEB/usr/share/epomaker-battery/assets/"
chmod 755 "$DEB/usr/share/epomaker-battery"/*.py
cp "$OUT/build/99-epomaker.rules" "$OUT/build/98-bt-power.rules" "$DEB/etc/udev/rules.d/"

for pair in "tray:battery-tray.py" "watch:battery-watch.py"; do
  name="${pair%%:*}"; script="${pair##*:}"
  cat > "$DEB/etc/xdg/autostart/epomaker-battery-$name.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=EPOMAKER Battery ($name)
Comment=Keyboard battery tray applet and notifications
Exec=/usr/bin/env python3 /usr/share/epomaker-battery/$script
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
done

cat > "$DEB/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION-1
Architecture: all
Maintainer: My-AI-Workspace <maintainer@localhost>
Installed-Size: $(du -sk "$DEB" | cut -f1)
Depends: python3, upower, python3-gi, gir1.2-ayatanaappindicator3-0.1 | gir1.2-appindicator3-0.1
Section: misc
Priority: optional
Description: Bluetooth keyboard battery tray applet and notifications
 Taskbar applet showing live battery percentage of Bluetooth keyboards
 (EPOMAKER/AULA and any device with a GATT Battery Service), with
 low-battery/charging notifications, automatic reconnect for dropped
 links, and udev rules for the VIA web configurator plus a Bluetooth
 adapter autosuspend fix. Autostarts at login via XDG.
EOF

cat > "$DEB/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
    udevadm trigger --action=add || true
fi
EOF
cat > "$DEB/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
fi
EOF
chmod 755 "$DEB/DEBIAN/postinst" "$DEB/DEBIAN/postrm"

dpkg-deb --build --root-owner-group "$DEB" "$OUT/${PKG}_${VERSION}-1_all.deb"

# ---------- tar.gz ----------
TAR="$OUT/$PKG-$VERSION"
mkdir -p "$TAR/app/assets" "$TAR/rules"
cp "$APPFILES/battery-tray.py" "$APPFILES/battery-watch.py" "$TAR/app/"
cp "$APPFILES/assets/epomaker-applet.png" "$TAR/app/assets/"
cp "$OUT/build/99-epomaker.rules" "$OUT/build/98-bt-power.rules" "$TAR/rules/"
cp install.sh uninstall.sh README-user.md "$TAR/"
chmod +x "$TAR/install.sh" "$TAR/uninstall.sh" "$TAR/app"/*.py
tar czf "$OUT/${PKG}-${VERSION}.tar.gz" -C "$OUT" "$PKG-$VERSION"
rm -rf "$TAR"

echo
echo "Built:"
ls -la "$OUT/${PKG}_${VERSION}-1_all.deb" "$OUT/${PKG}-${VERSION}.tar.gz"

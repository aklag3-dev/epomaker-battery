#!/usr/bin/env bash
# EPOMAKER keyboard setup — installs udev rules (+ optional kernel quirk).
# Run from anywhere; paths are resolved relative to this script.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

echo "=== EPOMAKER F75 Ultra / TH33 setup kit ==="
echo
echo "[1/2] udev rules (/etc/udev/rules.d/99-epomaker.rules + 98-bt-power.rules)"
echo "      99: grants non-root access to /dev/hidraw* for VIA/WebHID config."
echo "          REQUIRED — this is why the online configurator fails today."
echo "      98: disables USB autosuspend on the Bluetooth adapter — stops the"
echo "          'keyboard slept and keys stop arriving' BLE stale-link problem."
read -rp "      Install now? [Y/n] " ans
case "${ans:-Y}" in
  [Yy]*)
    sudo cp setup/99-epomaker.rules /etc/udev/rules.d/99-epomaker.rules
    sudo cp setup/98-bt-power.rules /etc/udev/rules.d/98-bt-power.rules
    sudo udevadm control --reload-rules
    sudo udevadm trigger --action=add   # ACTION=="add" rules only fire on add-events
    echo "      Installed. Unplug/replug your dongles (or reboot) so nodes get new permissions."
    echo "      Verify BT fix: cat /sys/bus/usb/devices/*/power/autosuspend  (adapter should show -1)"
    ;;
  *) echo "      Skipped." ;;
esac

echo
echo "[2/2] usbhid idle-drop quirk (/etc/modprobe.d/epomaker-usbhid.conf)"
echo "      Fixes F75 Ultra 2.4G dongle dropping after ~1min idle on kernel 6.8."
echo "      OPTIONAL — skip if your dongle never sleeps/drops."
read -rp "      Install now? [y/N] " ans
case "${ans:-N}" in
  [Yy]*)
    sudo cp setup/epomaker-usbhid.conf /etc/modprobe.d/epomaker-usbhid.conf
    echo "      Installed. Takes effect on next reboot."
    echo "      Verify later with: cat /sys/module/usbhid/parameters/quirks"
    ;;
  *) echo "      Skipped (can add any time: sudo cp setup/epomaker-usbhid.conf /etc/modprobe.d/)" ;;
esac

echo
echo "=== Done. Check permissions:  ./check.sh after-setup  (compare hidraw modes) ==="

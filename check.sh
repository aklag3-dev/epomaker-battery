#!/usr/bin/env bash
# State snapshot for the keyboard checklist. Usage:
#   ./check.sh baseline          # now
#   ./check.sh f75-wired         # after plugging F75 Ultra via USB-C
#   ./check.sh th33-wired        # after plugging TH33 via USB-C
#   ./check.sh dongle-test       # after unplugging one dongle
#   ./check.sh bt-f75            # after pairing F75 Ultra over Bluetooth
#   ./check.sh bt-th33           # after pairing TH33 over Bluetooth
# Output: printed + saved to checks/<timestamp>-<label>.txt
set -u
label="${1:-state}"
dir="$(dirname "$(readlink -f "$0")")/checks"
mkdir -p "$dir"
out="$dir/$(date +%Y%m%d-%H%M%S)-$label.txt"
exec > >(tee "$out") 2>&1

echo "# snapshot: $label  @  $(date '+%F %T')"

echo; echo "## lsusb — keyboard vendors"
lsusb | grep -iE '0c45|36b0|258a|fffe|microdia|rdmct|aula|epomaker' || echo "(no keyboard devices on USB bus)"

echo; echo "## hidraw nodes (path [perm owner:group] product name)"
found=0
for h in /dev/hidraw*; do
  [ -e "$h" ] || continue
  found=1
  perm=$(stat -c '%A %U:%G' "$h")
  info=$(grep -hE '^(HID_ID|HID_NAME)=' "/sys/class/hidraw/$(basename "$h")/device/uevent" 2>/dev/null | sed 's/^[A-Z_]*=//' | paste -sd' ' -)
  echo "$h  [$perm]  $info"
done
[ $found -eq 1 ] || echo "(no hidraw nodes)"

echo; echo "## power_supply entries (battery from BT HID appears here)"
for p in /sys/class/power_supply/*; do
  [ -d "$p" ] || continue
  echo "$(basename "$p"): type=$(cat "$p/type" 2>/dev/null) capacity=$(cat "$p/capacity" 2>/dev/null)% status=$(cat "$p/status" 2>/dev/null) model=$(cat "$p/model_name" 2>/dev/null)"
done

echo; echo "## UPower devices"
upower -e 2>/dev/null | grep -vi 'display' || true
for d in $(upower -e 2>/dev/null | grep -iv 'display'); do
  echo "-- $d"; upower -i "$d" 2>/dev/null | grep -E 'state|percentage|vendor|model|native|is-present' | sed 's/^/   /'
done

echo; echo "## Bluetooth devices + Battery Service (GATT 0x180F) presence"
if command -v bluetoothctl >/dev/null; then
  devs=$(bluetoothctl devices 2>/dev/null | awk '/^Device /{print $2" "$3" "$4}')
  [ -n "$devs" ] && echo "$devs" | sed 's/^/   paired-known: /' || echo "   (none)"
  for mac in $(bluetoothctl devices 2>/dev/null | awk '/^Device /{print $2}'); do
    blk=$(timeout 8 bluetoothctl info "$mac" 2>/dev/null)
    name=$(echo "$blk" | awk -F': ' '/Alias/{print $2}')
    bas=$(echo "$blk" | grep -icE '0000180f|battery')
    bat=$(echo "$blk" | grep -iE 'Battery Percentage' || true)
    echo "   $mac ${name:-?}: BATTERY_GATT=$([ "$bas" -gt 0 ] && echo YES || echo no) $bat"
  done
else
  echo "   (bluetoothctl not installed)"
fi

echo; echo "# saved: $out"

> **Appendix note (sanitized for publication, 2026-11-05).** This is the original internal investigation write-up behind EPOMAKER Battery. Device MAC addresses are replaced with `AA:BB:CC:DD:EE:*` placeholders and local home paths generalized; hardware model names, USB IDs and links to EPOMAKER's public firmware repositories are kept because they are the useful part. Companion artifacts referenced below (raw `check.sh` snapshots, vendored firmware sources, the experimental `th33-via.py` CLI) are intentionally not published.

# VIA Configuration — F75 Ultra + TH33 (Linux)

Settings are written to the keyboard's EEPROM: configure **wired**, use over 2.4G/BT anywhere after.
VIA = key remap, layers, macros, tap-hold, RGB, encoder/knob behavior.

## One-time prerequisites
1. Run `./install-setup.sh` (installs `setup/99-epomaker.rules`) — without it, Chrome/Edge cannot open `/dev/hidraw*` and VIA silently fails to see the keyboard.
2. Replug the keyboard, switch it to **USB-C wired** mode.
3. Use **Chrome / Edge / Opera** (WebHID; Firefox/Safari won't work).

## Connecting in VIA
1. Open <https://usevia.app>
2. Settings tab → enable **Display the language menu**? not needed → main thing: under "Advanced Mode" you'll land on the Design/Keycap tabs.
3. The keyboard should auto-appear. If not: replug wired, check udev rule installed (`ls -l /dev/hidraw*` → `crw-rw-rw-`).
4. **Important for these boards:** in Settings, "Use V2 Definitions" must be **OFF** (vendor JSONs are V1 format).

## Loading the vendor definitions (local copies — already downloaded)
The boards don't auto-load their layout, so upload the vendor JSON:
- **F75 Ultra:** `vendor/si_2635_via_v1.06_20251218.json`
- **TH33:** `vendor/EPOMAKER-TH33.json`

Upload via: Design tab (or Settings → "Custom definitions" → drag JSON / select file).
Source of truth: `github.com/Epomaker/x-Aula-F75-Ultra` and `github.com/Epomaker/th33` — re-download from there if firmware updates ship new JSONs.

## What works where (board truth)
| | F75 Ultra | TH33 |
|---|---|---|
| VIA over USB-C | ✅ (VID `FFFE:00A9`) | ✅ (VID `36B0:30AA`) |
| VIA over 2.4G/BT | ❌ structurally impossible — dongle is a dumb HID relay | ❌ same |
| Knob/encoder | VIA encoder tab (2 functions per layer) | VIA (has encoder) |
| Battery readout | custom keycode `BT_VOL` = **Fn+B** shows LED bar | **Fn+PAUSE** shows LED bar |
| Macros | VIA key-sequencer only — for OS-level scripting see keyd/input-remapper | same |

## Notes
- **Fn+B battery** (Ultra): 10 LEDs light = tens-of-%, red <30%, green ≥30%. Firmware source calls it `BT_VOL` (query voltage); the value stays inside the keyboard — see `OPTIONS.md` battery section.
- Per-app profiles and shell-command macros are NOT VIA's job on Linux — pair VIA with `keyd` (system-wide layers/tap-dance) or `input-remapper` (GUI, per-app, macros) for host-side scripting.

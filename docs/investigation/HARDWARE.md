> **Appendix note (sanitized for publication, 2026-11-05).** This is the original internal investigation write-up behind EPOMAKER Battery. Device MAC addresses are replaced with `AA:BB:CC:DD:EE:*` placeholders and local home paths generalized; hardware model names, USB IDs and links to EPOMAKER's public firmware repositories are kept because they are the useful part. Companion artifacts referenced below (raw `check.sh` snapshots, vendored firmware sources, the experimental `th33-via.py` CLI) are intentionally not published.

# Keyboard Tooling Investigation — Local Hardware Audit

Date: 2026-11-03 · Machine: ThinkPad P50, Linux (session dir `~/workspace`)
Goal: battery readout + key remap + macros/scripts for EPOMAKER x AULA F75 Ultra and EPOMAKER TH33, without relying on the vendor web driver.

## F75 Ultra (via 2.4GHz dongle — current mode)

- USB: `Bus 001 Device 027: ID 0c45:fefe Microdia F75 Ultra Dongle`
- HID interfaces (`/sys/bus/hid/devices/0003:0C45:FEFE.000B..000F`) — 5 collections, exposed as:
  - `F75 Ultra Dongle` (generic ×2 — likely vendor/config + mouse), `... Keyboard`, `... Consumer Control`, `... System Control`, `... System Multi Axis` (= rotary knob)
- hidraw endpoints: `/dev/hidraw10`–`/dev/hidraw14` (a userspace tool can target these; udev rule needed for non-root access)
- **Battery: NOT exposed** — `/sys/class/power_supply/` shows only laptop `BAT0` + `AC`. Dongle HID has no battery power_supply entry.
- Not currently paired over Bluetooth.

## TH33 candidate dongle

- USB: `Bus 001 Device 026: ID 36b0:3002 RDMCTMZT Wireless 2.4G Dongle` — 3 HID interfaces (`...0008/0009/000A`), names: Keyboard / Mouse / Consumer Control / System Control; `/dev/hidraw7`–`hidraw9`
- **RESOLVED (2026-11-03):** this IS the TH33's 2.4G receiver. Official source `github.com/Epomaker/th33` declares `"manufacturer": "RDMCTMZT"`, VID `0x36B0` (wired PID `0x30AA`); `36B0:3002` is the shared RDR-family dongle PID. TH33 is a **real QMK board** (ESSEMI ES32FS026 Cortex-M0 + separate "91680" radio over SPI), VIA-supported wired-only.
- Battery: none exposed either — and firmware analysis says **none will be**: battery value only goes one-way to the closed radio module (`USER_BATTERY_DATA 0x10` over SPI), no GATT BAS expected. Readout = `FN+PAUSE` (number keys 0–9 light as %). Confirm with `bluetoothctl info | grep -i 180f`.

## Other devices present (not targets)

- Logitech Bolt receiver `046d:c548` (mouse), Razer Atheris `1532:0062`, ProtoArc XK01 (paired BT, MAC `AA:BB:CC:DD:EE:03`).

## Toolchain status on this machine

- `python3` ✔ · `upower` ✔
- `hid` (hidapi python) ✘ · `input-remapper` ✘ · `key-mapper` ✘ · `evremap` ✘ · `vial` ✘ · `hidrd-convert` ✘
- No passwordless sudo → report-descriptor dump (`/sys/kernel/debug/hid/*/report_descriptor`) requires interactive sudo later.

## Open questions for the research phase

1. Can the vendor web driver talk through the 2.4G dongle (0c45:fefe) or only wired? Which device do WebHID filters request?
2. Does the keyboard report battery over BLE Battery Service when used in Bluetooth mode?
3. Prior art: RE'd protocol repos for AULA F75 family / EPOMAKER; OS-level remappers for remap/macro; tray battery monitors.

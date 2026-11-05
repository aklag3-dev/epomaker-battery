# EPOMAKER Battery — tray applet + battery watcher

Small user-space tools for Linux that monitor Bluetooth keyboard/mouse
battery levels over UPower D-Bus. Built for EPOMAKER/AULA keyboards
(F75 Ultra, TH33) but they show **any** battery-reporting Bluetooth keyboard
or mouse UPower can see (Keychron, Logitech, ProtoArc, ...).

The applet icon is the bundled **EPOMAKER wordmark logo** (`assets/epomaker-applet.png`,
auto-installed into `~/.local/share/icons/hicolor` at {16x16,24x24,32x32,48x48}/apps
on start — it deliberately never writes a user `index.theme`, which would break
the system hicolor theme). The icon switches to the themed
`battery-warning`/`battery-caution` glyphs at ≤20%/≤10% and to a charging glyph
when a device reports `state=charging`.

## What it does

- Detects UPower keyboard/mouse devices by:
  - D-Bus device `Type == 5` (mouse) or `Type == 6` (keyboard), **or**
  - model/native-path matching `F75`, `EPOMAKER`, `AULA`, `TH33`, `Keychron`, `Nuphy`,
    `Logitech`, `Razer`, `Steelseries`, `Corsair`, `Zidoo`, `ProtoArc`, or generic `keyboard|mouse`.
- Strips the BLE profile-slot suffix from names (`TH33-1` → `TH33`,
  `AULA F75 Ultra 1` → `AULA F75 Ultra`; product names ending in a number like
  `MX Master 3` are protected).
- Subscribes to D-Bus `PropertiesChanged` if `python3-gi` is available; otherwise polls `upower -e` every 60 seconds.
- Prints model, MAC, percentage, and reading age; `state` is hidden in menus/tooltips when it is the useless `unknown` (BLE Battery Service reports percentage only).
- Marks disappeared devices as `OFFLINE` (keyboards go to sleep and vanish from UPower; it does not crash).
- Sends desktop notifications when:
  - battery drops to the configured threshold (default 20%) — once per discharge episode,
  - battery drops to 10% or below — re-notifies,
  - charging begins or ends.
  - notifications replace each other (synchronous hint) + 15-min refire cooldown, so they never stack.

## Files

| File | Purpose |
|------|---------|
| `battery-tray.py` | **Taskbar applet (MATE/Ayatana)** — EPOMAKER logo + live % label + per-device menu incl. **transport readout** (`via [Bluetooth + 2.4G dongle]` etc.). Run this for the visual readout. |
| `battery-watch.py` | Daemon: notifications (low battery, charging) via D-Bus events. |
| `battery-watch.sh` | Pure-shell fallback if `python3-gi` is missing. |
| `epomaker-battery-tray.service` | User unit for the tray applet. |
| `epomaker-battery.service` | User unit for the notification daemon. |
| `assets/epomaker-applet.png` | Brand logo installed into the icon theme. |
| `README.md` | This file. |

## Enable everything (run once)

```bash
mkdir -p ~/.config/systemd/user
cd ~/My-AI-Workspace/projects/keyboard-tooling/battery
ln -sf $PWD/epomaker-battery.service $PWD/epomaker-battery-tray.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now epomaker-battery.service epomaker-battery-tray.service
```

A keyboard-battery icon with a live `%` label appears in the MATE notification area; click it for the per-keyboard menu. The daemon adds desktop notifications at ≤20% / ≤10% / charging changes.

## Requirements

- Linux with UPower D-Bus service running (Ubuntu 24.04 ships this).
- `python3` and optionally `python3-gi` for D-Bus signal subscription.
- `notify-send` for desktop notifications (from `libnotify-bin`).

This machine already has everything required:

```text
$ python3 -c "import gi; from gi.repository import Gio, GLib; print('gi ok')"
gi ok
$ which upower notify-send
/usr/bin/upower
/usr/bin/notify-send
```

## Quick test (right now)

With an AULA F75 Ultra connected at 75%, run:

```bash
cd ~/epomaker-battery/battery
python3 battery-watch.py --once
```

Expected output (expected shape):

```text
Keyboard battery snapshot (2026-11-04T11:20:46+00:00)
  AULA F75 Ultra 1  MAC=AA:BB:CC:DD:EE:01  75%  state=unknown  updated 0s ago
```

If `python3-gi` is not installed, use the shell fallback:

```bash
bash battery-watch.sh --once
```

## Run as a daemon

### Option A: user systemd service (recommended)

1. Link or copy the unit into your user systemd directory:

   ```bash
   mkdir -p ~/.config/systemd/user
   ln -sf ~/epomaker-battery/battery/epomaker-battery.service \
          ~/.config/systemd/user/epomaker-battery.service
   systemctl --user daemon-reload
   ```

2. Start and enable autostart:

   ```bash
   systemctl --user start epomaker-battery.service
   systemctl --user enable epomaker-battery.service
   ```

3. Check status:

   ```bash
   systemctl --user status epomaker-battery.service
   journalctl --user -u epomaker-battery.service -f
   ```

### Option B: run manually in a terminal

```bash
python3 battery-watch.py --debug
```

### Option C: cron snapshot

```bash
python3 battery-watch.py --once >> ~/.local/share/epomaker-battery.log 2>&1
```

## Verified output

Captured on a ThinkPad P50 (Ubuntu 24.04, kernel 6.8) with the
AULA x EPOMAKER F75 Ultra connected over Bluetooth:

```text
$ python3 battery-watch.py --once
Keyboard battery snapshot (2026-11-04T11:36:33.176835+00:00)
  AULA F75 Ultra 1  MAC=AA:BB:CC:DD:EE:01  75%  state=unknown  updated 6047s ago
```

UPower source data:

```text
$ upower -i /org/freedesktop/UPower/devices/keyboard_dev_AA_BB_CC_DD_EE_01
  native-path:          /org/bluez/hci0/dev_AA_BB_CC_DD_EE_01
  model:                AULA F75 Ultra 1
  serial:               AA:BB:CC:DD:EE:01
    present:             yes
    state:               unknown
    percentage:          75%
```

## Notes

- `--threshold N` changes the low-battery notification level.
- By default the applet and watcher show **any** battery-reporting keyboard or
  mouse UPower can see (Keychron, NuPhy, Logitech, ProtoArc, …). Add
  `--epomaker-only` to either script (or to the ExecStart lines in the systemd
  units via `systemctl --user edit`) to restrict to EPOMAKER/AULA/TH33/F75 devices.
- The keyboard may disappear from UPower when its radio sleeps; the watcher
treats that as offline and re-detects it when it wakes.
- **Auto-reconnect:** when a paired keyboard's Bluetooth link goes stale (the
  "connected but keys do nothing" zombie state), the watcher tries
  `bluetoothctl connect` up to 3 times per 30-minute window. Pass
  `--no-auto-reconnect` to disable. The tray's **Reconnect Bluetooth
  keyboards** menu item does the same for all paired keyboards on demand.
- **Shareable builds:** `../dist/build-package.sh` produces a `.deb` and a
  tarball in `../dist/out/`. The tarball's `install.sh` needs no root,
  auto-starts via XDG autostart, and ships `uninstall.sh` + `README-user.md`
  for non-technical recipients.
- Multiple keyboards are supported; each is tracked independently.
- If BlueZ exposes battery via `bluetoothctl info` but UPower does not, this
tool relies on UPower. The shell fallback and Python path both use UPower as
the source of truth.

## Troubleshooting

If nothing is printed in `--once` mode:

1. Confirm UPower sees the keyboard: `upower -e | grep keyboard`
2. Check details: `upower -i /org/freedesktop/UPower/devices/keyboard_dev_...`
3. Run with `--debug` and check that `python3-gi` is installed.
4. Escalate with the exact command output if the device is present but the
script fails.

# EPOMAKER Battery — keyboard battery tray for Linux

A little taskbar applet that shows the live battery level of your Bluetooth
keyboards (EPOMAKER, AULA F75, TH33, Keychron, and anything else that reports
battery over Bluetooth) — plus desktop notifications when a keyboard gets low,
is charging, or falls asleep.

No terminal needed after install. No kernel modules, no compiled code.

## What you get

- **Tray icon + label** — e.g. `⌨75` for each connected keyboard; the EPOMAKER
  wordmark logo normally, themed warning glyphs at low battery, a lightning
  bolt while charging.
- **Menu** — click the icon to see every device, its charge, and which
  transports are visible (Bluetooth / USB cable / 2.4G dongle), plus a
  **Reconnect Bluetooth keyboards** button for stubborn sleep/zombie links.
- **Notifications** — low battery (≤20% / ≤10%), charging, unplugged, and
  "reconnected" once a dropped keyboard's link is restored. The watcher tries
  to reconnect dropped Bluetooth keyboards automatically (3 attempts per
  30-minute window).

## Requirements

- Linux with a desktop session (tested on MATE; GNOME/KDE/XF4 work — GNOME
  users need the "AppIndicator and KStatusNotifierItem Support" shell
  extension for the icon to appear).
- `python3`, `python3-gi`, `upower`, and AppIndicator support
  (`gir1.2-ayatanaappindicator3-0.1` or `gir1.2-appindicator3-0.1`).
- Your keyboard must be **paired over Bluetooth**. That is how Linux sees its
  battery. Keyboards used only over USB cable or 2.4G dongle almost never
  report battery to the computer — this is a firmware trait, not a bug here.

## Install — option 1: .deb (Ubuntu / Debian / Mint)

Double-click `epomaker-battery_1.0.1-1_all.deb`, or:

    sudo apt install ./epomaker-battery_1.0.1-1_all.deb

The applet starts automatically at your next login. Remove with:

    sudo apt purge epomaker-battery

## Install — option 2: tar.gz (Fedora / Arch / openSUSE / anything)

    tar xzf epomaker-battery-1.0.1.tar.gz
    cd epomaker-battery-1.0.1
    ./install.sh

`install.sh` never needs a password. It prints a one-line hint if a
dependency is missing (with the apt/dnf/pacman command for your distro).
Add `--with-udev` only if you also want to use the VIA web configurator —
it installs two udev rules (asks for your password once):

- `99-epomaker.rules` — lets the browser configurator open the keyboard.
- `98-bt-power.rules` — stops the PC's Bluetooth adapter from suspending,
  which is what makes a sleeping keyboard's connection go zombie.

Uninstall everything later with `./uninstall.sh` (add `--with-udev` to also
remove the system rules).

## First run

1. Pair your keyboard over Bluetooth (system Bluetooth settings → add device;
   put the keyboard in pairing mode — often a long press of the BLE key or
  Fn+key combo; check your keyboard's manual).
2. Look at the taskbar: the EPOMAKER logo appears, then the charge label
   within ~30 seconds.

If the icon shows `⌨ no kb`, your keyboard's battery isn't reaching the
system yet — make sure it is paired **and connected** over Bluetooth.

## FAQ

**Why does my keyboard show "?" or no battery on the USB cable / dongle?**
Most keyboards (including EPOMAKER/AULA models) only send battery data over
their Bluetooth link. Use Bluetooth and the number appears. A few brands
(e.g. Logitech with their special dongle) do report battery over 2.4G — those
show up too.

**What does "Reconnect Bluetooth keyboards" do?**
Disconnects and reconnects each paired Bluetooth keyboard. This is the fix
for the "keyboard slept, connected flag says yes but keys do nothing" state.

**The state shows "unknown" instead of "discharging"?**
Harmless. Bluetooth's battery service only reports the percentage; the
charging bolt appears when a device does report charging (some mice do).

**I have other Bluetooth keyboards/mice — will they show up?**
Yes, anything that reports battery over Bluetooth appears by default. If you
want only EPOMAKER-family devices, edit the autostart entries (or systemd
units) and add `--epomaker-only` to the command line of both scripts.

## For developers / power users

Source files, systemd user units, and full project history live in the
`keyboard-tooling` project folder: `battery/battery-tray.py` (applet),
`battery/battery-watch.py` (notifier daemon), `battery/README.md` (systemd
setup + flags like `--once`, `--threshold`, `--no-auto-reconnect`).

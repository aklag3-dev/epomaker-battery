#!/usr/bin/env python3
"""Battery watcher for EPOMAKER Bluetooth keyboards via UPower D-Bus.

Detects UPower keyboard devices (type keyboard, or model/name matching
F75/EPOMAKER/AULA/TH33), subscribes to D-Bus PropertiesChanged events if
python3-gi is available, and sends desktop notifications on low battery or
charging state changes.

Usage:
    python3 battery-watch.py          # daemon mode
    python3 battery-watch.py --once   # print snapshot and exit
    python3 battery-watch.py --debug  # verbose daemon logs
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

HAVE_GI = False
Gio = GLib = None
try:
    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    HAVE_GI = True
except Exception:
    HAVE_GI = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UPOWER_NAME = "org.freedesktop.UPower"
UPOWER_PATH = "/org/freedesktop/UPower"
UPOWER_IFACE = "org.freedesktop.UPower"
DEVICE_IFACE = "org.freedesktop.UPower.Device"
PROPS_IFACE = "org.freedesktop.DBus.Properties"

STATE_NAMES = {
    0: "unknown",
    1: "charging",
    2: "discharging",
    3: "empty",
    4: "fully-charged",
    5: "pending-charge",
    6: "pending-discharge",
}

TYPE_NAMES = {
    1: "line-power",
    2: "battery",
    3: "ups",
    4: "monitor",
    5: "mouse",
    6: "keyboard",
    7: "pda",
    8: "phone",
}

# Friendly names used by UPower for bluetooth HID devices vary; match a few.
KEYBOARD_RE = re.compile(
    r"(?i)(epomaker|aula|f75|th33|keyboard|keyboards|keychron|nuphy|mouse|trackball|touchpad)"
)
# --epomaker-only restricts to EPOMAKER-family devices (see main()).
BRAND_RE = re.compile(r"(?i)(epomaker|aula|f75|th33)")
BRAND_ONLY = False
MAC_RE = re.compile(r"[0-9A-Fa-f]{2}(_[0-9A-Fa-f]{2}){5}")

# Auto-reconnect policy for BT keyboards that fall off (radio sleep/drop):
# try `bluetoothctl connect` after the device goes OFFLINE — 3 attempts per
# 30-minute window, 2 minutes apart, then back off until the device returns.
RECONNECT_MAX_ATTEMPTS = 3
RECONNECT_INTERVAL_SECONDS = 120
RECONNECT_WINDOW_SECONDS = 1800

# ---------------------------------------------------------------------------
# Logging / output helpers
# ---------------------------------------------------------------------------


def log(msg, debug=False, always=False):
    if always or debug:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
        print(f"[{ts}] {msg}", flush=True)


def notify(title, body, urgency="normal", sync=None):
    """Best-effort desktop notification.

    sync: if given, used as an x-canonical-private-synchronous id so the
    notification server REPLACES the previous notification of the same
    category instead of stacking duplicates (MATE's daemon supports this).
    """
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        # notify-send still works under many session managers, but warn in debug.
        pass
    cmd = ["notify-send", "-u", urgency, "-a", "EPOMAKER Battery"]
    if sync:
        cmd += ["-h", f"string:x-canonical-private-synchronous:{sync}"]
    cmd += [title, body]
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=10)
    except Exception as exc:
        log(f"notify-send failed: {exc}", debug=True)


def bt_connect(mac: str, timeout: int = 15) -> bool:
    """Ask BlueZ to (re)connect a paired device. True on 'Connection successful'."""
    if not shutil.which("bluetoothctl"):
        return False
    try:
        r = subprocess.run(
            ["bluetoothctl", "--timeout", str(timeout), "--", "connect", mac],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        out = (r.stdout or "") + (r.stderr or "")
        return "Connection successful" in out
    except Exception:
        return False


# ---------------------------------------------------------------------------
# UPower access
# ---------------------------------------------------------------------------


def parse_mac_from_native_path(native_path: str) -> str | None:
    """UPower native path for BT HID devices ends with dev_AA_BB_CC_DD_EE_01."""
    m = MAC_RE.search(native_path.replace(":", "_"))
    if m:
        return m.group(0).replace("_", ":").upper()
    return None


def state_name(state_val) -> str:
    try:
        return STATE_NAMES.get(int(state_val), f"state-{state_val}")
    except Exception:
        return str(state_val)


def read_device_props(bus, device_path: str) -> dict:
    proxy = Gio.DBusProxy.new_sync(
        bus,
        Gio.DBusProxyFlags.NONE,
        None,
        UPOWER_NAME,
        device_path,
        PROPS_IFACE,
        None,
    )
    return proxy.GetAll("(s)", DEVICE_IFACE)


def enumerate_devices(bus) -> list[str]:
    proxy = Gio.DBusProxy.new_sync(
        bus,
        Gio.DBusProxyFlags.NONE,
        None,
        UPOWER_NAME,
        UPOWER_PATH,
        UPOWER_IFACE,
        None,
    )
    return list(proxy.EnumerateDevices())


def clean_model(model, native_path=""):
    """Strip BLE profile-slot suffixes: 'TH33-1' -> 'TH33', 'AULA F75 Ultra 1' -> 'AULA F75 Ultra'."""
    name = (model or "").strip()
    if not name:
        return name
    if "keyboard_dev" in native_path:
        stripped = re.sub(r"[-_ ]\s*[1-4]\s*$", "", name)
    else:
        stripped = re.sub(r"[-_][1-4]$", "", name)
    return stripped.strip() or name


def is_keyboard_device(props: dict) -> bool:
    """True if this UPower device is a battery-reporting keyboard or mouse."""
    if not props.get("IsPresent", True):
        return False

    dtype = int(props.get("Type", 0))
    if dtype in (5, 6):  # mouse, keyboard
        if BRAND_ONLY:
            model = str(props.get("Model", "") or "")
            return bool(BRAND_RE.search(model))
        return True

    model = str(props.get("Model", "") or "")
    native_path = str(props.get("NativePath", "") or "")
    text = f"{model} {native_path}"
    if KEYBOARD_RE.search(text):
        return True

    # Some vendors expose BT battery as a generic device; whitelist friendly names.
    return False


# ---------------------------------------------------------------------------
# Snapshot logic
# ---------------------------------------------------------------------------


def describe_device(props: dict, now: float | None = None) -> dict:
    if now is None:
        now = time.time()
    model = str(props.get("Model", "") or "Unknown")
    native_path = str(props.get("NativePath", "") or "")
    model = clean_model(model, native_path)
    mac = parse_mac_from_native_path(native_path)
    pct = float(props.get("Percentage", 0.0) or 0.0)
    state = state_name(props.get("State", 0))
    update_time = int(props.get("UpdateTime", 0) or 0)
    age = int(now - update_time) if update_time else -1
    return {
        "model": model,
        "mac": mac,
        "percentage": pct,
        "state": state,
        "update_time": update_time,
        "age_seconds": age,
        "native_path": native_path,
    }


def print_snapshot(devices: list[dict], offline: dict[str, dict] | None = None):
    print(f"Keyboard battery snapshot ({datetime.now(timezone.utc).isoformat()})")
    if not devices:
        print("  No keyboards currently online.")
    for d in devices:
        age_str = f"{d['age_seconds']}s ago" if d["age_seconds"] >= 0 else "unknown"
        print(
            f"  {d['model']}  MAC={d['mac'] or 'n/a'}  "
            f"{d['percentage']:.0f}%  state={d['state']}  updated {age_str}"
        )
    if offline:
        for path, d in offline.items():
            print(
                f"  [OFFLINE] {d['model']}  MAC={d['mac'] or 'n/a'}  "
                f"last seen {d['percentage']:.0f}%  at {d['last_seen']}"
            )


# ---------------------------------------------------------------------------
# Polling fallback (no Gio)
# ---------------------------------------------------------------------------


def upower_i(device_path: str) -> dict:
    """Parse `upower -i` output into a dict of simple values."""
    out = subprocess.run(
        ["upower", "-i", device_path],
        capture_output=True,
        text=True,
        check=False,
    )
    props = {}
    for line in out.stdout.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        props[key.strip().lower().replace("-", "_")] = val.strip()
    return props


def poll_keyboards() -> list[dict]:
    """Enumerate keyboards using the `upower` CLI (no Gio)."""
    out = subprocess.run(
        ["upower", "-e"],
        capture_output=True,
        text=True,
        check=False,
    )
    found = []
    now = time.time()
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line.startswith("/org/freedesktop/UPower/devices/"):
            continue
        props = upower_i(line)
        model = props.get("model", "")
        native_path = props.get("native_path", "")
        text = f"{model} {native_path}"
        if not KEYBOARD_RE.search(text):
            continue
        pct_str = props.get("percentage", "0%").replace("%", "")
        try:
            pct = float(pct_str)
        except ValueError:
            pct = 0.0
        # upower -i prints relative "updated: ... (N seconds ago)"
        update_time = now
        age_match = re.search(r"\((\d+) seconds? ago\)", props.get("updated", ""))
        if age_match:
            update_time = now - int(age_match.group(1))
        found.append(
            {
                "model": clean_model(model or "Unknown", native_path),
                "mac": parse_mac_from_native_path(native_path),
                "percentage": pct,
                "state": props.get("state", "unknown"),
                "update_time": int(update_time),
                "age_seconds": int(now - update_time),
                "native_path": native_path,
                "path": line,
            }
        )
    return found


def poll_snapshot(debug=False) -> list[dict]:
    found = poll_keyboards()
    print_snapshot(found)
    return found


# ---------------------------------------------------------------------------
# Notification state machine
# ---------------------------------------------------------------------------


class Notifier:
    # Same (device, category) notification never fires more than once per this
    # window — protects against UPower/BlueZ state flap storms (e.g. a BLE
    # keyboard oscillating between 'unknown' and 'charging' between reads).
    REFIRE_SECONDS = 15 * 60

    def __init__(self, threshold: int = 20):
        self.threshold = threshold
        # path -> last state we already notified about
        self._last_state: dict[str, str] = {}
        self._low_notified: dict[str, int] = {}  # path -> lowest level notified
        self._offline_notified: set[str] = set()
        self._fired_at: dict[tuple, float] = {}  # (path, category) -> monotonic ts

    def _fire(self, path, category, title, body, urgency="normal"):
        now = time.time()
        last = self._fired_at.get((path, category))
        if last is not None and now - last < self.REFIRE_SECONDS:
            return  # still cooling down — skip silently
        self._fired_at[(path, category)] = now
        notify(title, body, urgency=urgency, sync=f"epomaker-{category}")

    def tick(self, devices: list[dict], all_known_paths=None):
        online_paths = {d.get("path", d.get("native_path", d["model"])) for d in devices}
        if all_known_paths is not None:
            # caller supplies the FULL known-device set: only truly vanished
            # devices get their episode state cleared (prevents re-arming
            # low-battery alerts when one device signals in isolation).
            online_paths = set(all_known_paths)
        for d in devices:
            path = d.get("path", d.get("native_path", d["model"]))
            model = d["model"]
            pct = d["percentage"]
            state = d["state"]

            prev_state = self._last_state.get(path)
            if prev_state != state:
                if state == "charging" and prev_state is not None:
                    self._fire(path, "charging", "Keyboard charging",
                               f"{model} is now charging.")
                elif prev_state == "charging" and state != "charging":
                    self._fire(path, "unplugged", "Keyboard unplugged",
                               f"{model} is now on battery.")
                self._last_state[path] = state

            # Low-battery notifications: once per discharge episode, re-arm when charged.
            if state == "charging":
                self._low_notified[path] = 100
            else:
                prev_low = self._low_notified.get(path, 100)
                if pct <= 10 and prev_low > 10:
                    self._fire(
                        path, "critical", "Keyboard battery critical",
                        f"{model} is at {pct:.0f}%.", urgency="critical",
                    )
                    self._low_notified[path] = 10
                elif pct <= self.threshold and prev_low > self.threshold:
                    self._fire(
                        path, "low", "Keyboard battery low",
                        f"{model} is at {pct:.0f}%.",
                    )
                    self._low_notified[path] = self.threshold

        # Devices that disappeared: clear state so next online event triggers fresh.
        for path in list(self._last_state.keys()):
            if path not in online_paths:
                self._last_state.pop(path, None)
                self._low_notified.pop(path, None)


# ---------------------------------------------------------------------------
# D-Bus daemon (Gio)
# ---------------------------------------------------------------------------


class WatchDaemon:
    def __init__(self, bus, threshold: int = 20, debug: bool = False,
                 auto_reconnect: bool = True):
        self.bus = bus
        self.threshold = threshold
        self.debug = debug
        self.auto_reconnect = auto_reconnect
        self.devices: dict[str, dict] = {}  # path -> device description
        self.offline: dict[str, dict] = {}  # path -> last seen description
        self._reconnect: dict[str, dict] = {}  # path -> reconnect attempt state
        self.notifier = Notifier(threshold)
        self._proxy_paths: dict[str, Gio.DBusProxy] = {}

    def _scan(self):
        paths = enumerate_devices(self.bus)
        now = time.time()
        online = set()
        for path in paths:
            try:
                props = read_device_props(self.bus, path)
            except Exception as exc:
                log(f"Cannot read {path}: {exc}", debug=self.debug)
                continue
            if not is_keyboard_device(props):
                continue
            info = describe_device(props, now)
            info["path"] = path
            self.devices[path] = info
            online.add(path)
            if path in self.offline:
                self.offline.pop(path, None)
                st = self._reconnect.pop(path, None)
                if st and st.get("attempts"):
                    self.notifier._fire(
                        path, "reconnect", "Keyboard reconnected",
                        f"{info['model']} Bluetooth link restored "
                        f"after {st['attempts']} reconnect attempt(s).",
                    )
            self._subscribe(path)

        # Mark disappeared devices offline.
        for path in list(self.devices.keys()):
            if path not in online:
                old = self.devices.pop(path)
                old["last_seen"] = datetime.now(timezone.utc).isoformat()
                self.offline[path] = old
                self._proxy_paths.pop(path, None)
                log(f"OFFLINE: {old['model']} ({path})", debug=True)

        return [self.devices[p] for p in self.devices]

    def _subscribe(self, path: str):
        if path in self._proxy_paths:
            return
        try:
            proxy = Gio.DBusProxy.new_sync(
                self.bus,
                Gio.DBusProxyFlags.NONE,
                None,
                UPOWER_NAME,
                path,
                DEVICE_IFACE,
                None,
            )
            proxy.connect("g-signal", self._on_signal, path)
            self._proxy_paths[path] = proxy
            log(f"Subscribed to {path}", debug=self.debug)
        except Exception as exc:
            log(f"Subscribe failed for {path}: {exc}", debug=self.debug)

    def _on_signal(self, proxy, sender_name, signal_name, parameters, path):
        if signal_name != "PropertiesChanged":
            return
        iface, changed, _invalidated = parameters.unpack()
        if iface != DEVICE_IFACE:
            return
        log(f"PropertiesChanged on {path}: {list(changed.keys())}", debug=self.debug)
        try:
            props = read_device_props(self.bus, path)
        except Exception as exc:
            log(f"Re-read failed for {path}: {exc}", debug=self.debug)
            return
        if not is_keyboard_device(props):
            # Device may have changed type or been removed.
            if path in self.devices:
                old = self.devices.pop(path)
                old["last_seen"] = datetime.now(timezone.utc).isoformat()
                self.offline[path] = old
            return
        info = describe_device(props, time.time())
        info["path"] = path
        self.devices[path] = info
        # Tick only this device's data, but tell the notifier which devices are
        # still known-good so isolated PropertiesChanged events do not wipe
        # other devices' notification episode state (that caused re-fires).
        self.notifier.tick([info], all_known_paths=list(self.devices.keys()))

    def run_once(self):
        online = self._scan()
        print_snapshot(online, self.offline)
        self.notifier.tick(online)

    def run_forever(self):
        log("Starting battery-watch daemon (D-Bus)", always=True)
        self.run_once()
        loop = GLib.MainLoop()
        # Safety re-scan every 60s in case D-Bus signals are missed.
        GLib.timeout_add_seconds(60, self._periodic_rescan)
        try:
            loop.run()
        except KeyboardInterrupt:
            log("Interrupted, exiting.", always=True)

    def _periodic_rescan(self):
        online = self._scan()
        self.notifier.tick(online)
        self._reconnect_tick()
        return True

    def _reconnect_tick(self):
        """Nudge BT keyboards that fell offline back into connection."""
        if not self.auto_reconnect or not self.offline:
            return
        now = time.time()
        for path, d in list(self.offline.items()):
            mac = d.get("mac")
            if not mac:
                continue
            if BRAND_ONLY and not BRAND_RE.search(d.get("model", "")):
                continue
            st = self._reconnect.setdefault(
                path, {"attempts": 0, "next_try": now + 60, "window_start": now}
            )
            if st["attempts"] >= RECONNECT_MAX_ATTEMPTS:
                if now - st["window_start"] >= RECONNECT_WINDOW_SECONDS:
                    st.update(attempts=0, window_start=now)  # fresh retry window
                else:
                    continue
            if now < st["next_try"]:
                continue
            ok = bt_connect(mac)
            st["attempts"] += 1
            st["next_try"] = now + RECONNECT_INTERVAL_SECONDS
            log(
                f"BT reconnect #{st['attempts']} for {d['model']} ({mac}): "
                f"{'ok' if ok else 'no answer'}",
                debug=self.debug, always=ok,
            )


# ---------------------------------------------------------------------------
# Polling daemon (no Gio)
# ---------------------------------------------------------------------------


def run_polling_daemon(threshold: int = 20, debug: bool = False):
    log("Starting battery-watch daemon (polling, upower CLI)", always=True)
    notifier = Notifier(threshold)
    while True:
        devices = poll_keyboards()
        print_snapshot(devices)
        notifier.tick(devices)
        if debug:
            log(f"Sleeping 60s...", debug=True)
        time.sleep(60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Watch EPOMAKER keyboard batteries")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print a snapshot and exit (for cron/CI/tests).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose logging.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=20,
        help="Low-battery notification threshold (default: 20).",
    )
    parser.add_argument(
        "--epomaker-only",
        action="store_true",
        help="Limit to EPOMAKER/AULA/TH33/F75 devices instead of all keyboards+mice.",
    )
    parser.add_argument(
        "--no-auto-reconnect",
        action="store_true",
        help="Do not try to reconnect Bluetooth keyboards that fall offline.",
    )
    args = parser.parse_args()
    global BRAND_ONLY
    BRAND_ONLY = args.epomaker_only

    if HAVE_GI:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except Exception:  # no D-Bus system bus (minimal/headless session)
            bus = None
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                  "No D-Bus system bus — falling back to UPower polling.",
                  file=sys.stderr)
        if bus is not None:
            daemon = WatchDaemon(
                bus, threshold=args.threshold, debug=args.debug,
                auto_reconnect=not args.no_auto_reconnect,
            )
            if args.once:
                daemon.run_once()
            else:
                daemon.run_forever()
        elif args.once:
            poll_snapshot(debug=args.debug)
        else:
            run_polling_daemon(threshold=args.threshold, debug=args.debug)
    else:
        if args.once:
            poll_snapshot(debug=args.debug)
        else:
            run_polling_daemon(threshold=args.threshold, debug=args.debug)


if __name__ == "__main__":
    main()

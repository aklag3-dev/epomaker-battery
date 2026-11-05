#!/usr/bin/env python3
"""EPOMAKER Battery — keyboard & mouse battery tray applet for MATE (Ayatana AppIndicator).

Shows live battery % of Bluetooth-paired keyboards and mice (via UPower)
as a taskbar icon + text label, with a per-device menu. Works with any
device whose battery reaches UPower (in practice: BLE devices with the
GATT Battery Service). Pure stdlib + gi; no pip. Complements
battery-watch.py (which does low-battery notifications); this one is
the visual readout.

Usage:
    battery-tray.py            # run the applet
    battery-tray.py --once     # print parsed devices, exit (no GUI)
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time

POLL_SECONDS = 30
DEVICE_FILTER = ("keyboard_dev", "mouse_dev")  # UPower object path substrings; BT input devices land here
BRAND_RE = re.compile(r"(?i)(epomaker|aula|f75|th33)")
# --epomaker-only: restrict to EPOMAKER-family devices (hide other BT keyboards/mice)
EPOMAKER_ONLY = "--epomaker-only" in sys.argv
APP_NAME = "EPOMAKER Battery"
LOGO_ICON = "epomaker-applet"  # bundled brand icon, installed to user theme by install_logo_icon()
LOGO_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "epomaker-applet.png")

# USB presence table: (vid:pid lowercase, keyboard, transport label).
# Battery % itself only ever arrives over the Bluetooth GATT path — these
# rows show which physical transports the host can SEE the keyboard on.
LSUSB_TRANSPORTS = [
    ("36b0:30aa", "EPOMAKER TH33", "USB cable"),
    ("36b0:3002", "EPOMAKER TH33", "2.4G dongle (receiver present)"),
    ("fffe:00a9", "AULA F75 Ultra", "USB cable"),
    ("0c45:fefe", "AULA F75 Ultra", "2.4G dongle (receiver present)"),
]


def usb_model_key(model):
    """Map a UPower model string to the keyboard family used in LSUSB_TRANSPORTS."""
    m = (model or "").lower()
    if "th33" in m:
        return "EPOMAKER TH33"
    if "f75" in m or "ultra" in m or "aula" in m:
        return "AULA F75 Ultra"
    return model


def clean_model(model, path=""):
    """Strip BLE profile-slot suffixes: 'TH33-1' -> 'TH33', 'AULA F75 Ultra 1' -> 'AULA F75 Ultra'.

    Firmware appends the Bluetooth profile-slot number to the advertised
    name. Dash/underscore slots ('-1') are stripped for all devices; the
    space-separated form (' 1') only for keyboards, because mouse product
    names use trailing digits for generations ('MX Master 3').
    """
    name = (model or "").strip()
    if not name:
        return name
    if "keyboard_dev" in path:
        stripped = re.sub(r"[-_ ]\s*[1-4]\s*$", "", name)
    else:
        stripped = re.sub(r"[-_][1-4]$", "", name)
    return stripped.strip() or name

ICON_STEPS = [  # (min %, icon base name) — freedesktop names, '-symbolic' tried first
    (90, "battery-full"),
    (70, "battery-high"),
    (50, "battery-medium"),
    (30, "battery-low"),
    (15, "battery-caution"),
    (0, "battery-empty"),
]
FALLBACK_ICON = "input-keyboard"


def run_upower(*args):
    try:
        return subprocess.run(["upower", *args], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ""


def read_transports():
    """Return {keyboard family: [transport labels]} from USB bus presence (cable/dongle)."""
    try:
        out = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=10).stdout.lower()
    except Exception:
        out = ""
    found = {}
    for vidpid, kb, kind in LSUSB_TRANSPORTS:
        if vidpid in out:
            found.setdefault(kb, []).append(kind)
    return found


def read_keyboards():
    """Return list of dicts: model, path, pct, state, transports[]."""
    usb = read_transports()
    paths = [p for p in run_upower("-e").splitlines() if any(f in p for f in DEVICE_FILTER)]
    devices = []
    seen_families = set()
    for p in paths:
        txt = run_upower("-i", p)
        if not txt:
            continue
        d = {"path": p}
        for line in txt.splitlines():
            key, _, val = line.partition(":")
            key, val = key.strip().lower(), val.strip()
            if key == "model":
                d["model"] = val
            elif key == "percentage":
                m = re.search(r"(\d+(?:\.\d+)?)", val)
                if m:
                    d["pct"] = float(m.group(1))
            elif key == "state":
                d["state"] = val.lower()
            elif key == "time to empty":  # presence implies live reading
                pass
        d.setdefault("model", "Keyboard")
        d.setdefault("pct", None)
        d.setdefault("state", "unknown")
        d["model"] = clean_model(d["model"], p)
        if EPOMAKER_ONLY and not BRAND_RE.search(d["model"]):
            continue
        fam = usb_model_key(d["model"])
        d["transports"] = ["Bluetooth"] + usb.pop(fam, [])
        seen_families.add(fam)
        devices.append(d)
    # Keyboards visible on USB but with no Bluetooth battery link:
    for fam, kinds in usb.items():
        if fam not in seen_families:
            devices.append({"model": fam, "path": "usb-only", "pct": None,
                            "state": "no BT battery path", "transports": kinds})
    return devices


def state_text(state):
    """'unknown'/'discharging' are UPower noise for BLE keyboards — show only meaningful states."""
    s = (state or "").strip()
    if s in ("", "unknown", "discharging"):
        return ""
    return s


def pick_icon(pct, charging):
    from gi.repository import Gtk
    theme = Gtk.IconTheme.get_default()
    if not charging:
        try:
            if pct is None or pct > 20:
                if theme.has_icon(LOGO_ICON):
                    return LOGO_ICON  # brand logo is the normal-state icon
        except Exception:
            pass
    if charging:
        names = ["battery-charging-symbolic", "battery-charging"]
    else:
        base = next((b for t, b in ICON_STEPS if pct is not None and pct >= t), FALLBACK_ICON)
        names = [base + "-symbolic", base]
    names.append(FALLBACK_ICON)
    theme = Gtk.IconTheme.get_default()
    for n in names:
        try:
            if theme.has_icon(n):
                return n
        except Exception:
            pass
    return FALLBACK_ICON


def install_logo_icon():
    """Copy the bundled brand PNG into USER hicolor theme dirs that the stock
    /usr/share/icons/hicolor/index.theme already indexes.

    CRITICAL: never write ~/.local/share/icons/hicolor/index.theme — a
    partial file there overrides the system hicolor index and breaks icon
    resolution (Gtk 'Theme file for hicolor has no name' warnings).
    Silent on failure — pick_icon then falls back to battery-*/ themed icons.
    """
    try:
        if not os.path.isfile(LOGO_SRC):
            return
        base = os.path.expanduser("~/.local/share/icons/hicolor")
        sizes = ("16x16", "24x24", "32x32", "48x48")
        src_mtime = os.path.getmtime(LOGO_SRC)
        for size in sizes:
            d = os.path.join(base, size, "apps")
            os.makedirs(d, exist_ok=True)
            dst = os.path.join(d, LOGO_ICON + ".png")
            if not os.path.isfile(dst) or os.path.getmtime(dst) < src_mtime:
                shutil.copyfile(LOGO_SRC, dst)
    except Exception:
        pass


def label_text(devices):
    if not devices:
        return "⌨ no kb"
    parts = []
    for d in devices:
        pct = d["pct"]
        mark = "⚡" if d["state"] == "charging" else ""
        parts.append(f"⌨{mark}{'' if pct is None else f'{pct:.0f}'}")
    return "  ".join(parts)


def tooltip_text(devices):
    if not devices:
        return f"{APP_NAME}: no keyboard/mouse battery visible (pair over Bluetooth)"
    lines = []
    for d in devices:
        pct = "?" if d["pct"] is None else f"{d['pct']:.0f}%"
        transports = " + ".join(d.get("transports", ["Bluetooth"]))
        st = state_text(d["state"])
        st = f" ({st})" if st else ""
        lines.append(f"{d['model']}: {pct}{st}\n    via {transports}")
    return "\n".join(lines)


def bt_cmd(args, timeout=15):
    """Run bluetoothctl non-interactively; return combined output text."""
    if not shutil.which("bluetoothctl"):
        return ""
    try:
        r = subprocess.run(
            ["bluetoothctl", "--timeout", str(timeout), "--"] + args,
            capture_output=True, text=True, timeout=timeout + 5,
        )
        return (r.stdout or "") + (r.stderr or "")
    except Exception:
        return ""


def paired_bt_keyboards():
    """[(mac, name, connected)] for paired BT keyboards, honouring --epomaker-only."""
    out = bt_cmd(["devices"], timeout=10)
    cands = []
    for line in out.splitlines():
        m = re.match(r"Device ([0-9A-F:]{17}) (.+)", line.strip())
        if not m:
            continue
        mac, name = m.group(1), m.group(2).strip()
        if EPOMAKER_ONLY and not BRAND_RE.search(name):
            continue
        info = bt_cmd(["info", mac], timeout=10)
        icon_m = re.search(r"Icon:\s*(\S+)", info)
        icon = icon_m.group(1) if icon_m else "other"
        connected = bool(re.search(r"Connected:\s*yes", info))
        looks_keyboard = icon == "keyboard" or re.search(r"(?i)keyboard", name)
        if EPOMAKER_ONLY or looks_keyboard or BRAND_RE.search(name):
            # (EPOMAKER_ONLY already dropped non-brand names above.)
            cands.append((mac, name, connected))
    return cands


def tray_notify(title, body):
    try:
        subprocess.run(
            ["notify-send", "-a", APP_NAME, "-t", "5000",
             "-h", "string:x-canonical-private-synchronous:epomaker-reconnect",
             title, body],
            check=False, capture_output=True, timeout=10,
        )
    except Exception:
        pass


def do_reconnect(done_cb):
    """Force-refresh BT links for paired keyboards (zombie links get a
    disconnect+connect cycle, dropped ones just a connect). Runs off the GUI thread."""
    cands = paired_bt_keyboards()
    if not cands:
        done_cb("No paired Bluetooth keyboards found.")
        return
    ok, failed = [], []
    for mac, name, connected in cands:
        if connected:
            bt_cmd(["disconnect", mac], timeout=10)
            time.sleep(1.5)
        out = bt_cmd(["connect", mac], timeout=15)
        (ok if "Connection successful" in out else failed).append(name)
    if ok and not failed:
        done_cb("Reconnected: " + ", ".join(ok))
    elif ok:
        done_cb("Reconnected " + ", ".join(ok) + "; failed: " + ", ".join(failed))
    else:
        done_cb("Could not reconnect: " + ", ".join(failed))


def main_once():
    devices = read_keyboards()
    ts = time.strftime("%F %T")
    if not devices:
        print(f"[{ts}] No keyboards visible on any transport (BT pairing, USB cable or 2.4G dongle).")
        return
    print(f"[{ts}] Keyboard battery tray data:")
    for d in devices:
        transports = " + ".join(d.get("transports", []))
        pct = "?" if d["pct"] is None else f"{d['pct']:.0f}%"
        print(f"  {d['model']}  {pct}  state={d['state']}  via [{transports}]  path={d['path']}")


def main_gui():
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import Gtk, GLib, AyatanaAppIndicator3 as AAI

    indicator = AAI.Indicator.new(
        "epomaker-battery", FALLBACK_ICON, AAI.IndicatorCategory.HARDWARE)
    indicator.set_status(AAI.IndicatorStatus.ACTIVE)
    install_logo_icon()

    def refresh(*_):
        devices = read_keyboards()
        # Build a fresh menu each tick — the old code re-prepended separators
        # and quit items onto the same Gtk.Menu forever (stacking duplicates).
        menu = Gtk.Menu()
        if not devices:
            item = Gtk.MenuItem.new_with_label(
                "(no keyboards detected — pair your keyboard over Bluetooth first)")
            item.set_sensitive(False)
            menu.append(item)
        for d in devices:
            pct = "?" if d["pct"] is None else f"{d['pct']:.0f}%"
            transports = " + ".join(d.get("transports", []))
            st = state_text(d["state"])
            st = f" {st}" if st else ""
            item = Gtk.MenuItem.new_with_label(f"{d['model']} — {pct}{st} [{transports}]")
            item.set_sensitive(False)
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        if shutil.which("bluetoothctl"):
            def on_reconnect(*_):
                threading.Thread(
                    target=do_reconnect,
                    args=(lambda msg: (tray_notify(APP_NAME, msg),
                                       GLib.idle_add(refresh)),),
                    daemon=True,
                ).start()
            rc_item = Gtk.MenuItem.new_with_label("Reconnect Bluetooth keyboards")
            rc_item.connect("activate", on_reconnect)
            menu.append(rc_item)
            menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem.new_with_label(f"Quit {APP_NAME}")
        quit_item.connect("activate", lambda *_: Gtk.main_quit())
        menu.append(quit_item)
        menu.show_all()
        indicator.set_menu(menu)
        indicator.set_label(label_text(devices), tooltip_text(devices))
        pct0 = devices[0]["pct"] if devices else None
        charging = any(d["state"] == "charging" for d in devices)
        icon = pick_icon(pct0, charging)
        try:
            indicator.set_icon_full(icon, APP_NAME)
        except Exception:
            indicator.set_icon(icon)
        return True

    refresh()
    GLib.timeout_add_seconds(POLL_SECONDS, refresh)
    Gtk.main()


if __name__ == "__main__":
    if "--once" in sys.argv:
        main_once()
    else:
        main_gui()

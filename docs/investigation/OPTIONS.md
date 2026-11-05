> **Appendix note (sanitized for publication, 2026-11-05).** This is the original internal investigation write-up behind EPOMAKER Battery. Device MAC addresses are replaced with `AA:BB:CC:DD:EE:*` placeholders and local home paths generalized; hardware model names, USB IDs and links to EPOMAKER's public firmware repositories are kept because they are the useful part. Companion artifacts referenced below (raw `check.sh` snapshots, vendored firmware sources, the experimental `th33-via.py` CLI) are intentionally not published.

# Keyboard Tooling Options Map — F75 Ultra + TH33

Date: 2026-11-03 · Status: **investigation complete, awaiting owner choices**
Inputs: 3 research briefs (F75 Ultra ecosystem, TH33 ecosystem, generic landscape) + local hardware audit (`HARDWARE.md`).
Full briefs preserved in session `ses_*` outputs; this file is the decision layer.

## Why "drivers are hard to set up" — root causes found

1. **F75 Ultra: the vendor tools don't support it at all.** AULA HUB, EPOMAKER Hub, and the legacy F75 online driver list only F75/F87/F99-class boards. The Ultra was deliberately moved to the **VIA track** — no hub will ever detect it. Every attempt to "set up the driver" was fighting a tool that isn't for this keyboard.
2. **Both boards: WebHID ≠ driver.** The sanctioned config path is `usevia.app` (Chrome/Edge/Opera) + vendor JSON, **wired USB only**. On Linux the classic failure is `/dev/hidraw` permissions (silent "failed to open") — fixed with one udev rule.
3. **F75 Ultra "finicky wireless" is partly a known Linux kernel bug.** `0c45:fefe` dongles go dead after ~1 min idle (kernels 6.8–7.1.x; fix merged upstream Aug 2026, **not in our 6.8.0-147** — verified: pattern absent from this kernel's `usbhid.ko`). Userspace workaround: `usbhid.quirks=0x0c45:0xfefe:0x400` (module parm confirmed available) or kernel upgrade.
4. **2.4G config is structurally impossible on this class of dongle.** The receivers expose only standard HID collections — no vendor endpoint to talk settings through, and Bluetooth never carries a config channel (confirmed across 4+ projects). Config = cable. Always.

## Device truth table (verified/confidence)

| | F75 Ultra | TH33 |
|---|---|---|
| Platform | **WB32FQ95** + closed wireless (2 of 3 briefs; supersedes 8051 guess) — vendor QMK PR #26444 in review | **Real QMK**: ES32FS026 Cortex-M0 + "91680" radio over SPI; GPL source at `github.com/Epomaker/th33` |
| Wired USB ID | `0xFFFE:0x00A9` — **CONFIRMED** from vendor `keyboard.json` in `github.com/Epomaker/x-Aula-F75-Ultra` (also processor WB32FQ95, bootloader `wb32-dfu`, encoder+rgb_matrix features on) | `36b0:30aa` — **CONFIRMED** from vendor `info.json` in `github.com/Epomaker/th33` (manufacturer string "RDMCTMZT" matches dongle) |
| Dongle | `0c45:fefe` (generic Sonix relay, 5 collections incl. knob) | `36b0:3002` — **confirmed** via manufacturer string in official firmware |
| VIA | Yes — vendor JSON, "Use V2 Definition" OFF | Yes — vendor JSON |
| DFU/reflash | ESC-hold → QMK Toolbox sees it (one-way-ish; no stock dump published) | Custom bootloader; GPL tree incomplete (no FS026 board def) → rebuild not possible |
| Battery readout | Fn+B = 10-step LED bar; BLE BAS test pending; no public HID cmd | Fn+PAUSE = LED bar; firmware analysis says **no host-readable battery exists** (one-way SPI to radio) |

## The two pain points split cleanly

**Key mapping / macros / layers → solved today, no building required:**
1. **VIA (on-board, best):** wire up the keyboard → `usevia.app` → load vendor JSON → remap keys/layers/macros/tap-hold/RGB/knob. Persists in EEPROM → works over 2.4G and BT on any host afterwards. Needs: Chromium-family browser + one udev rule.
2. **OS-level (host-side, for *scripts*):** VIA macros are key-sequencer limited and only live on the keyboard. For real scripting (open apps, shell commands, per-app layers, home-row mods): **keyd** (layers/tap-hold, covers login screen), **input-remapper** (richest macro engine + handles the knob's wheel axis), or **kanata** (QMK-shaped config language, portable to Windows). All work over *any* transport because they sit at evdev. This is the recommended complement, not a replacement.

**Battery → the genuine gap; three routes, cheapest first:**
1. **Bluetooth + GATT Battery Service** (Ultra): if the Ultra implements BAS (0x180F), BlueZ → UPower gives a true % natively, zero code. TH33: firmware evidence says no, but 30-second `bluetoothctl info` test decides both.
2. **Vendor query over wired/dongle** (Ultra): siblings have known commands (F87 `13 4A` over dongle; F75 `0x87` wired). Untested on Ultra — probeable with `hidapi` against `/dev/hidraw*` (read-only probing is low risk). Dongles cache; power-cycle to refresh.
3. **Keyboard LED readout** (Fn+B / Fn+PAUSE): the guaranteed-to-work answer, 10% granularity, no software.

## What we can build (ranked by value/effort)

| # | Build | What | Effort | Depends on |
|---|---|---|---|---|
| A | **Setup kit** | udev rules for `36b0` + `0c45:fefe` + wired IDs, VIA walkthrough, usbhid quirk config | ~15 min | ✅ **DONE + INSTALLED (2026-11-04)** |
| B | **Battery watcher daemon** | Python/hidapi + UPower: poll BT BAS when paired; probe known vendor battery cmds on hidraw for Ultra; tray/AppIndicator with age-stamp + charging detection. Copy `deepan-alve/l65battery.py` + `aula-f87-control-rs` patterns | ~1 day | ✅ **BUILT + LIVE-VERIFIED (2026-11-04)** — `battery/`: D-Bus event-driven daemon (PropertiesChanged + 60s re-scan), low-battery/charging notifications with episode logic, offline tracking, shell fallback, user systemd unit. Reads real F75 Ultra @ 75%. Awaiting user enablement. |
| C | **Remap/script stack** | keyd/input-remapper configs tuned to these two boards incl. knob handling | ~2–4 h | nothing; pairs with VIA |
| D | **Dongle protocol RE** | capture/decrypt `0c45:fefe` settings channel to get battery-over-2.4G | days, **maybe void** | B must fail first |
| — | Custom firmware | **No.** TH33 source incomplete; Ultra no stock dump; brick risk | — | — |

## Firmware source intelligence (from `vendor/` copies of Epomaker's own QMK source)

- **F75 Ultra repo = full WB32 QMK source incl. wireless stack** (`bled/`, `common/bt_task.c`, `bts_lib.h`). Battery lives as `bts_info.bt_info.pvol` = integer % on the main MCU, obtained by the keyboard sending vendor cmd `v_query_vol = 0x53` to its radio coprocessor every 4 s when awake+paired. Charge state via pins `B8` (charge) and cable detect. **No QMK battery report to host is compiled** (no `BATTERY_LEVELS`/`host_battery_publish`), and no GATT BAS string appears in the headers → battery almost certainly never reaches the host by any standard route. `BT_VOL` is also a VIA custom keycode (the Fn+B combo).
- **Implication for Build B:** a *dongle/wired* battery daemon needs a firmware feature the stock firmware doesn't have — RE of `bts_lib` internals (closed lib) would be required; **Option D territory**. If the BT-pairing checklist shows a GATT Battery Service anyway (stack default), Option B collapses to a 10-line UPower watcher instead. Run the checklist before building anything.
- **TH33 repo**: plain QMK board dir `keyboards/th33/th33/` (FS026, custom bootloader, VIA JSON shipped in-repo, 14 custom keycodes) — battery handling absent from `th33.c` as previously found.

## Owner action checklist — REDUCED (2026-11-04)

*Owner status update: both keyboards live on 2.4G dongles, working, layouts already flashed via a previous system, updated JSONs backed up. Mapping pain is SOLVED; battery is the remaining gap.*

**Kit status (2026-11-04, `checks/20261104-112445-th33-wired.txt`):** `install-setup.sh` RUN — udev rules live (Ultra dongle hidraw4–8 and TH33 wired `36b0:30aa` hidraw9–11 now `crw-rw-rw-` ✅; TH33 wired ID confirmed EXACTLY as predicted from vendor source). usbhid idle-drop quirk installed → **takes effect at next reboot** (verify: `cat /sys/module/usbhid/parameters/quirks`). NOTE: hidraw12 (Ultra's BT-HID path, `0005:0c45:fefe`) stays root-only — deliberate, not needed (battery goes via UPower/BlueZ D-Bus; config is wired-only). F75 Ultra battery re-confirmed: 75%, GATT BAS present while dongle active.

1. ~~Wired IDs~~ — **skipped** (confirmed from vendor sources; no remap needed now).
2. ~~Dongle discriminator~~ — **done** (`check.sh` baseline machine-confirmed: hidraw7–9 = TH33 `36b0:3002`, hidraw10–14 = Ultra `0c45:fefe`).
3. **BT battery test — DONE (both PASSED, 2026-11-04):** F75 Ultra `keyboard_dev_AA_BB_CC_DD_EE_01` 73-75%, GATT BAS present even while dongle active. **TH33 REVERSAL:** now paired over BT as `TH33-1` (AA:BB:CC:DD:EE:02) and UPower exposes `keyboard_dev_AA_BB_CC_DD_EE_02` at **100%, Battery Service 0x180F YES** — the earlier firmware-analysis pessimism ("battery not host-readable") was WRONG; the vendor BLE stack publishes BAS by default. Both keyboards fully covered by the Build B watcher/tray; no Option D RE needed. Both `state=unknown` because BLE BAS carries only the level char — charge status never arrives over BT (cosmetic only).
4. ~~VIA smoke test~~ — **superseded (2026-11-04):** user configured the TH33 keymap through the **official Epomaker hub web tool** (hub.getepomaker.com) successfully — it works where usevia.app stalled (V2 OFF, wired mode, after the udev fix). Our `th33-via.py` CLI remains as fallback; NOTE its hard lesson: the ES32 fw crashes under >5 back-to-back GET_BUFFER requests, and the live buffer serves a fixed window regardless of requested offset.

*End state 2026-11-04: both keyboards mapped + on Bluetooth; battery tray shows Ultra 73% + TH33 100%; mission (driver pain + battery visibility + remapping) CLOSED.*

*Closure 2026-11-05: BT autosuspend fix rules installed for real (`install-setup.sh` via pkexec; `98-bt-power.rules` live; adapter autosuspend = -1 confirmed; `udevadm trigger --action=add` bug in the installer found and fixed). Optional niceties shipped: watcher auto-reconnects stale BLE links (3 tries / 30-min window, `--no-auto-reconnect` disables) and the tray gained a Reconnect Bluetooth keyboards menu item. Packaging DONE: `dist/build-package.sh` → `epomaker-battery_1.0.1-1_all.deb` + tarball (rootless `install.sh`/`uninstall.sh` + `README-user.md`), all gates green in a clean ubuntu:24.04 container. Ultra keymap settled by user ("already mapped as i want") — f75 CLI tool retired. Only open item left: the 2.4G idle-drop quirk needs a GRUB kernel param if it ever matters again (currently irrelevant — BT-only workflow).**PUBLISHED 2026-11-05:** public repo [`aklag3-dev/epomaker-battery`](https://github.com/aklag3-dev/epomaker-battery) (MIT) — curated from `release/epomaker-battery/` (personal paths/MACs scrubbed; vendor sources, raw checks/ snapshots and the experimental th33-via.py kept out of the repo — the investigation notes themselves are published here as `docs/investigation/`). Release `v1.0.1` carries the .deb + tarball + SHA256SUMS; README states the rationale and an explicit 12-point limitations section, with the taskbar screenshot.*

## Next step options for the manager

- **Option 1 (recommended):** Run checklist → then build **A + B**; keep VIA for mapping, add keyd/input-remapper (C) only for scripting needs.
- **Option 2:** Skip battery dreaming; A + C only, accept Fn+B / Fn+PAUSE as the readout.
- **Option 3:** Full RE expedition (D) for battery-over-2.4G on the Ultra — research project, uncertain payoff.

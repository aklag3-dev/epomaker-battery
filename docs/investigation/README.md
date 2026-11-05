# Investigation log

The research behind EPOMAKER Battery, published as an appendix to the limitations
section of the main README — what was tested on real hardware, in what order, and
why the design settled where it did.

| File | Contents |
|---|---|
| `HARDWARE.md` | Local audit: USB IDs, hidraw topology, kernel config, paired devices |
| `OPTIONS.md` | The full options map — vendor driver, VIA/QMK, RE, remappers — ranked, plus the verification checklist results and the journey from open questions to shipped tools |
| `VIA.md` | The browser-remapping walkthrough and its failure modes (WebHID, hidraw permissions, protocol-version errors) |

> Sanitized for publication (2026-11-05): Bluetooth MACs are `AA:BB:CC:DD:EE:*`
> placeholders and home paths are generalized. Hardware names, USB IDs and links to
> EPOMAKER's public firmware repos are kept — they are the useful part. Raw
> diagnostic snapshots, vendored firmware sources and the experimental
> `th33-via.py` CLI are intentionally not published.

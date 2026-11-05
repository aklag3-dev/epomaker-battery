#!/usr/bin/env bash
# Battery watcher fallback for EPOMAKER keyboards using upower CLI.
# Used when python3-gi is not installed. Polls every 60s and sends
# notify-send alerts when battery is low or charging state changes.

set -euo pipefail

INTERVAL=60
THRESHOLD=20
DEBUG=0
ONCE=0

usage() {
    cat <<'EOF'
Usage: battery-watch.sh [--once] [--debug] [--threshold N]

  --once       Print a snapshot and exit.
  --debug      Print extra diagnostics.
  --threshold  Low-battery alert level (default: 20).
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --once) ONCE=1 ;;
        --debug) DEBUG=1 ;;
        --threshold) THRESHOLD="$2"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
    shift
done

LOG_PREFIX="battery-watch"
log() {
    echo "[$(date -Iseconds)] $*"
}

debug() {
    [[ $DEBUG -eq 1 ]] && echo "[$(date -Iseconds)] DEBUG: $*" >&2 || true
}

notify() {
    local urgency="$1" title="$2" body="$3"
    if command -v notify-send >/dev/null 2>&1; then
        notify-send -u "$urgency" -a "$LOG_PREFIX" "$title" "$body" || true
    else
        debug "notify-send not available"
    fi
}

# State files in /run/user/$UID or fall back to /tmp.
STATE_DIR="${XDG_RUNTIME_DIR:-/tmp}/battery-watch-state"
mkdir -p "$STATE_DIR"
LAST_STATE_FILE="$STATE_DIR/last_state"
LOW_NOTIFIED_FILE="$STATE_DIR/low_notified"

# EPOMAKER/AULA/F75/TH33 keyboards.
KEYBOARD_RE='(epomaker|aula|f75|th33|keyboard|keychron|nuphy)'

snapshot() {
    local path pct state model native_path mac age_line
    log "Keyboard battery snapshot ($(date -Iseconds))"
    local found=0
    while IFS= read -r path; do
        [[ -z "$path" ]] && continue
        local info
        info=$(upower -i "$path" 2>/dev/null || true)
        [[ -z "$info" ]] && continue
        model=$(echo "$info" | awk -F': ' '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $2); if ($1=="model") print $2}')
        native_path=$(echo "$info" | awk -F': ' '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $2); if ($1=="native-path") print $2}')
        if ! echo "${model} ${native_path}" | grep -qiE "$KEYBOARD_RE"; then
            continue
        fi
        found=1
        pct=$(echo "$info" | awk -F': ' '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $2); if ($1=="percentage") print $2}' | tr -d '%')
        state=$(echo "$info" | awk -F': ' '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $2); if ($1=="state") print $2}')
        mac=$(echo "$native_path" | grep -oE '([0-9A-Fa-f]{2}_){5}[0-9A-Fa-f]{2}' | tail -1 | tr '_' ':' | tr '[:lower:]' '[:upper:]')
        age_line=$(echo "$info" | awk -F': ' '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $2); if ($1=="updated") print $2}')
        printf '  %s  MAC=%s  %s%%  state=%s  updated %s\n' \
            "${model:-Unknown}" "${mac:-n/a}" "${pct:-0}" "${state:-unknown}" "${age_line:-unknown}"
    done < <(upower -e 2>/dev/null)

    if [[ $found -eq 0 ]]; then
        log "  No keyboards currently online."
    fi
}

# Daemon helpers for state persistence across polls.
load_state() {
    [[ -f "$LAST_STATE_FILE" ]] && cat "$LAST_STATE_FILE" || true
}

save_state() {
    printf '%s' "$1" > "$LAST_STATE_FILE"
}

load_low() {
    [[ -f "$LOW_NOTIFIED_FILE" ]] && cat "$LOW_NOTIFIED_FILE" || echo "100"
}

save_low() {
    printf '%s' "$1" > "$LOW_NOTIFIED_FILE"
}

snapshot_structured() {
    # Emit path|model|mac|pct|state for the daemon loop.
    local path info model native_path pct state mac
    while IFS= read -r path; do
        [[ -z "$path" ]] && continue
        info=$(upower -i "$path" 2>/dev/null || true)
        [[ -z "$info" ]] && continue
        model=$(echo "$info" | awk -F': ' '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $2); if ($1=="model") print $2}')
        native_path=$(echo "$info" | awk -F': ' '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $2); if ($1=="native-path") print $2}')
        if ! echo "${model} ${native_path}" | grep -qiE "$KEYBOARD_RE"; then
            continue
        fi
        pct=$(echo "$info" | awk -F': ' '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $2); if ($1=="percentage") print $2}' | tr -d '%')
        state=$(echo "$info" | awk -F': ' '{gsub(/^[ \t]+/, "", $1); gsub(/^[ \t]+/, "", $2); if ($1=="state") print $2}')
        mac=$(echo "$native_path" | grep -oE '([0-9A-Fa-f]{2}_){5}[0-9A-Fa-f]{2}' | tail -1 | tr '_' ':' | tr '[:lower:]' '[:upper:]')
        printf '%s|%s|%s|%s|%s\n' "$path" "${model:-Unknown}" "${mac:-n/a}" "${pct:-0}" "${state:-unknown}"
    done < <(upower -e 2>/dev/null)
}

update_state() {
    local path model mac pct state
    local new_state=""
    while IFS='|' read -r path model mac pct state; do
        [[ -z "$path" ]] && continue
        new_state="${new_state}${path}=${state}\n"
        local prev_state
        prev_state=$(load_state | awk -F'=' -v p="$path" '$1==p {print $2}' || true)

        if [[ -n "$prev_state" && "$prev_state" != "$state" ]]; then
            if [[ "$state" == "charging" ]]; then
                notify normal "Keyboard charging" "${model} is now charging."
            elif [[ "$prev_state" == "charging" ]]; then
                notify normal "Keyboard unplugged" "${model} is now on battery."
            fi
        fi

        local prev_low
        prev_low=$(load_low)
        if [[ "$state" == "charging" ]]; then
            save_low "100"
        else
            if awk "BEGIN {exit !($pct <= 10 && $prev_low > 10)}"; then
                notify critical "Keyboard battery critical" "${model} is at ${pct}%."
                save_low "10"
            elif awk "BEGIN {exit !($pct <= $THRESHOLD && $prev_low > $THRESHOLD)}"; then
                notify normal "Keyboard battery low" "${model} is at ${pct}%."
                save_low "$THRESHOLD"
            fi
        fi
    done < <(snapshot_structured)

    # Only keep online devices in state file.
    printf '%b' "$new_state" > "$LAST_STATE_FILE"
}

if [[ $ONCE -eq 1 ]]; then
    snapshot
    exit 0
fi

log "Starting battery-watch daemon (shell polling)"
while true; do
    snapshot
    update_state
    debug "Sleeping ${INTERVAL}s"
    sleep "$INTERVAL"
done

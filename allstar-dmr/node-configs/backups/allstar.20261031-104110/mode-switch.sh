#!/usr/bin/env bash
# mode-switch.sh -- privileged mode-switch helper for the dvswitch dashboard.
#
# Root-cause fix (Oct 16 2026): `dvswitch.sh mode <X>` changes Analog_Bridge's
# codec but leaves its TLV ports on the previous mode's values, silently
# breaking the Analog_Bridge -> MMDVM_Bridge audio handoff. Observed: after
# `mode YSF`, Analog_Bridge.ini still had the DMR ports (txPort=31103 /
# rxPort=31100), so a YSF tune (FCS00155 -> 900155) produced no "Remote CMD"
# in the bridge log and no "Linked to" in the YSFGateway log.
#
# This helper derives the correct ports at runtime from the node's own
# DVSwitch.ini [<MODE>] section and cross-pairs them into Analog_Bridge.ini's
# [AMBE_AUDIO] section BEFORE dvswitch.sh runs, then verifies afterwards:
#   Analog_Bridge txPort = DVSwitch [<MODE>] rxPort   (MMDVM_Bridge import)
#   Analog_Bridge rxPort = DVSwitch [<MODE>] txPort   (MMDVM_Bridge export)
# (Verified on the node: YSF 35100/35103 cross-pairs to AB tx=35103/rx=35100,
#  exactly like DMR's 31100/31103 <-> AB tx=31103/rx=31100.)
#
# Only [AMBE_AUDIO] is ever touched -- the [USRP] txPort/rxPort lines are left
# alone. If the mode has no section in DVSwitch.ini (e.g. M17), the port fix is
# skipped and the legacy `dvswitch.sh mode` behavior is preserved.
#
# Usage: sudo mode-switch.sh <MODE>   (MODE in DMR|YSF|P25|NXDN|DSTAR|M17)
# Env overrides (for testing): DVS_SWITCH, DVS_INI, ANALOG_INI
# Exit: 0 = dvswitch.sh mode succeeded; 1 = it failed; 2 = bad usage.
# Stdout (parsed by the CGI): "fixed=1|0" and optionally "note=<text>".

set -u
DVS_SWITCH="${DVS_SWITCH:-/opt/MMDVM_Bridge/dvswitch.sh}"
DVS_INI="${DVS_INI:-/opt/MMDVM_Bridge/DVSwitch.ini}"
ANALOG_INI="${ANALOG_INI:-/opt/Analog_Bridge/Analog_Bridge.ini}"

MODE="${1:-}"
case "$MODE" in
  DMR|YSF|P25|NXDN|DSTAR|M17) ;;
  *) echo "fixed=0"; echo "note=invalid mode: $MODE"; exit 2 ;;
esac

# --- 1. Read [<MODE>] txPort/rxPort from DVSwitch.ini (node ground truth) ---
section_for() {
  # $1 = mode -> candidate ini section names, one per line
  case "$1" in
    YSF) printf 'YSF\nSystem Fusion\n' ;;
    *)   printf '%s\n' "$1" ;;
  esac
}

dvs_port() {
  # $1 = section, $2 = key (txPort|rxPort) -> numeric value or empty
  awk -v sec="$1" -v key="$2" '
    /^\[/ { in_sec = ($0 == "[" sec "]") }
    in_sec && $0 ~ "^" key "[ \t]*=" {
      v = $0
      sub(/^[^=]*=[ \t]*/, "", v)
      sub(/[ \t;].*$/, "", v)
      if (v ~ /^[0-9]+$/) { print v; exit }
    }' "$DVS_INI" 2>/dev/null
}

ambe_port() {
  # $1 = key (txPort|rxPort) -> numeric value from [AMBE_AUDIO], or empty
  awk -v key="$1" '
    /^\[/ { in_ambe = ($0 == "[AMBE_AUDIO]") }
    in_ambe && $0 ~ "^" key "[ \t]*=" {
      v = $0
      sub(/^[^=]*=[ \t]*/, "", v)
      sub(/[ \t;].*$/, "", v)
      if (v ~ /^[0-9]+$/) { print v; exit }
    }' "$ANALOG_INI" 2>/dev/null
}

set_ambe_port() {
  # $1 = key, $2 = value ; scoped to [AMBE_AUDIO] only, idempotent, keeps
  # trailing comments. The [USRP] txPort/rxPort lines are never touched.
  local key="$1" val="$2" tmp
  [[ "$(ambe_port "$key")" == "$val" ]] && return 0
  tmp=$(mktemp) || return 1
  awk -v key="$key" -v val="$val" '
    /^\[/ { in_ambe = ($0 == "[AMBE_AUDIO]") }
    in_ambe && $0 ~ "^" key "[ \t]*=" {
      sub(/=[ \t]*[0-9]+/, "= " val); print; next
    }
    { print }
  ' "$ANALOG_INI" > "$tmp" && cat "$tmp" > "$ANALOG_INI"
  rm -f "$tmp"
}

dvs_tx=""; dvs_rx=""
while IFS= read -r sec; do
  [[ -n "$sec" ]] || continue
  dvs_tx=$(dvs_port "$sec" txPort); dvs_rx=$(dvs_port "$sec" rxPort)
  [[ -n "$dvs_tx" && -n "$dvs_rx" ]] && break
done < <(section_for "$MODE")

if [[ -z "$dvs_tx" || -z "$dvs_rx" ]]; then
  # No TLV section for this mode: keep legacy behavior, say so.
  if "$DVS_SWITCH" mode "$MODE" >/dev/null 2>&1; then
    echo "fixed=0"
    echo "note=no [$MODE] TLV ports in DVSwitch.ini; Analog_Bridge ports untouched"
    exit 0
  else
    echo "fixed=0"
    echo "note=no [$MODE] TLV ports in DVSwitch.ini and dvswitch.sh mode failed"
    exit 1
  fi
fi

# Cross-pair into [AMBE_AUDIO] before dvswitch.sh restarts the chain.
want_tx="$dvs_rx"; want_rx="$dvs_tx"
set_ambe_port txPort "$want_tx"
set_ambe_port rxPort "$want_rx"

# --- 2. Run the mode switch (dvswitch.sh restarts the bridge chain) ---
dvs_out=$("$DVS_SWITCH" mode "$MODE" 2>&1)
dvs_rc=$?
if [[ $dvs_rc -ne 0 ]]; then
  echo "fixed=1"
  echo "note=Analog_Bridge TLV ports set for $MODE but dvswitch.sh mode failed: $dvs_out"
  exit 1
fi

# --- 2b. Verify the codec actually switched (wait for Analog_Bridge restart) ---
# dvswitch.sh can exit 0 without the codec changing (e.g. ABInfo stale).
# Expected ambe_mode per target: DMR->DMR, YSF->YSFN, P25->P25, NXDN->NXDN,
# DSTAR->DSTAR. M17 has no TLV section so we never reach here for M17.
expected_mode="$MODE"
[[ "$MODE" == "YSF" ]] && expected_mode="YSFN"
abinfo_now=""
for _ in 1 2 3 4 5 6; do
  sleep 2
  abinfo_now=$(ls -t /tmp/ABInfo_*.json 2>/dev/null | head -1)
  [[ -n "$abinfo_now" ]] || continue
  cur_mode=$(python3 -c "import json,sys; print(json.load(open('$abinfo_now')).get('tlv',{}).get('ambe_mode',''))" 2>/dev/null)
  [[ "$cur_mode" == "$expected_mode" ]] && break
  cur_mode=""
done
if [[ -z "${cur_mode:-}" ]]; then
  got=$(python3 -c "import json,sys; print(json.load(open('$abinfo_now')).get('tlv',{}).get('ambe_mode','?'))" 2>/dev/null || echo "?")
  echo "fixed=1"
  echo "note=TLV ports set for $MODE but codec still '$got' (expected '$expected_mode'); dvswitch.sh mode may not have taken"
  exit 1
fi

# --- 3. Verify dvswitch.sh didn't move the ports; repair + restart if it did ---
if [[ "$(ambe_port txPort)" != "$want_tx" || "$(ambe_port rxPort)" != "$want_rx" ]]; then
  set_ambe_port txPort "$want_tx"
  set_ambe_port rxPort "$want_rx"
  systemctl restart analog_bridge 2>/dev/null || true
  echo "fixed=1"
  echo "note=ports drifted after dvswitch.sh; repaired and restarted analog_bridge"
  exit 0
fi

echo "fixed=1"
exit 0

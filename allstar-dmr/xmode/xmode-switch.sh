#!/usr/bin/env bash
# xmode-switch.sh -- privileged helper for the dashboard Bridge card.
# Design v2 (xmode/DESIGN.md): the bridge is DVSwitch-native and
# pairwise. No Asterisk, no node numbers -- a bridge is an
# Analog_Bridge<->Analog_Bridge USRP crossover with the usrp-agc shim
# in the middle, between two leg stacks that run only while bridged.
#
#   bridge-start <legA> <legB>
#       Point both legs' USRP transmit ports at a generated bridge
#       shim (ini edits; they persist across restarts), generate the
#       shim config, start the shim + both leg stacks, and record the
#       pairing in bridge.state. One bridge at a time.
#   bridge-stop
#       Stop the shim + both leg stacks, park the transmit ports.
#   tune <leg> <dest...>
#       Ini edit (+ restart of the affected process IF it is running;
#       a stopped leg just takes the new value at its next start).
#       dmr: leg AB ini [AMBE_AUDIO] txTg (dial string for the leg's
#       own DMRGateway: plain=BM, 4+pad=TGIF, 7+pad=KS-DMR).
#       ysf/p25/nxdn: leg gateway ini [Network] Startup.
#       m17: /etc/USRP2M17-xmode.ini [M17 Network] Name/Address/
#       DstPort, resolved server-side from the DVRef mrefd registry --
#       never from browser-supplied hosts. When the M17 leg is
#       running, the switch is verified by a NEW ACKN in its log.
#   agc-shim <main|bridge> on|bypass
#       Write the shim's state file (noticed within a second).
#       "bypass" = byte-identical pass-through.
#   agc-ab <main|dmr|ysf|p25|nxdn> agc|gain
#       Flip that Analog_Bridge.ini [USRP] usrpAudio between
#       AUDIO_USE_AGC and AUDIO_USE_GAIN.
#   gain <main|dmr|ysf|p25|nxdn> <usrp|tlv> <0.00-5.00>
#       Set a manual gain; that direction leaves AGC for
#       AUDIO_USE_GAIN (manual override is the point).
#   status -- key=value lines for the CGI.
#
# Env overrides (testing): XMODE_DIR, MAIN_AB_INI, M17_XMODE_INI,
# M17_REGISTRY, M17_XMODE_LOG, AGC_STATE_DIR, BRIDGE_STATE, SYSTEMCTL
# Exit: 0 ok, 1 failed, 2 bad usage. Stdout is machine-parsed.

set -u
XMODE_DIR="${XMODE_DIR:-/opt/xmode}"
MAIN_AB_INI="${MAIN_AB_INI:-/opt/Analog_Bridge/Analog_Bridge.ini}"
M17_XMODE_INI="${M17_XMODE_INI:-/etc/USRP2M17-xmode.ini}"
M17_REGISTRY="${M17_REGISTRY:-/var/lib/usrp2m17/reflectors.json}"
AGC_STATE_DIR="${AGC_STATE_DIR:-/run/usrp-agc}"
BRIDGE_STATE="${BRIDGE_STATE:-$XMODE_DIR/bridge.state}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
PARK=34299
SHIM_A=34401
SHIM_B=34402

leg_home() { case "$1" in dmr) echo 34201;; ysf) echo 34211;; p25) echo 34221;; nxdn) echo 34231;; m17) echo 34240;; esac; }
leg_ab_ini() { [[ "$1" == main ]] && echo "$MAIN_AB_INI" || echo "$XMODE_DIR/legs/$1/Analog_Bridge.ini"; }
leg_ab_unit() { [[ "$1" == main ]] && echo "analog_bridge" || echo "analog-bridge-xmode-$1"; }
leg_gw_ini() { case "$1" in ysf) echo "$XMODE_DIR/legs/ysf/YSFGateway.ini";; p25) echo "$XMODE_DIR/legs/p25/P25Gateway.ini";; nxdn) echo "$XMODE_DIR/legs/nxdn/NXDNGateway.ini";; esac; }
leg_gw_unit() { echo "$1gateway-xmode"; }
leg_main_unit() { [[ "$1" == m17 ]] && echo "usrp2m17-xmode" || echo "analog-bridge-xmode-$1"; }
leg_units() { # start order: gateway, bridge, AB (m17 = single unit)
  case "$1" in
    dmr) echo "dmrgateway-xmode mmdvm-bridge-xmode-dmr analog-bridge-xmode-dmr" ;;
    ysf) echo "ysfgateway-xmode mmdvm-bridge-xmode-ysf analog-bridge-xmode-ysf" ;;
    p25) echo "p25gateway-xmode mmdvm-bridge-xmode-p25 analog-bridge-xmode-p25" ;;
    nxdn) echo "nxdngateway-xmode mmdvm-bridge-xmode-nxdn analog-bridge-xmode-nxdn" ;;
    m17) echo "usrp2m17-xmode" ;;
  esac
}
# Where a leg's USRP transmit port lives: AB ini [USRP] txPort, or
# USRP2M17 ini [USRP Network] DstPort.
leg_tx_target() { [[ "$1" == m17 ]] && echo "$M17_XMODE_INI|USRP Network|DstPort" || echo "$(leg_ab_ini "$1")|USRP|txPort"; }

ini_get() {
  awk -v sec="$2" -v key="$3" '
    /^\[/ { in_sec = ($0 == "[" sec "]") }
    in_sec && $0 ~ "^" key "[ \t]*=" {
      v = $0; sub(/^[^=]*=[ \t]*/, "", v); sub(/[ \t;].*$/, "", v); print v; exit
    }' "$1" 2>/dev/null
}

ini_get_line() {
  awk -v sec="$2" -v key="$3" '
    /^\[/ { in_sec = ($0 == "[" sec "]") }
    in_sec && $0 ~ "^" key "[ \t]*=" {
      v = $0; sub(/^[^=]*=[ \t]*/, "", v); sub(/[ \t]*;.*$/, "", v)
      sub(/[ \t]+$/, "", v); print v; exit
    }' "$1" 2>/dev/null
}

ini_set() {
  local file="$1" sec="$2" key="$3" val="$4" tmp
  [[ "$(ini_get_line "$file" "$sec" "$key")" == "$val" ]] && return 0
  tmp=$(mktemp) || return 1
  awk -v sec="$sec" -v key="$key" -v val="$val" '
    /^\[/ { in_sec = ($0 == "[" sec "]") }
    in_sec && $0 ~ "^" key "[ \t]*=" {
      c = index($0, ";"); comment = (c > 0) ? " " substr($0, c) : ""
      eq = index($0, "=")
      print substr($0, 1, eq) " " val comment; next
    }
    { print }
  ' "$file" > "$tmp" && cat "$tmp" > "$file"
  rm -f "$tmp"
}

set_leg_tx() { # <leg> <port>
  local spec file sec key
  spec=$(leg_tx_target "$1"); file="${spec%%|*}"; spec="${spec#*|}"; sec="${spec%%|*}"; key="${spec##*|}"
  ini_set "$file" "$sec" "$key" "$2"
}

unit_active() { $SYSTEMCTL is-active --quiet "$1" 2>/dev/null; }

read_bridge() { # sets BA, BB (empty when no bridge recorded)
  BA=""; BB=""
  [[ -f "$BRIDGE_STATE" ]] || return 0
  BA=$(grep '^a=' "$BRIDGE_STATE" 2>/dev/null | cut -d= -f2)
  BB=$(grep '^b=' "$BRIDGE_STATE" 2>/dev/null | cut -d= -f2)
}

do_bridge_start() { # <legA> <legB>
  local a="$1" b="$2" home_a home_b shim_ini
  [[ "$a" != "$b" ]] || { echo "ok=0"; echo "note=pick two different legs"; return 2; }
  read_bridge
  if [[ -n "$BA" && -n "$BB" ]]; then
    echo "ok=0"; echo "note=bridge $BA<->$BB is already up -- stop it first"; return 1
  fi
  home_a=$(leg_home "$a"); home_b=$(leg_home "$b")
  shim_ini="$XMODE_DIR/usrp-agc/bridge.ini"
  mkdir -p "$XMODE_DIR/usrp-agc" "$AGC_STATE_DIR"
  cat > "$shim_ini" <<EOF
; usrp-agc -- BRIDGE instance, generated by xmode-switch.sh.
; A side faces leg "$a" (home $home_a), B side faces leg "$b" (home $home_b).
; AGC on both directions: digital-to-digital leveling.
[shim]
listen_a = $SHIM_A
send_a = $home_a
listen_b = $SHIM_B
send_b = $home_b
agc_a_to_b = on
agc_b_to_a = on
state_file = $AGC_STATE_DIR/bridge.state

[agc]
target_dbfs_rms = -20
max_gain_db = 24
min_gain_db = -6
ceiling_dbfs_peak = -3
gate_dbfs_rms = -50
attack_ms = 5
release_ms = 200
EOF
  set_leg_tx "$a" "$SHIM_A" || { echo "ok=0"; echo "note=failed to wire leg $a"; return 1; }
  set_leg_tx "$b" "$SHIM_B" || { echo "ok=0"; echo "note=failed to wire leg $b"; return 1; }
  printf 'a=%s\nb=%s\n' "$a" "$b" > "$BRIDGE_STATE"
  $SYSTEMCTL start usrp-agc@bridge 2>/dev/null
  $SYSTEMCTL start $(leg_units "$a") 2>/dev/null
  $SYSTEMCTL start $(leg_units "$b") 2>/dev/null
  sleep 1
  if unit_active usrp-agc@bridge && unit_active "$(leg_main_unit "$a")" && unit_active "$(leg_main_unit "$b")"; then
    echo "ok=1"; echo "bridge=$a-$b"
  else
    echo "ok=0"; echo "note=bridge started but a component is not active -- check systemctl status, then bridge-stop"
    return 1
  fi
}

do_bridge_stop() {
  read_bridge
  local legs="$BA $BB"
  [[ -z "${BA}${BB}" ]] && legs="dmr ysf p25 nxdn m17"
  $SYSTEMCTL stop usrp-agc@bridge 2>/dev/null
  local leg
  for leg in $legs; do
    [[ -n "$leg" ]] || continue
    $SYSTEMCTL stop $(leg_units "$leg") 2>/dev/null
    set_leg_tx "$leg" "$PARK"
  done
  rm -f "$BRIDGE_STATE"
  echo "ok=1"; echo "bridge="
}

do_tune() { # <leg> <dest...>
  local leg="$1"; shift
  case "$leg" in
    dmr)
      local dial="$1"
      [[ "$dial" =~ ^[0-9]{1,7}$ ]] || { echo "ok=0"; echo "note=bad DMR dial string"; return 2; }
      ini_set "$(leg_ab_ini dmr)" "AMBE_AUDIO" "txTg" "$dial" || { echo "ok=0"; echo "note=ini edit failed"; return 1; }
      $SYSTEMCTL try-restart "$(leg_ab_unit dmr)" 2>/dev/null
      echo "ok=1"; echo "dest=$(ini_get "$(leg_ab_ini dmr)" "AMBE_AUDIO" "txTg")"
      ;;
    ysf|p25|nxdn)
      local dest="$1" ini unit
      if [[ "$leg" == ysf ]]; then [[ "$dest" =~ ^[A-Za-z0-9_.\ -]{1,48}$ ]] || { echo "ok=0"; echo "note=bad YSF destination"; return 2; }
      else [[ "$dest" =~ ^[0-9]{1,6}$ ]] || { echo "ok=0"; echo "note=bad destination"; return 2; }; fi
      ini=$(leg_gw_ini "$leg"); unit=$(leg_gw_unit "$leg")
      ini_set "$ini" "Network" "Startup" "$dest" || { echo "ok=0"; echo "note=ini edit failed"; return 1; }
      $SYSTEMCTL try-restart "$unit" 2>/dev/null
      echo "ok=1"; echo "dest=$(ini_get "$ini" "Network" "Startup")"
      ;;
    m17)
      # args: <reflector> <module>; reflector may be "M17-ZOM" or bare
      # "ZOM" (the m17-switch.sh convention). Host/port resolved
      # server-side from the DVRef registry -- never from the browser.
      local desig="$1" mod="$2" resolved
      [[ "$desig" =~ ^(M17-)?[A-Za-z0-9]{1,12}$ && "$mod" =~ ^[A-Z]$ ]] || { echo "ok=0"; echo "note=bad M17 reflector/module"; return 2; }
      resolved=$(python3 - "$M17_REGISTRY" "$desig" <<'PYEOF'
import json, sys
want = sys.argv[2].strip().upper()
if want.startswith("M17-"):
    want = want[4:]
try:
    refs = json.load(open(sys.argv[1]))["data"]["reflectors"]
except Exception:
    sys.exit(1)
for r in refs:
    if str(r.get("designator", "")).upper() == want:
        host = r.get("dns") or r.get("ipv4")
        if not host:
            sys.exit(1)
        print("%s %s M17-%s" % (host, r.get("port") or 17000, r.get("designator")))
        sys.exit(0)
sys.exit(1)
PYEOF
) || { echo "ok=0"; echo "note=reflector not in registry"; return 1; }
      local host port canon; read -r host port canon <<< "$resolved"
      [[ -n "$host" && "$port" =~ ^[0-9]+$ && -n "$canon" ]] || { echo "ok=0"; echo "note=registry entry incomplete"; return 1; }
      ini_set "$M17_XMODE_INI" "M17 Network" "Name" "$canon $mod"
      ini_set "$M17_XMODE_INI" "M17 Network" "Address" "$host"
      ini_set "$M17_XMODE_INI" "M17 Network" "DstPort" "$port"
      if ! unit_active usrp2m17-xmode; then
        echo "ok=1"; echo "dest=$canon $mod"; echo "note=leg not running; applies at next bridge start"; return 0
      fi
      # Running: restart and verify a NEW ACKN (a stale one from the
      # previous session must not count). NACK retry rides the
      # bridge's own re-CONN; allow one retry cycle.
      local log="${M17_XMODE_LOG:-/var/log/usrp2m17-xmode/USRP2M17-XMode.log}" size_before=0 i
      [[ -f "$log" ]] && size_before=$(stat -c %s "$log" 2>/dev/null || echo 0)
      $SYSTEMCTL restart usrp2m17-xmode 2>/dev/null
      for i in $(seq 1 20); do
        sleep 3
        if [[ -f "$log" ]] && tail -c +$((size_before + 1)) "$log" 2>/dev/null | grep -q "Received ACKN from reflector"; then
          echo "ok=1"; echo "dest=$canon $mod"; echo "note=reflector acknowledged"; return 0
        fi
      done
      echo "ok=0"; echo "note=no ACKN from reflector within 60s (session may still settle; check the bridge log)"
      return 1
      ;;
  esac
}

do_agc_shim() { # <main|bridge> on|bypass
  local which="$1" val="$2"
  [[ "$val" == on || "$val" == bypass ]] || { echo "ok=0"; echo "note=bad shim state"; return 2; }
  mkdir -p "$AGC_STATE_DIR" || return 1
  printf '%s\n' "$val" > "$AGC_STATE_DIR/$which.state" || return 1
  echo "ok=1"; echo "shim=$val"
}

do_agc_ab() { # <which> agc|gain
  local which="$1" val="$2" ini want
  ini=$(leg_ab_ini "$which")
  case "$val" in agc) want="AUDIO_USE_AGC";; gain) want="AUDIO_USE_GAIN";; *) echo "ok=0"; echo "note=bad ab agc value"; return 2;; esac
  ini_set "$ini" "USRP" "usrpAudio" "$want" || { echo "ok=0"; echo "note=ini edit failed"; return 1; }
  $SYSTEMCTL try-restart "$(leg_ab_unit "$which")" 2>/dev/null
  echo "ok=1"; echo "ab_agc=$([[ "$val" == agc ]] && echo 1 || echo 0)"
}

do_gain() { # <which> <usrp|tlv> <0.00-5.00>
  local which="$1" dir="$2" val="$3" ini key modekey
  [[ "$val" =~ ^[0-9]+(\.[0-9]{1,2})?$ ]] || { echo "ok=0"; echo "note=bad gain value"; return 2; }
  awk -v v="$val" 'BEGIN { exit !(v >= 0 && v <= 5) }' || { echo "ok=0"; echo "note=gain out of range 0-5"; return 2; }
  ini=$(leg_ab_ini "$which")
  case "$dir" in
    usrp) key="usrpGain"; modekey="usrpAudio" ;;
    tlv)  key="tlvGain";  modekey="tlvAudio" ;;
    *) echo "ok=0"; echo "note=bad direction"; return 2 ;;
  esac
  # A manual gain write is an explicit override: that direction leaves
  # AGC (if it was in it) and goes to AUDIO_USE_GAIN with this value.
  ini_set "$ini" "USRP" "$modekey" "AUDIO_USE_GAIN" || { echo "ok=0"; echo "note=ini edit failed"; return 1; }
  ini_set "$ini" "USRP" "$key" "$val" || { echo "ok=0"; echo "note=ini edit failed"; return 1; }
  $SYSTEMCTL try-restart "$(leg_ab_unit "$which")" 2>/dev/null
  echo "ok=1"; echo "gain=$(ini_get "$ini" "USRP" "$key")"
}

shim_state() { # <which> -> on|bypass (missing file = on)
  local f="$AGC_STATE_DIR/$1.state"
  [[ -f "$f" ]] && grep -qi bypass "$f" && echo bypass || echo on
}

do_status() {
  read_bridge
  if [[ -n "$BA" && -n "$BB" ]] && unit_active usrp-agc@bridge; then
    echo "bridge.active=1"
  else
    echo "bridge.active=0"
  fi
  echo "bridge.a=$BA"
  echo "bridge.b=$BB"
  echo "bridge.shim=$(shim_state bridge)"
  local leg
  for leg in dmr ysf p25 nxdn m17; do
    if [[ "$leg" == "$BA" || "$leg" == "$BB" ]]; then echo "leg.$leg.bridged=1"; else echo "leg.$leg.bridged=0"; fi
    unit_active "$(leg_main_unit "$leg")" && echo "leg.$leg.active=1" || echo "leg.$leg.active=0"
    case "$leg" in
      dmr) echo "leg.dmr.dest=$(ini_get "$(leg_ab_ini dmr)" "AMBE_AUDIO" "txTg")" ;;
      ysf|p25|nxdn) echo "leg.$leg.dest=$(ini_get "$(leg_gw_ini "$leg")" "Network" "Startup")" ;;
      m17) echo "leg.m17.dest=$(ini_get_line "$M17_XMODE_INI" "M17 Network" "Name")" ;;
    esac
    if [[ "$leg" != m17 ]]; then
      [[ "$(ini_get "$(leg_ab_ini "$leg")" "USRP" "usrpAudio")" == "AUDIO_USE_AGC" ]] && echo "leg.$leg.ab_agc=1" || echo "leg.$leg.ab_agc=0"
      echo "leg.$leg.usrp_gain=$(ini_get "$(leg_ab_ini "$leg")" "USRP" "usrpGain")"
      echo "leg.$leg.tlv_gain=$(ini_get "$(leg_ab_ini "$leg")" "USRP" "tlvGain")"
    fi
  done
  echo "main.shim=$(shim_state main)"
  [[ "$(ini_get "$MAIN_AB_INI" "USRP" "usrpAudio")" == "AUDIO_USE_AGC" ]] && echo "main.ab_agc=1" || echo "main.ab_agc=0"
  echo "main.usrp_gain=$(ini_get "$MAIN_AB_INI" "USRP" "usrpGain")"
  echo "main.tlv_gain=$(ini_get "$MAIN_AB_INI" "USRP" "tlvGain")"
  echo "ok=1"
}

ACTION="${1:-}"; ARG1="${2:-}"; ARG2="${3:-}"
case "$ACTION" in
  bridge-start) case "$ARG1" in dmr|ysf|p25|nxdn|m17) case "$ARG2" in dmr|ysf|p25|nxdn|m17) do_bridge_start "$ARG1" "$ARG2";; *) echo "ok=0"; echo "note=bad leg B"; exit 2;; esac;; *) echo "ok=0"; echo "note=bad leg A"; exit 2;; esac ;;
  bridge-stop)  do_bridge_stop ;;
  tune)         case "$ARG1" in dmr|ysf|p25|nxdn) do_tune "$ARG1" "$ARG2";; m17) do_tune m17 "$ARG2" "${4:-}";; *) echo "ok=0"; echo "note=bad leg"; exit 2;; esac ;;
  agc-shim)     case "$ARG1" in main|bridge) do_agc_shim "$ARG1" "$ARG2";; *) echo "ok=0"; echo "note=bad target"; exit 2;; esac ;;
  agc-ab)       case "$ARG1" in main|dmr|ysf|p25|nxdn) do_agc_ab "$ARG1" "$ARG2";; *) echo "ok=0"; echo "note=bad target"; exit 2;; esac ;;
  gain)         case "$ARG1" in main|dmr|ysf|p25|nxdn) do_gain "$ARG1" "$ARG2" "${4:-}";; *) echo "ok=0"; echo "note=bad target"; exit 2;; esac ;;
  status)       do_status ;;
  *) echo "ok=0"; echo "note=usage: xmode-switch.sh bridge-start|bridge-stop|tune|agc-shim|agc-ab|gain|status ..."; exit 2 ;;
esac

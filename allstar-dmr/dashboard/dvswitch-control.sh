#!/usr/bin/env bash
# dvswitch-control.sh -- CGI backend for the KF0RIZ digital control panel.
#
# Install: sudo cp dvswitch-control.sh /var/www/cgi-bin/ (or /usr/lib/cgi-bin/)
#          sudo chmod 755 /var/www/cgi-bin/dvswitch-control.sh
# Apache needs: ScriptAlias /cgi-bin/ /var/www/cgi-bin/ + ExecCGI
#
# Actions (via ?action=):
#   status  -> JSON: mode, tune, tune_alias, services, scan_src, log
#   tune    -> ?tgid=NNNN : run dvswitch.sh tune <tgid>
#   mode    -> ?mode=DMR|YSF|P25|NXDN|DSTAR : run dvswitch.sh mode <mode>
#
# Security: LAN-only by Apache config. No auth in script (matches existing
# DVSwitch dashboard posture). All inputs are validated against allowlists.

DVS_SWITCH="/opt/MMDVM_Bridge/dvswitch.sh"
ANALOG_INI="/opt/Analog_Bridge/Analog_Bridge.ini"
DMR_INI="/opt/DMRGateway/DMRGateway.ini"

# --- helpers ---
json_escape() {
  # Escape for JSON string (basic: backslash, quote, newline)
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\n' ' ' | sed 's/  */ /g'
}

urldecode() {
  printf '%b' "${1//%/\\x}"
}

get_param() {
  # $1 = param name; reads from QUERY_STRING
  local name="$1"
  printf '%s' "$QUERY_STRING" | tr '&' '\n' | grep "^${name}=" | head -1 | cut -d= -f2- | { read -r v; urldecode "$v"; }
}

svc_state() {
  # $1 = service name -> active|inactive|unknown
  if systemctl is-active --quiet "$1" 2>/dev/null; then
    printf 'active'
  else
    printf 'inactive'
  fi
}

current_mode() {
  # Analog_Bridge.ini [AMBE] mode or similar; fall back to dvswitch.sh status
  # Try to read the mode from the ini
  local m
  m=$(grep -i "^mode" "$ANALOG_INI" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' ')
  if [[ -n "$m" ]]; then
    printf '%s' "$m"
  else
    printf 'DMR'
  fi
}

current_tune() {
  # The tuned TG is in Analog_Bridge.ini as txTG. Strip comments (;) and whitespace.
  local t
  t=$(grep -iE "^txTG" "$ANALOG_INI" 2>/dev/null | head -1 | cut -d= -f2 | cut -d';' -f1 | tr -d ' ')
  # Validate it's numeric; otherwise return empty
  if [[ "$t" =~ ^[0-9]+$ ]]; then
    printf '%s' "$t"
  else
    printf ''
  fi
}

tune_alias() {
  case "$1" in
    4000777) printf 'TGIF 777 (scan)' ;;
    7003120) printf 'KS-DMR 3120 (Kansas)' ;;
    91)      printf 'BM 91 Worldwide' ;;
    93)      printf 'BM 93 North America' ;;
    3100)    printf 'BM 3100 USA' ;;
    3120)    printf 'BM 3120 Kansas' ;;
    4000)    printf 'Disconnect' ;;
    *)       printf '' ;;
  esac
}

scan_source() {
  # Parse the latest "Scan rewrite: TG X -> Y" from dmrgateway journal
  # Returns the real source TG (X)
  journalctl -u dmrgateway --no-pager -n 200 2>/dev/null \
    | grep "Scan rewrite:" \
    | tail -1 \
    | sed -n 's/.*Scan rewrite: TG \([0-9]*\) -> .*/\1/p'
}

recent_log() {
  journalctl -u dmrgateway --no-pager -n 15 2>/dev/null \
    | grep -v "Scan rewrite:" \
    | tail -8
}

# --- actions ---
do_status() {
  local mode tune alias scan svc_dmr svc_mmdvm svc_ab log
  mode=$(current_mode)
  tune=$(current_tune)
  alias=$(tune_alias "$tune")
  scan=$(scan_source)
  svc_dmr=$(svc_state dmrgateway)
  svc_mmdvm=$(svc_state mmdvm_bridge)
  svc_ab=$(svc_state analog_bridge)
  log=$(recent_log)

  printf '{'
  printf '"mode":"%s",' "$(json_escape "$mode")"
  printf '"tune":"%s",' "$(json_escape "$tune")"
  printf '"tune_alias":"%s",' "$(json_escape "$alias")"
  printf '"scan_src":"%s",' "$(json_escape "$scan")"
  printf '"services":{"dmrgateway":"%s","mmdvm_bridge":"%s","analog_bridge":"%s"},' \
    "$svc_dmr" "$svc_mmdvm" "$svc_ab"
  printf '"log":"%s"' "$(json_escape "$log")"
  printf '}'
}

do_tune() {
  local tgid
  tgid=$(get_param tgid)
  # Validate: 1-7 digit number only
  if ! [[ "$tgid" =~ ^[0-9]{1,7}$ ]]; then
    printf '{"ok":false,"error":"Invalid TGID"}'
    return
  fi
  if [[ ! -x "$DVS_SWITCH" ]]; then
    printf '{"ok":false,"error":"dvswitch.sh not found"}'
    return
  fi
  # NOTE: the DVSwitch chain (dvswitch.sh tune -> MMDVM_Bridge) always emits
  # group-call frames; there is no per-tune group/private switch. Service
  # TGs that require a real private call (BM Parrot 9990) are converted by
  # the DMRGateway private-call patch (scripts/dmrgateway-private-call.patch).
  if sudo "$DVS_SWITCH" tune "$tgid" >/dev/null 2>&1; then
    printf '{"ok":true,"tgid":"%s"}' "$tgid"
  else
    printf '{"ok":false,"error":"tune command failed"}'
  fi
}

do_mode() {
  local mode
  mode=$(get_param mode)
  case "$mode" in
    DMR|YSF|P25|NXDN|DSTAR) ;;
    *) printf '{"ok":false,"error":"Invalid mode"}'; return ;;
  esac
  if [[ ! -x "$DVS_SWITCH" ]]; then
    printf '{"ok":false,"error":"dvswitch.sh not found"}'
    return
  fi
  if sudo "$DVS_SWITCH" mode "$mode" >/dev/null 2>&1; then
    printf '{"ok":true,"mode":"%s"}' "$mode"
  else
    printf '{"ok":false,"error":"mode command failed"}'
  fi
}

# --- main ---
printf 'Content-Type: application/json\r\n'
printf 'Cache-Control: no-cache\r\n'
printf '\r\n'

action=$(get_param action)
case "$action" in
  status) do_status ;;
  tune)   do_tune ;;
  mode)   do_mode ;;
  *)      printf '{"ok":false,"error":"Unknown action"}' ;;
esac

#!/usr/bin/env bash
# dvswitch-control.sh -- CGI backend for the KF0RIZ digital control panel.
#
# Install: sudo cp dvswitch-control.sh /var/www/cgi-bin/ (or /usr/lib/cgi-bin/)
#          sudo chmod 755 /var/www/cgi-bin/dvswitch-control.sh
# Apache needs: ScriptAlias /cgi-bin/ /var/www/cgi-bin/ + ExecCGI
#
# Actions (via ?action=):
#   status  -> JSON: mode, tune, tune_alias, services, scan_src, log
#   tune    -> ?tgid=NNNN[&for_mode=YSF] : run dvswitch.sh tune <tgid>;
#              for_mode declares which mode the value belongs to (the dashboard
#              tune card knows); when it disagrees with the node's live mode
#              the mode is switched first so the tune lands correctly.
#   mode    -> ?mode=DMR|YSF|P25|NXDN|DSTAR : mode-switch.sh (fixes Analog_Bridge
#              [AMBE_AUDIO] TLV ports for the target mode from DVSwitch.ini,
#              then runs dvswitch.sh mode <mode>)
#
# Security: LAN-only by Apache config. No auth in script (matches existing
# DVSwitch dashboard posture). All inputs are validated against allowlists.

DVS_SWITCH="/opt/MMDVM_Bridge/dvswitch.sh"
ANALOG_INI="/opt/Analog_Bridge/Analog_Bridge.ini"
DMR_INI="/opt/DMRGateway/DMRGateway.ini"
# Privileged mode-switch helper (installed beside this CGI by install.sh).
# Fixes Analog_Bridge's [AMBE_AUDIO] TLV ports for the target mode before
# dvswitch.sh runs -- dvswitch.sh leaves them on the previous mode's values,
# which silently breaks the Analog_Bridge -> MMDVM_Bridge handoff.
MODE_SWITCH="$(dirname "$0" 2>/dev/null)/mode-switch.sh"
[[ -x "$MODE_SWITCH" ]] || MODE_SWITCH="/var/www/cgi-bin/mode-switch.sh"

# --- helpers ---
json_escape() {
  # Escape for JSON string (basic: backslash, quote, newline). Tabs and other
  # control chars are flattened to spaces: a literal TAB inside a JSON string
  # is invalid JSON and makes the browser's r.json() throw (this is what made
  # the P25/NXDN dropdowns silently fall back to the short hardcoded list).
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr '\t\n\r' '   ' | sed 's/  */ /g'
}

urldecode() {
  # URLSearchParams encodes space as '+'; convert before %XX decoding
  local s="${1//+/ }"
  printf '%b' "${s//%/\\x}"
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
  # Read the LIVE mode the same way dvswitch.sh does ("dvswitch.sh mode" with
  # no args -> getABInfoValue tlv ambe_mode). Analog_Bridge writes
  # /tmp/ABInfo_*.json and updates tlv.ambe_mode on every mode change, so this
  # reflects reality. (The ini has no mode= line; grepping it always fell back
  # to DMR, which made the UI "jump back to DMR" on every refresh.)
  local f m
  f=$(ls -t /tmp/ABInfo_*.json 2>/dev/null | head -1)
  if [[ -n "$f" && -r "$f" ]]; then
    m=$(python3 -c 'import json,sys
try:
  d = json.load(open(sys.argv[1]))
  print(d.get("tlv", {}).get("ambe_mode", ""))
except Exception:
  print("")' "$f" 2>/dev/null)
  fi
  case "${m^^}" in
    YSF|YSFN|YSFW) printf 'YSF' ;;
    DMR)   printf 'DMR' ;;
    P25)   printf 'P25' ;;
    NXDN)  printf 'NXDN' ;;
    DSTAR) printf 'DSTAR' ;;
    *)     printf '' ;;   # unknown / Analog_Bridge not running: highlight nothing
  esac
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
    *)
      # A 7-digit value that is not a dial string (4xxxxxx/7xxxxxx) is a DMR
      # ID, not a talkgroup (Analog_Bridge defaults txTG to the DMR ID).
      if [[ "$1" =~ ^[0-9]{7}$ ]] && ! [[ "$1" =~ ^[47] ]]; then
        printf 'not a talkgroup (DMR ID?) — tune below'
      else
        printf ''
      fi
      ;;
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
  local tgid tune_re mode tune_val for_mode live_mode mode_switched waited
  tgid=$(get_param tgid)
  for_mode=$(get_param for_mode)
  # Validate: 1-12 chars, alphanumeric/dash, spaces allowed after the first
  # char (reflector names like "M17-001 A" contain a space; DMR TGs are
  # numeric). The value is passed quoted to dvswitch.sh, so a space is safe.
  # The regex lives in a variable: [[ =~ ]] misparses a literal space in a
  # bracket expression, but a variable-held pattern is treated as one regex.
  # (Dash stays last in each class: "9- " would be an invalid reversed range.)
  tune_re='^[A-Za-z0-9-][A-Za-z0-9 -]{0,11}$'
  if ! [[ "$tgid" =~ $tune_re ]]; then
    printf '{"ok":false,"error":"Invalid tune value"}'
    return
  fi
  # Optional intended mode, supplied by the dashboard's mode-specific tune
  # card (it knows which mode its value belongs to). Allowlisted.
  case "$for_mode" in
    DMR|YSF|P25|NXDN|DSTAR|M17) ;;
    "") ;;
    *) printf '{"ok":false,"error":"Invalid for_mode"}'; return ;;
  esac
  if [[ ! -x "$DVS_SWITCH" ]]; then
    printf '{"ok":false,"error":"dvswitch.sh not found"}'
    return
  fi
  live_mode=$(current_mode)
  mode_switched=false
  if [[ -n "$for_mode" && "$for_mode" != "$live_mode" ]]; then
    # The tune card's mode and the node's live mode disagree. The mode-button
    # tap is async and a failed/lagging switch used to make the tune below
    # silently land in the wrong mode (e.g. a YSF value tuned while the node
    # was still in DMR). Switch first so the tune goes to the right place.
    # switch_mode also repairs Analog_Bridge's TLV ports for the target mode
    # (dvswitch.sh alone leaves them stale -- the Oct 16 YSF outage).
    if ! switch_mode "$for_mode"; then
      printf '{"ok":false,"error":"mode switch to %s failed"}' "$for_mode"
      return
    fi
    mode_switched=true
    # Wait for the switch to take effect (Analog_Bridge reconfigures); fail
    # loudly instead of tuning blindly into the wrong mode.
    waited=0
    while [[ "$(current_mode)" != "$for_mode" && $waited -lt 10 ]]; do
      sleep 1; waited=$((waited+1))
    done
    if [[ "$(current_mode)" != "$for_mode" ]]; then
      printf '{"ok":false,"error":"mode switch to %s did not take effect (node still reports %s)"}' \
        "$for_mode" "$(current_mode)"
      return
    fi
  fi
  # Effective mode for value conversion: explicit intent wins, else live mode.
  mode="${for_mode:-$live_mode}"
  # YSF/FCS tune format -- documented DVSwitch convention (DVSwitch forum
  # msg 1666362428180938016; ASL3 DTMF dialplan: [ysf] tune 8${EXTEN},
  # [fcs] tune 9${EXTEN}):
  #   YSF reflector: prepend 8 (e.g., 41729 -> 841729)
  #   FCS room: prepend 9 (e.g., FCS00155 -> 900155)
  # The dashboard shows "FCS00155" but dvswitch.sh needs "900155".
  tune_val="$tgid"
  if [[ "$mode" == "YSF" ]]; then
    if [[ "$tgid" =~ ^[Ff][Cc][Ss]([0-9]+)$ ]]; then
      # FCS00155 -> 900155
      tune_val="9${BASH_REMATCH[1]}"
    elif [[ "$tgid" =~ ^[0-9]{5}$ ]]; then
      # 5-digit YSF reflector ID -> prepend 8
      tune_val="8${tgid}"
    fi
  fi
  # NOTE: the DVSwitch chain (dvswitch.sh tune -> MMDVM_Bridge) always emits
  # group-call frames; there is no per-tune group/private switch. Service
  # TGs that require a real private call (BM Parrot 9990) are converted by
  # the DMRGateway private-call patch (scripts/dmrgateway-private-call.patch).
  if sudo "$DVS_SWITCH" tune "$tune_val" >/dev/null 2>&1; then
    printf '{"ok":true,"tgid":"%s","tuned_as":"%s","mode_switched":%s}' \
      "$tgid" "$tune_val" "$mode_switched"
  else
    printf '{"ok":false,"error":"tune command failed"}'
  fi
}

switch_mode() {
  # $1 = mode (already allowlisted by the caller). Runs the privileged
  # mode-switch helper (TLV port fix + dvswitch.sh mode); falls back to plain
  # dvswitch.sh if the helper isn't installed yet OR sudo rejects it (stale
  # sudoers from before the helper existed). Returns 0 on success.
  # Sets SWITCH_TLV_FIXED (1/0) and SWITCH_TLV_NOTE for the JSON response.
  local mode="$1" out rc k v
  SWITCH_TLV_FIXED=0; SWITCH_TLV_NOTE=""
  if [[ -x "$MODE_SWITCH" ]]; then
    out=$(sudo "$MODE_SWITCH" "$mode" 2>/dev/null); rc=$?
    if [[ $rc -ne 0 && -z "$out" ]]; then
      # Helper always prints fixed=/note= lines, even on failure -- empty
      # output means sudo itself refused (stale sudoers). Legacy path keeps
      # mode switching working until install.sh is re-run.
      sudo "$DVS_SWITCH" mode "$mode" >/dev/null 2>&1; rc=$?
      SWITCH_TLV_NOTE="mode-switch helper not permitted by sudoers; TLV ports not verified (re-run install.sh)"
      return "$rc"
    fi
    while IFS='=' read -r k v; do
      case "$k" in
        fixed) SWITCH_TLV_FIXED="$v" ;;
        note)  SWITCH_TLV_NOTE="$v" ;;
      esac
    done <<< "$out"
  else
    sudo "$DVS_SWITCH" mode "$mode" >/dev/null 2>&1; rc=$?
    SWITCH_TLV_NOTE="mode-switch helper not installed; TLV ports not verified"
  fi
  return "$rc"
}

do_mode() {
  local mode tlv_fixed
  mode=$(get_param mode)
  case "$mode" in
    DMR|YSF|P25|NXDN|DSTAR|M17) ;;
    *) printf '{"ok":false,"error":"Invalid mode"}'; return ;;
  esac
  if [[ ! -x "$DVS_SWITCH" ]]; then
    printf '{"ok":false,"error":"dvswitch.sh not found"}'
    return
  fi
  if switch_mode "$mode"; then
    tlv_fixed=false
    [[ "$SWITCH_TLV_FIXED" == "1" ]] && tlv_fixed=true
    printf '{"ok":true,"mode":"%s","tlv_fixed":%s' "$mode" "$tlv_fixed"
    [[ -n "$SWITCH_TLV_NOTE" ]] && printf ',"tlv_note":"%s"' "$(json_escape "$SWITCH_TLV_NOTE")"
    printf '}'
  else
    printf '{"ok":false,"error":"mode command failed"}'
  fi
}

find_hostfile() {
  # $1 = keyword (lowercase, e.g. "p25"); remaining args = exact basenames to
  # try first (e.g. P25Hosts.txt P25_Hosts.txt).
  # Returns the first readable match in the common DVSwitch locations. If no
  # exact name hits, scans those directories for any readable *.txt whose name
  # contains the keyword -- handles installs where the files are named or
  # cased differently (P25/NXDN/M17 lists were reported missing even with the
  # exact names in the search list).
  local kw="$1"; shift
  local base d f
  for d in /var/lib/mmdvm /usr/local/etc /var/lib/dvswitch /opt/MMDVM_Bridge \
           /opt/dvswitch /usr/local/etc/dvswitch /etc/dvswitch; do
    for base in "$@"; do
      if [[ -r "$d/$base" ]]; then
        printf '%s' "$d/$base"
        return 0
      fi
    done
  done
  for d in /var/lib/mmdvm /usr/local/etc /var/lib/dvswitch /opt/MMDVM_Bridge \
           /opt/dvswitch /usr/local/etc/dvswitch /etc/dvswitch; do
    [[ -d "$d" ]] || continue
    for f in "$d"/*; do
      [[ -f "$f" && -r "$f" ]] || continue
      case "$(basename "$f" | tr 'A-Z' 'a-z')" in
        *"$kw"*.txt) printf '%s' "$f"; return 0 ;;
      esac
    done
  done
  return 1
}

do_reflectors_web() {
  # $1 = mode (lowercase). Fetch from DVRef API, cache 24h in /tmp.
  # Returns JSON list or empty list on failure.
  local mode="$1" cache="/tmp/dvswitch-reflectors-${mode}.json" url json
  # Serve from cache if fresh (<24h)
  if [[ -f "$cache" ]] && [[ $(($(date +%s) - $(stat -c %Y "$cache" 2>/dev/null || echo 0))) -lt 86400 ]]; then
    json=$(cat "$cache" 2>/dev/null)
    if [[ -n "$json" ]]; then
      printf '{"ok":true,"reflectors":%s,"source":"dvref-cache"}' "$json"
      return
    fi
  fi
  # DVRef API endpoints (from Pi-Star host file headers)
  case "$mode" in
    ysf)  url="https://dvref.com/api/v2/ysf/reflectors/" ;;
    p25)  url="https://dvref.com/api/v2/p25/reflectors/" ;;
    nxdn) url="https://dvref.com/api/v2/nxdn/reflectors/" ;;
    m17)  url="https://dvref.com/api/v2/m17/reflectors/" ;;
    *) printf '{"ok":true,"reflectors":[]}'; return ;;
  esac
  # Fetch with callsign headers (required by DVRef)
  json=$(curl -s --max-time 15 -H "X-DVRef-Callsign: KF0RIZ" \
    -H "X-DVRef-Contact: KF0RIZ" "$url" 2>/dev/null | \
    python3 -c '
import json,sys
try:
  d = json.load(sys.stdin)
  refs = d.get("data", {}).get("reflectors", [])
  out = []
  for r in refs[:300]:
    rid = str(r.get("designator", ""))
    name = r.get("name") or r.get("slug") or rid
    if rid:
      out.append({"id": rid, "name": name})
  print(json.dumps(out))
except Exception:
  print("[]")
' 2>/dev/null)
  if [[ -n "$json" && "$json" != "[]" ]]; then
    printf '%s' "$json" > "$cache" 2>/dev/null
    printf '{"ok":true,"reflectors":%s,"source":"dvref"}' "$json"
  else
    printf '{"ok":true,"reflectors":[]}'
  fi
}

do_reflectors() {
  # ?mode=ysf|p25|nxdn|dstar|m17 -> JSON list from the node's host files,
  # falling back to the DVRef API (cached 24h in /tmp) if not found locally.
  local mode f line id name count=0 first=1
  mode=$(get_param mode | tr 'A-Z' 'a-z')
  case "$mode" in
    ysf)   f=$(find_hostfile "ysf"   "YSFHosts.txt")
           # Also try FCS rooms (separate file, same directory)
           fcs=$(find_hostfile "fcs" "FCSRooms.txt")
           ;;
    p25)   f=$(find_hostfile "p25"   "P25Hosts.txt" "P25_Hosts.txt") ;;
    nxdn)  f=$(find_hostfile "nxdn"  "NXDNHosts.txt" "NXDN_Hosts.txt") ;;
    m17)   f=$(find_hostfile "m17"   "M17Hosts.txt" "M17_Hosts.txt") ;;
    dstar)
      # D-STAR has three host files; DPlus (REF) is the primary list
      f=$(find_hostfile "dplus" "DPlus_Hosts.txt" "DExtra_Hosts.txt" "DCS_Hosts.txt")
      ;;
    *) printf '{"ok":false,"error":"Invalid mode"}'; return ;;
  esac
  # For YSF, merge FCS rooms into the list if found
  if [[ "$mode" == "ysf" && -n "$fcs" && "$fcs" != "$f" ]]; then
    # We'll append FCS entries after the YSF ones in the output loop
    fcs_file="$fcs"
  else
    fcs_file=""
  fi
  if [[ -z "$f" && -z "$fcs_file" ]]; then
    # No local host file and no FCS file -- try the DVRef API (cached 24h)
    do_reflectors_web "$mode"
    return
  fi
  # If we have FCS but no YSF hosts file, use /dev/null for the YSF loop
  # (the FCS append loop below will still run)
  if [[ -z "$f" ]]; then
    f="/dev/null"
  fi
  printf '{"ok":true,"reflectors":['
  # Per-mode data-line formats (verified against the live Pi-Star/dvref files):
  #   YSFHosts.txt : "designator;name;description;host;port;000;" (semicolons)
  #   P25Hosts.txt / NXDNHosts.txt : "designator<TAB>host<TAB>port" (Pi-Star
  #     header literally says "# Format: designator<TAB>host<TAB>port"; there
  #     is NO name column, so the host is shown as the label). The old code
  #     parsed these as semicolon-separated, which stuffed literal TABs into
  #     the JSON ids -> invalid JSON -> the page silently fell back to the
  #     short hardcoded list.
  #   D-STAR host files : "REF001C  address" (whitespace separated)
  while IFS= read -r line && [[ $count -lt 300 ]]; do
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "${line//[[:space:]]/}" ]] && continue
    case "$mode" in
      ysf)
        id=$(printf '%s' "$line" | cut -d';' -f1 | sed 's/^ *//;s/ *$//')
        name=$(printf '%s' "$line" | cut -d';' -f2 | sed 's/^ *//;s/ *$//')
        ;;
      p25|nxdn)
        id=$(printf '%s' "$line" | awk '{print $1}')
        name=$(printf '%s' "$line" | awk '{print $2}')
        ;;
      *)
        id=$(printf '%s' "$line" | awk '{print $1}')
        name="$id"
        ;;
    esac
    [[ -z "$id" ]] && continue
    [[ -z "$name" ]] && name="$id"
    if [[ $first -eq 1 ]]; then first=0; else printf ','; fi
    printf '{"id":"%s","name":"%s"}' "$(json_escape "$id")" "$(json_escape "$name")"
    count=$((count+1))
  done < "$f"
  # Append FCS rooms for YSF mode (separate file, e.g. FCS00155)
  if [[ -n "$fcs_file" && -r "$fcs_file" ]]; then
    while IFS= read -r line && [[ $count -lt 400 ]]; do
      [[ "$line" =~ ^#.*$ ]] && continue
      [[ -z "${line//[[:space:]]/}" ]] && continue
      # FCSRooms.txt: try "FCS00155;Name;..." or "FCS00155 Name" formats
      if [[ "$line" == *";"* ]]; then
        id=$(printf '%s' "$line" | cut -d';' -f1 | sed 's/^ *//;s/ *$//')
        name=$(printf '%s' "$line" | cut -d';' -f2 | sed 's/^ *//;s/ *$//')
      else
        id=$(printf '%s' "$line" | awk '{print $1}')
        name=$(printf '%s' "$line" | awk '{print $2}')
      fi
      [[ -z "$id" ]] && continue
      [[ -z "$name" ]] && name="$id"
      # Prefix with FCS if not already (some files list just the number)
      if ! [[ "$id" =~ ^FCS ]]; then
        id="FCS${id}"
      fi
      if [[ $first -eq 1 ]]; then first=0; else printf ','; fi
      printf '{"id":"%s","name":"%s"}' "$(json_escape "$id")" "$(json_escape "$name")"
      count=$((count+1))
    done < "$fcs_file"
  fi
  printf ']}'
}

# --- main ---
printf 'Content-Type: application/json\r\n'
printf 'Cache-Control: no-cache\r\n'
printf '\r\n'

action=$(get_param action)
case "$action" in
  status)     do_status ;;
  tune)       do_tune ;;
  mode)       do_mode ;;
  reflectors) do_reflectors ;;
  *)          printf '{"ok":false,"error":"Unknown action"}' ;;
esac

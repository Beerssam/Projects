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
# Privileged gain helper (installed beside this CGI by install.sh). The CGI
# runs as www-data and may not edit Analog_Bridge.ini or restart services
# directly -- the sudoers rule permits only this helper (same pattern as
# mode-switch.sh). Without it, gain writes were silently refused and the
# sliders always snapped back to the ini values (found Oct 21 2026).
GAIN_SET="$(dirname "$0" 2>/dev/null)/gain-set.sh"
[[ -x "$GAIN_SET" ]] || GAIN_SET="/var/www/cgi-bin/gain-set.sh"
# Privileged network-status helper (same pattern): reads the DMRGateway
# journal, which www-data cannot, and reports BM/TGIF/KS-DMR login state.
NET_STATUS="$(dirname "$0" 2>/dev/null)/net-status.sh"
[[ -x "$NET_STATUS" ]] || NET_STATUS="/var/www/cgi-bin/net-status.sh"
# Privileged M17 bridge helper (same pattern): controls the USRP2M17 bridge
# (reflector switching, connect/disconnect, node-1998 link) -- M17 is NOT a
# DVSwitch mode (no version of DVSwitch has it), so it lives outside the
# mode/tune machinery entirely. See allstar-dmr/m17/DESIGN.md.
M17_SWITCH="$(dirname "$0" 2>/dev/null)/m17-switch.sh"
[[ -x "$M17_SWITCH" ]] || M17_SWITCH="/var/www/cgi-bin/m17-switch.sh"
# USRP2M17 config (env override for testing). Read directly by the CGI for
# status display; only the helper may write it.
M17_INI="${M17_INI:-/etc/USRP2M17.ini}"
# MMDVM_Bridge log directory (env override for testing). The bridge logs
# real in/out transmissions to files here; unlike the systemd journal,
# these are readable by www-data.
BRIDGE_LOG_DIR="${BRIDGE_LOG_DIR:-/var/log/mmdvm}"

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
    M17)   printf 'M17' ;;
    *)     printf '' ;;   # unknown / Analog_Bridge not running: highlight nothing
  esac
}

abinfo_file() {
  ls -t /tmp/ABInfo_*.json 2>/dev/null | head -1
}

abinfo_value() {
  # $1 = dotted path into the ABInfo JSON (e.g. digital.tg, last_tune).
  # Prints the string value or nothing. Analog_Bridge rewrites this file
  # on every state change, so it reflects live state (the ini does not).
  local f
  f=$(abinfo_file)
  [[ -n "$f" && -r "$f" ]] || return 0
  python3 -c 'import json,sys
try:
  d = json.load(open(sys.argv[1]))
  for k in sys.argv[2].split("."):
    d = d.get(k, {}) if isinstance(d, dict) else {}
  print(d if isinstance(d, str) else "")
except Exception:
  print("")' "$f" "$1" 2>/dev/null
}

bridge_log_files() {
  # Newest first. MMDVM_Bridge logs real in/out transmissions here.
  ls -t "$BRIDGE_LOG_DIR"/MMDVM_Bridge-*.log 2>/dev/null | head -2
}

last_tx_dst() {
  # Destination of the most recent outbound transmission in the bridge log.
  local f dst
  while IFS= read -r f; do
    dst=$(grep -a "Begin TX:" "$f" 2>/dev/null | tail -1 | sed -n 's/.*dst=\([0-9][0-9]*\).*/\1/p')
    if [[ -n "$dst" ]]; then printf '%s' "$dst"; return; fi
  done < <(bridge_log_files)
  printf ''
}

current_tune() {
  # Best available "current TG", in order:
  #   1. ABInfo last_tune (Analog_Bridge's record of the last tune)
  #   2. Destination of the last transmission in the bridge log
  #   3. Analog_Bridge.ini txTG (startup default)
  #   4. ABInfo digital.tg (equals the node's own DMR ID at idle; the
  #      alias text explains that case instead of calling it a talkgroup)
  # The old code read only the ini, so Current sat at the DMR ID (3209686)
  # and never reflected traffic (Sam's report, Oct 21 2026; ABInfo on the
  # node confirmed digital.tg is the ID whenever the node is idle).
  local t
  t=$(abinfo_value last_tune)
  if [[ "$t" =~ ^[0-9]+$ ]]; then printf '%s' "$t"; return; fi
  t=$(last_tx_dst)
  if [[ -n "$t" ]]; then printf '%s' "$t"; return; fi
  t=$(grep -iE "^[[:space:]]*txTG[[:space:]]*=" "$ANALOG_INI" 2>/dev/null | head -1 | cut -d= -f2 | cut -d';' -f1 | tr -d ' ')
  if [[ "$t" =~ ^[0-9]+$ ]]; then printf '%s' "$t"; return; fi
  t=$(abinfo_value digital.tg)
  if [[ "$t" =~ ^[0-9]+$ ]]; then printf '%s' "$t"; return; fi
  printf ''
}

tune_alias() {
  # $1 = tune value; $2 = gateway DMR ID (ABInfo digital.gw), may be empty
  case "$1" in
    4000777) printf 'TGIF 777 (scan)' ;;
    7003120) printf 'KS-DMR 3120 (Kansas)' ;;
    91)      printf 'BM 91 Worldwide' ;;
    93)      printf 'BM 93 North America' ;;
    3100)    printf 'BM 3100 USA' ;;
    3120)    printf 'BM 3120 Kansas' ;;
    9990)    printf 'BM Parrot (private)' ;;
    4000)    printf 'Disconnect' ;;
    *)
      if [[ -n "$2" && "$1" == "$2" ]]; then
        # The value is the node's own DMR ID: Analog_Bridge idles there.
        printf 'Standby — showing your DMR ID, tune below'
      elif [[ "$1" =~ ^4[0-9]{6}$ ]]; then
        printf 'TGIF TG %s' "$((10#${1:1}))"
      elif [[ "$1" =~ ^7[0-9]{6}$ ]]; then
        printf 'KS-DMR TG %s' "$((10#${1:1}))"
      elif [[ "$1" =~ ^[0-9]{7}$ ]]; then
        # A 7-digit value that is not a dial string (4xxxxxx/7xxxxxx) is a
        # DMR ID, not a talkgroup.
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

recent_activity() {
  # Recent in/out transmissions from the MMDVM_Bridge log files. (The
  # journal is not readable by www-data -- verified on the node Oct 21
  # 2026: "No journal files were opened due to insufficient permissions" --
  # so the old journal-based activity feed was always empty.) Prints a JSON
  # array of display strings, newest first, max 8. Log timestamps are UTC;
  # displayed in node-local time.
  local -a files
  mapfile -t files < <(bridge_log_files)
  if [[ ${#files[@]} -eq 0 ]]; then printf '[]'; return; fi
  python3 - "${files[@]}" <<'PYEOF'
import json, re, sys
from datetime import datetime, timezone

TX_BEGIN = re.compile(r"^.: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ (\w+), Begin TX: src=(\S+) rpt=\S+ dst=(\S+) slot=\d+(?: .*metadata=(\S+))?")
RX_HEAD = re.compile(r"^.: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ (\w+)(?: Slot \d+)?, received network voice header from (\S+) to (?:TG )?(\S+)")
RX_END = re.compile(r"received network end of voice transmission, ([\d.]+) seconds")
TX_OFF = re.compile(r"TX state = OFF, DMR frame count was (\d+) frames")
TX_RF_END = re.compile(r"received RF end of transmission, ([\d.]+) seconds")

def epoch(ts):
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()

events = []
try:
    for path in reversed(sys.argv[1:]):
        try:
            with open(path, errors="replace") as fh:
                lines = fh.readlines()[-4000:]
        except OSError:
            continue
        last_tx = None
        last_rx = None
        for line in lines:
            m = TX_BEGIN.match(line)
            if m:
                ts, mode, src, dst, meta = m.groups()
                ep = epoch(ts)
                who = meta or src
                if mode != "DMR":
                    who = "%s %s" % (mode, who)
                ev = [ep, "%s TX %s \u2192 %s" % (datetime.fromtimestamp(ep).strftime("%H:%M"), who, dst)]
                events.append(ev)
                last_tx, last_rx = ev, None
                continue
            m = RX_HEAD.match(line)
            if m:
                ts, mode, frm, to = m.groups()
                ep = epoch(ts)
                if mode != "DMR":
                    frm = "%s %s" % (mode, frm)
                ev = [ep, "%s RX %s \u2192 %s" % (datetime.fromtimestamp(ep).strftime("%H:%M"), frm, to)]
                events.append(ev)
                last_rx, last_tx = ev, None
                continue
            m = RX_END.search(line)
            if m and last_rx is not None:
                last_rx[1] += " \u00b7 %gs" % float(m.group(1))
                last_rx = None
                continue
            m = TX_OFF.search(line)
            if m and last_tx is not None:
                secs = round(int(m.group(1)) / 16.67)
                if secs >= 1:
                    last_tx[1] += " \u00b7 ~%ds" % secs
                last_tx = None
                continue
            m = TX_RF_END.search(line)
            if m and last_tx is not None:
                last_tx[1] += " \u00b7 %gs" % float(m.group(1))
                last_tx = None
except Exception:
    events = []

events.sort(key=lambda e: e[0])
print(json.dumps([label for _ep, label in reversed(events[-8:])]))
PYEOF
}

live_state() {
  # Live TX/RX state for the dashboard lamps, from the newest bridge log:
  # a direction is "on" when its latest begin line has no matching end
  # line after it and began within the last 300s (staleness guard against
  # a missed end line sticking a lamp on). Prints a JSON object.
  local -a files
  mapfile -t files < <(bridge_log_files)
  if [[ ${#files[@]} -eq 0 ]]; then printf '{"tx_on":false,"tx_label":"","rx_on":false,"rx_label":""}'; return; fi
  python3 - "${files[0]}" <<'PYEOF'
import json, re, sys, time
from datetime import datetime, timezone

TX_BEGIN = re.compile(r"^.: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ (\w+), Begin TX: src=(\S+) rpt=\S+ dst=(\S+) slot=\d+(?: .*metadata=(\S+))?")
RX_HEAD = re.compile(r"^.: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ (\w+)(?: Slot \d+)?, received network voice header from (\S+) to (?:TG )?(\S+)")
TX_END = re.compile(r"TX state = OFF|received RF end of transmission")
RX_END = re.compile(r"received network end of voice transmission")

def epoch(ts):
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()

tx = {"begin": 0, "end": 0, "label": ""}
rx = {"begin": 0, "end": 0, "label": ""}
try:
    with open(sys.argv[1], errors="replace") as fh:
        lines = fh.readlines()[-800:]
    for line in lines:
        m = TX_BEGIN.match(line)
        if m:
            ts, mode, src, dst, meta = m.groups()
            tx["begin"] = epoch(ts)
            tx["label"] = "%s %s \u2192 %s" % (mode, meta or src, dst)
            continue
        if TX_END.search(line):
            # No timestamp needed: any end after the last begin closes it;
            # ordering is by file position, so record it positionally.
            if tx["begin"]:
                tx["end"] = tx["begin"] + 0.5
            continue
        m = RX_HEAD.match(line)
        if m:
            ts, mode, frm, to = m.groups()
            rx["begin"] = epoch(ts)
            rx["label"] = "%s %s \u2192 %s" % (mode, frm, to)
            continue
        if RX_END.search(line):
            if rx["begin"]:
                rx["end"] = rx["begin"] + 0.5
except OSError:
    pass

now = time.time()
def on(st):
    return st["begin"] > st["end"] and (now - st["begin"]) <= 300

print(json.dumps({
    # Sam's convention (Oct 22 2026): the lamps speak from the NODE's RF
    # perspective, not the digital network's. When the operator keys up,
    # the node is RECEIVING him -- that is the bridge's "Begin TX" stream
    # (his audio entering the network). When network audio plays out to
    # him, the node is TRANSMITTING -- the bridge's "received network"
    # stream. The fields are deliberately crossed here; do not "fix" back.
    "rx_on": on(tx), "rx_label": tx["label"] if on(tx) else "",
    "tx_on": on(rx), "tx_label": rx["label"] if on(rx) else "",
}))
PYEOF
}

network_states() {
  # Prints the JSON object contents for the "nets" status field: DMR
  # network login states from the net-status helper (or "down" for all
  # three when the gateway itself is not running), plus gateway unit
  # states from systemctl.
  local bm="unknown" bm_ts="" tgif="unknown" tgif_ts="" ks="unknown" ks_ts=""
  local out kv rest k v
  if [[ "$(svc_state dmrgateway)" != "active" ]]; then
    bm="down"; tgif="down"; ks="down"
  elif [[ -x "$NET_STATUS" ]]; then
    out=$(sudo "$NET_STATUS" 2>/dev/null)
    while IFS=' ' read -r kv rest; do
      k="${kv%%=*}"; v="${kv#*=}"
      case "$k" in
        BM)    bm="$v";   bm_ts="$rest" ;;
        TGIF)  tgif="$v"; tgif_ts="$rest" ;;
        KSDMR) ks="$v";   ks_ts="$rest" ;;
      esac
    done <<< "$out"
  fi
  printf '"bm":"%s","bm_ts":"%s","tgif":"%s","tgif_ts":"%s","ksdmr":"%s","ksdmr_ts":"%s","ysf":"%s","p25":"%s","nxdn":"%s","dstar":"%s"' \
    "$bm" "$bm_ts" "$tgif" "$tgif_ts" "$ks" "$ks_ts" \
    "$(svc_state ysfgateway)" "$(svc_state p25gateway)" \
    "$(svc_state nxdngateway)" "$(svc_state ircddbgatewayd)"
}

m17_block() {
  # JSON object contents for the status "m17" field: USRP2M17 service state
  # plus the reflector/module from the ini's [M17 Network] Name line. Cheap
  # (no sudo, no asterisk) so it can ride every status poll; the linked
  # state needs Asterisk and is only in the action=m17 status response.
  local name ref mod
  name=$(grep -E '^[[:space:]]*Name[[:space:]]*=' "$M17_INI" 2>/dev/null | head -1 \
         | cut -d= -f2 | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
  ref="${name%% *}"; mod=""
  [[ "$name" == *" "* ]] && mod="${name##* }"
  printf '"service":"%s","reflector":"%s","module":"%s"' \
    "$(svc_state usrp2m17)" "$(json_escape "$ref")" "$(json_escape "$mod")"
}

# --- actions ---
do_status() {
  local mode tune alias scan svc_dmr svc_mmdvm svc_ab svc_m17 log gw activity nets
  mode=$(current_mode)
  tune=$(current_tune)
  gw=$(abinfo_value digital.gw)
  alias=$(tune_alias "$tune" "$gw")
  scan=$(scan_source)
  activity=$(recent_activity)
  [[ "$activity" == \[* ]] || activity='[]'
  svc_dmr=$(svc_state dmrgateway)
  svc_mmdvm=$(svc_state mmdvm_bridge)
  svc_ab=$(svc_state analog_bridge)
  svc_m17=$(svc_state usrp2m17)
  log=$(recent_log)

  printf '{'
  printf '"mode":"%s",' "$(json_escape "$mode")"
  printf '"tune":"%s",' "$(json_escape "$tune")"
  printf '"tune_alias":"%s",' "$(json_escape "$alias")"
  printf '"scan_src":"%s",' "$(json_escape "$scan")"
  printf '"activity":%s,' "$activity"
  printf '"services":{"dmrgateway":"%s","mmdvm_bridge":"%s","analog_bridge":"%s","usrp2m17":"%s"},' \
    "$svc_dmr" "$svc_mmdvm" "$svc_ab" "$svc_m17"
  nets=$(network_states)
  printf '"nets":{%s},' "$nets"
  printf '"m17":{%s},' "$(m17_block)"
  printf '"log":"%s"' "$(json_escape "$log")"
  printf '}'
}

do_m17() {
  # ?action=m17&op=status|switch|connect|disconnect|link|unlink
  #   switch also takes &name=<reflector>&module=<A-Z>.
  # All work goes through the privileged m17-switch helper, which prints
  # key=value lines; the CGI validates inputs, runs it, and renders the
  # result as JSON -- including honest ok:false on any helper failure.
  local op name module out rc k v
  local service="" reflector="" mod="" address="" port="" linked="" note=""
  op=$(get_param op)
  case "$op" in
    status|switch|connect|disconnect|link|unlink) ;;
    *) printf '{"ok":false,"error":"Invalid m17 op"}'; return ;;
  esac
  if [[ ! -x "$M17_SWITCH" ]]; then
    if [[ "$op" == "status" ]]; then
      # Degraded status without the helper: ini + service state only.
      printf '{"ok":true,"op":"status","m17":{%s},"linked":"unknown","note":"m17 helper not installed - re-run install.sh"}' \
        "$(m17_block)"
      return
    fi
    printf '{"ok":false,"error":"m17 helper not installed - re-run install.sh"}'
    return
  fi
  if [[ "$op" == "switch" ]]; then
    name=$(get_param name)
    module=$(get_param module)
    # The helper re-validates and resolves the address server-side; this
    # allowlist just keeps junk out of the sudo call entirely.
    if ! [[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,23}$ ]]; then
      printf '{"ok":false,"error":"Invalid reflector name"}'; return
    fi
    if ! [[ "$module" =~ ^[A-Z]$ ]]; then
      printf '{"ok":false,"error":"Invalid module (A-Z)"}'; return
    fi
    out=$(sudo "$M17_SWITCH" switch "$name" "$module" 2>/dev/null); rc=$?
  else
    out=$(sudo "$M17_SWITCH" "$op" 2>/dev/null); rc=$?
  fi
  while IFS='=' read -r k v; do
    case "$k" in
      service)   service="$v" ;;
      reflector) reflector="$v" ;;
      module)    mod="$v" ;;
      address)   address="$v" ;;
      port)      port="$v" ;;
      linked)    linked="$v" ;;
      note)      note="$v" ;;
    esac
  done <<< "$out"
  printf '{"ok":%s,"op":"%s","service":"%s","reflector":"%s","module":"%s","address":"%s","port":"%s","linked":"%s","note":"%s"}' \
    "$([[ $rc -eq 0 ]] && echo true || echo false)" "$op" \
    "$(json_escape "$service")" "$(json_escape "$reflector")" \
    "$(json_escape "$mod")" "$(json_escape "$address")" \
    "$(json_escape "$port")" "$(json_escape "$linked")" \
    "$(json_escape "$note")"
}

do_live() {
  local live
  live=$(live_state)
  [[ "$live" == \{* ]] || live='{"tx_on":false,"tx_label":"","rx_on":false,"rx_label":""}'
  printf '%s' "$live"
}

do_tune() {
  local tgid tune_re mode tune_val for_mode live_mode mode_switched waited stable
  local send_epoch attempts verified acked
  tgid=$(get_param tgid)
  for_mode=$(get_param for_mode)
  # from_list=1 means the dashboard value came from the reflector dropdown
  # (not typed manually). Only dropdown values get the YSF 8/9 prefix below;
  # a manually typed value tunes verbatim (Sam's Oct 19 correction: typing
  # 99999 must tune 99999, not be auto-converted to 899999).
  from_list=$(get_param from_list)
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
    # loudly instead of tuning blindly into the wrong mode. Same 2-read
    # stabilization as do_mode: one mid-restart ABInfo write can flap.
    waited=0; stable=0
    while [[ $waited -lt 10 ]]; do
      if [[ "$(current_mode)" == "$for_mode" ]]; then
        stable=$((stable+1)); [[ $stable -ge 2 ]] && break
      else
        stable=0
      fi
      sleep 1; waited=$((waited+1))
    done
    if [[ $stable -lt 2 ]]; then
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
  # Applies ONLY to values picked from the reflector dropdown (from_list=1);
  # manually typed values pass through unchanged.
  tune_val="$tgid"
  if [[ "$mode" == "YSF" && "$from_list" == "1" ]]; then
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
  #
  # Verified tune (Oct 22 2026 -- Sam's tune-sticking report): the tune
  # command is fire-and-forget UDP with no acknowledgement, so a tune sent
  # while the chain is restarting after a mode switch evaporates silently
  # while the page reports success (the Oct 21-22 NXDN case: tune sent 7s
  # after a mode switch never arrived). Send, then verify the tune actually
  # landed: MMDVM_Bridge logs every received remote command
  # ("<MODE>, Remote CMD: txTg=<tg>" -- e.g. "YSF, Remote CMD: txTg=32453",
  # DVSwitch groups.io Aug 2026), or ABInfo digital.tg already reflects the
  # new TG. Retry the send when no ack appears -- this automates Sam's manual
  # "tune it a second time" workaround. ok:true now means the tune was
  # acknowledged, not merely sent.
  # Verification is two-stage (v2, Oct 22): a bridge-log ack alone proved
  # insufficient right after a mode switch -- the bridge acked Sam's first
  # YSF tune within a second, but Analog_Bridge had not engaged it (its
  # network leg had not opened), so the tune only took on a second send.
  # A tune now counts as verified only when AB's own state (ABInfo
  # last_tune / digital.tg) shows it in effect; an acked-but-unengaged
  # tune is resent while attempts remain, which is what engages it.
  send_epoch=$(date -u +%s)
  attempts=0
  verified=false
  acked=false
  while [[ $attempts -lt 3 ]]; do
    attempts=$((attempts+1))
    if ! sudo "$DVS_SWITCH" tune "$tune_val" >/dev/null 2>&1; then
      printf '{"ok":false,"verified":false,"attempts":%d,"error":"tune command failed"}' "$attempts"
      return
    fi
    if tune_ack_wait "$tune_val" "$send_epoch" 8; then
      acked=true
      if tune_endstate_wait "$tune_val" "$tgid" 5; then
        verified=true
        break
      fi
      # Acked but not engaged in AB: fall through and resend.
    fi
    [[ $attempts -lt 3 ]] && sleep 2
  done
  if [[ "$verified" == true ]]; then
    printf '{"ok":true,"verified":true,"attempts":%d,"tgid":"%s","tuned_as":"%s","mode_switched":%s}' \
      "$attempts" "$tgid" "$tune_val" "$mode_switched"
  elif [[ "$acked" == true ]]; then
    printf '{"ok":true,"verified":false,"acked":true,"attempts":%d,"tgid":"%s","tuned_as":"%s","mode_switched":%s}' \
      "$attempts" "$tgid" "$tune_val" "$mode_switched"
  else
    printf '{"ok":false,"verified":false,"attempts":%d,"tgid":"%s","error":"tune sent %d time(s) but MMDVM_Bridge never acknowledged it (no Remote CMD in the bridge log and ABInfo unchanged); the tune probably did not land"}' \
      "$attempts" "$tgid" "$attempts"
  fi
}

tune_endstate_ok() {
  # $1 = tuned value, $2 = raw requested value (may equal $1). True when
  # Analog_Bridge's own state shows the tune in effect: ABInfo last_tune or
  # digital.tg equals either form (a YSF list pick tunes 894122 but AB may
  # record the reflector as 94122). The bridge can acknowledge a tune
  # (Remote CMD in its log) before AB has engaged it -- Sam's Oct 22 YSF
  # case: the bridge acked txTg=99999 at 15:29:23 UTC but the YSF network
  # leg only opened on a second send at :32, and only then did ABInfo move.
  local v
  v=$(abinfo_value last_tune)
  [[ -n "$v" && ( "$v" == "$1" || "$v" == "$2" ) ]] && return 0
  v=$(abinfo_value digital.tg)
  [[ -n "$v" && ( "$v" == "$1" || "$v" == "$2" ) ]] && return 0
  return 1
}

tune_endstate_wait() {
  # $1 = tuned value, $2 = raw value, $3 = max wait seconds. Polls
  # tune_endstate_ok once a second; 0 = the tune is in effect in AB.
  local waited=0
  while [[ $waited -lt ${3:-5} ]]; do
    tune_endstate_ok "$1" "$2" && return 0
    sleep 1; waited=$((waited+1))
  done
  tune_endstate_ok "$1" "$2"
}

tune_ack_wait() {
  # $1 = tune value string, $2 = UTC epoch just before the first send,
  # $3 = max wait seconds. Returns 0 when the tune is verified, by either:
  #   (a) a "Remote CMD:" line containing the value in the MMDVM_Bridge log
  #       with a timestamp at/after the send (MMDVM_Bridge logs every
  #       received remote command), or
  #   (b) ABInfo digital.tg equalling the value (the end state is correct,
  #       however the tune got there).
  # The timestamp guard keeps an older tune to the same value from counting.
  # The value match uses non-alphanumeric boundaries so tuning 91 does not
  # match a stale "txTg=910".
  local val="$1" send_epoch="$2" maxwait="${3:-8}"
  local waited=0 f
  while [[ $waited -lt $maxwait ]]; do
    if [[ "$(abinfo_value digital.tg)" == "$val" ]]; then return 0; fi
    f=$(bridge_log_files | head -1)
    if [[ -n "$f" && -r "$f" ]]; then
      if python3 - "$f" "$send_epoch" "$val" 2>/dev/null <<'PYEOF'
import re, sys
from datetime import datetime, timezone
path, send_epoch, val = sys.argv[1], float(sys.argv[2]), sys.argv[3]
pat = re.compile(r"Remote CMD:.*(?<![A-Za-z0-9])" + re.escape(val) + r"(?![A-Za-z0-9])")
def epoch(ts):
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return -1.0
try:
    with open(path, errors="replace") as fh:
        for line in fh:
            if not pat.search(line):
                continue
            m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if m and epoch(m.group(1)) >= send_epoch - 2:
                sys.exit(0)
except OSError:
    pass
sys.exit(1)
PYEOF
      then
        return 0
      fi
    fi
    sleep 1; waited=$((waited+1))
  done
  return 1
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
  local mode tlv_fixed waited stable
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
    # Don't report success on exit code alone (Oct 22 2026): the chain
    # restarts on a mode switch, and a mode tap sent into that window used
    # to return ok:true while the node stayed on the old mode. Wait for the
    # node to actually report the new mode via ABInfo first.
    # Require the new mode on 2 consecutive reads: a single mid-restart
    # ABInfo write can flap, and confirming on a flap would report success
    # for a mode the node then falls out of.
    waited=0; stable=0
    while [[ $waited -lt 12 ]]; do
      if [[ "$(current_mode)" == "$mode" ]]; then
        stable=$((stable+1)); [[ $stable -ge 2 ]] && break
      else
        stable=0
      fi
      sleep 1; waited=$((waited+1))
    done
    if [[ $stable -lt 2 ]]; then
      printf '{"ok":false,"error":"mode command sent but the node still reports %s after 12s"}' \
        "$(current_mode)"
      return
    fi
    tlv_fixed=false
    [[ "$SWITCH_TLV_FIXED" == "1" ]] && tlv_fixed=true
    printf '{"ok":true,"mode":"%s","tlv_fixed":%s' "$mode" "$tlv_fixed"
    [[ -n "$SWITCH_TLV_NOTE" ]] && printf ',"tlv_note":"%s"' "$(json_escape "$SWITCH_TLV_NOTE")"
    printf '}'
  else
    printf '{"ok":false,"error":"mode command failed"}'
  fi
}

read_gain() {
  # $1 = ini key (tlvGain|usrpGain) -> numeric value or empty
  local v
  v=$(grep -iE "^[[:space:]]*$1[[:space:]]*=" "$ANALOG_INI" 2>/dev/null | head -1 | cut -d= -f2 | cut -d';' -f1 | tr -d ' ')
  if [[ "$v" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then printf '%s' "$v"; else printf ''; fi
}

gain_value_ok() {
  # $1 = candidate value: numeric, 0.0-5.0
  [[ "$1" =~ ^[0-9]+(\.[0-9]+)?$ ]] || return 1
  python3 -c 'import sys; v = float(sys.argv[1]); sys.exit(0 if 0.0 <= v <= 5.0 else 1)' "$1" 2>/dev/null
}

do_gain() {
  # ?action=gain -> {"ok":true,"tlv":"0.25","usrp":"4.00"} (read from ini)
  # ?action=gain&tlv=0.50 -> set via the gain-set helper (the only write
  # path www-data is permitted; it restarts analog_bridge and verifies the
  # read-back), then return the values re-read from the ini -- never just
  # echo the request. A failed write returns ok:false. (The old code ran
  # sudo sed/tee/systemctl directly; sudoers refused all of it and the
  # failure was hidden, so the sliders never saved. Fixed Oct 21 2026.)
  local tlv usrp cur_tlv cur_usrp out
  tlv=$(get_param tlv)
  usrp=$(get_param usrp)
  cur_tlv=$(read_gain tlvGain)
  cur_usrp=$(read_gain usrpGain)
  [[ -z "$cur_tlv" ]] && cur_tlv="1.00"
  [[ -z "$cur_usrp" ]] && cur_usrp="1.00"

  if [[ -n "$tlv" || -n "$usrp" ]]; then
    if [[ ! -x "$GAIN_SET" ]]; then
      printf '{"ok":false,"error":"gain helper not installed - re-run install.sh"}'
      return
    fi
    if [[ -n "$tlv" ]]; then
      if ! gain_value_ok "$tlv"; then
        printf '{"ok":false,"error":"tlv gain must be 0.0-5.0"}'; return
      fi
      out=$(sudo "$GAIN_SET" tlv "$tlv" 2>/dev/null)
      if [[ $? -ne 0 ]]; then
        printf '{"ok":false,"error":"gain-set failed for tlv"}'; return
      fi
      cur_tlv=$(read_gain tlvGain)
      [[ -z "$cur_tlv" ]] && cur_tlv="$tlv"
    fi
    if [[ -n "$usrp" ]]; then
      if ! gain_value_ok "$usrp"; then
        printf '{"ok":false,"error":"usrp gain must be 0.0-5.0"}'; return
      fi
      out=$(sudo "$GAIN_SET" usrp "$usrp" 2>/dev/null)
      if [[ $? -ne 0 ]]; then
        printf '{"ok":false,"error":"gain-set failed for usrp"}'; return
      fi
      cur_usrp=$(read_gain usrpGain)
      [[ -z "$cur_usrp" ]] && cur_usrp="$usrp"
    fi
  fi

  printf '{"ok":true,"tlv":"%s","usrp":"%s"}' "$cur_tlv" "$cur_usrp"
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
  local mode="$1" url json
  local cache="/tmp/dvswitch-reflectors-${mode}.json"
  # Serve from cache if fresh (<24h)
  if [[ -f "$cache" ]] && [[ $(($(date +%s) - $(stat -c %Y "$cache" 2>/dev/null || echo 0))) -lt 86400 ]]; then
    json=$(cat "$cache" 2>/dev/null)
    if [[ -n "$json" ]]; then
      printf '{"ok":true,"reflectors":%s,"source":"dvref-cache"}' "$json"
      return
    fi
  fi
  # DVRef API endpoints (https://dvref.com/api/v2/ -- reflector lists are at
  # /api/v2/{mode}/reflectors/; the M17 list lives under the "mrefd" group,
  # NOT "m17"). Anonymous access requires X-DVRef-Callsign plus
  # X-DVRef-Contact as a valid email address or http(s) URL -- a bare
  # callsign is rejected with HTTP 400. Rate limit: 1 request per source IP
  # every 6 hours per resource, hence the 24h local cache above.
  case "$mode" in
    ysf)  url="https://dvref.com/api/v2/ysf/reflectors/" ;;
    p25)  url="https://dvref.com/api/v2/p25/reflectors/" ;;
    nxdn) url="https://dvref.com/api/v2/nxdn/reflectors/" ;;
    m17)  url="https://dvref.com/api/v2/mrefd/reflectors/" ;;
    *) printf '{"ok":true,"reflectors":[]}'; return ;;
  esac
  # Fetch with callsign headers (required by DVRef)
  json=$(curl -s --max-time 15 -H "X-DVRef-Callsign: KF0RIZ" \
    -H "X-DVRef-Contact: https://github.com/Beerssam/Projects" "$url" 2>/dev/null | \
    python3 -c '
import json,sys
mode = sys.argv[1] if len(sys.argv) > 1 else ""
try:
  d = json.load(sys.stdin)
  refs = d.get("data", {}).get("reflectors", [])
  out = []
  for r in refs[:300]:
    rid = str(r.get("designator", ""))
    name = r.get("name") or r.get("slug") or rid
    if not rid:
      continue
    # Dashboard convention: M17 reflector ids are "M17-<designator>"
    # (matches the hardcoded list and the "e.g. M17-M17" placeholder).
    if mode == "m17" and not rid.upper().startswith("M17"):
      rid = "M17-" + rid
    out.append({"id": rid, "name": name})
  print(json.dumps(out))
except Exception:
  print("[]")
' "$mode" 2>/dev/null)
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
  live)       do_live ;;
  tune)       do_tune ;;
  mode)       do_mode ;;
  reflectors) do_reflectors ;;
  gain)       do_gain ;;
  m17)        do_m17 ;;
  *)          printf '{"ok":false,"error":"Unknown action"}' ;;
esac

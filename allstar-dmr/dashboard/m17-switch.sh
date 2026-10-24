#!/usr/bin/env bash
# m17-switch.sh -- privileged M17 bridge helper for the dvswitch dashboard.
#
# Single privileged control path for the USRP2M17 bridge, same pattern as
# mode-switch.sh / gain-set.sh: www-data may run ONLY this script via sudo
# (sudoers rule written by the dashboard install.sh).
#
# USRP2M17 has no runtime control channel -- it reads /etc/USRP2M17.ini once
# at startup -- so a reflector switch rewrites the ini's [M17 Network]
# Name/Address/DstPort and restarts the service, then waits for the
# reflector's ACKN in the bridge log before claiming success. Reflector
# addresses are resolved HERE, on the node, from the DVRef mrefd registry
# (cached raw JSON); the browser only ever supplies a reflector name and a
# module letter, never an address.
#
# Usage:
#   m17-switch.sh status
#   m17-switch.sh switch <REFLECTOR> <MODULE>   e.g. switch M17-M17 A
#   m17-switch.sh connect | disconnect          (start/stop the bridge)
#   m17-switch.sh link | unlink                 (link/unlink node 1998 to 625730)
#   m17-switch.sh link1999 | unlink1999         (link/unlink DVSwitch node 1999)
#
# Linking is mutually exclusive by design: linking 1998 unlinks 1999 first
# (and vice versa) -- the two pseudo-nodes must never feed 625730 at once,
# or two digital networks (and Sam's analog audio) would mix.
#
# Stdout (parsed by the CGI): key=value lines --
#   service=active|inactive, reflector=, module=, address=, port=,
#   linked=yes|no|unknown (node 1998), linked1999=yes|no|unknown,
#   note=<text>
# Exit: 0 = done and verified; 1 = failure; 2 = bad usage/validation.
#
# Env overrides (for testing): M17_INI, SYSTEMCTL, ASTERISK,
#   REFLECTORS_JSON, M17_LOG_DIR, MAIN_NODE, M17_NODE, DVSWITCH_NODE, CURL

set -u
M17_INI="${M17_INI:-/etc/USRP2M17.ini}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
ASTERISK="${ASTERISK:-asterisk}"
CURL="${CURL:-curl}"
REFLECTORS_JSON="${REFLECTORS_JSON:-/var/lib/usrp2m17/reflectors.json}"
M17_LOG_DIR="${M17_LOG_DIR:-/var/log/usrp2m17}"
MAIN_NODE="${MAIN_NODE:-625730}"
M17_NODE="${M17_NODE:-1998}"
DVSWITCH_NODE="${DVSWITCH_NODE:-1999}"
DVREF_URL="https://dvref.com/api/v2/mrefd/reflectors/"
SERVICE="usrp2m17"

# ---------- ini helpers (section-aware; keys repeat across sections) ------
ini_get() {
  # $1 = section, $2 = key -> value or empty
  awk -v sec="[$1]" -v key="$2" '
    $0 == sec { insec = 1; next }
    /^\[/    { insec = 0 }
    insec && $0 ~ "^" key "[ \t]*=" {
      v = $0; sub(/^[^=]*=[ \t]*/, "", v); sub(/[ \t]*;.*$/, "", v); sub(/[ \t]+$/, "", v)
      print v; exit
    }' "$M17_INI" 2>/dev/null
}

ini_set() {
  # $1 = section, $2 = key, $3 = value. Rewrites the first key line inside
  # the section in place; inserts after the section header if absent.
  local sec="$1" key="$2" val="$3" tmp
  tmp=$(mktemp) || return 1
  if ! awk -v sec="[$sec]" -v key="$key" -v val="$val" '
    $0 == sec { print; insec = 1; next }
    /^\[/ { if (insec && !done) { print key "=" val; done = 1 } insec = 0; print; next }
    insec && !done && $0 ~ "^" key "[ \t]*=" { print key "=" val; done = 1; next }
    { print }
    END { if (insec && !done) print key "=" val }
  ' "$M17_INI" > "$tmp"; then
    rm -f "$tmp"; return 1
  fi
  if ! cat "$tmp" > "$M17_INI"; then rm -f "$tmp"; return 1; fi
  rm -f "$tmp"
  return 0
}

current_reflector() { ini_get "M17 Network" "Name" | awk '{print $1}'; }
current_module() {
  local n; n=$(ini_get "M17 Network" "Name")
  if [[ "$n" == *" "* ]]; then printf '%s' "${n##* }"; else printf ''; fi
}

svc() {
  if "$SYSTEMCTL" is-active --quiet "$SERVICE" 2>/dev/null; then
    printf 'active'
  else
    printf 'inactive'
  fi
}

ack_state() {
  # acked|nacked|unknown -- the reflector's LAST word in the bridge log.
  # "Service active" does NOT mean "connected to the reflector" (a NACKed
  # bridge keeps running), so state displays key off this, not off svc().
  local f
  f=$(ls -t "$M17_LOG_DIR"/USRP2M17-*.log 2>/dev/null | head -1)
  [[ -n "$f" && -r "$f" ]] || { printf 'unknown'; return; }
  case "$(tail -c 262144 "$f" 2>/dev/null | grep -aE 'Received (ACKN|NACK)' | tail -1)" in
    *ACKN*) printf 'acked' ;;
    *NACK*) printf 'nacked' ;;
    *) printf 'unknown' ;;
  esac
}

LSTATS_CACHE=""; LSTATS_DONE=0
lstats() {
  # MAIN_NODE's link table; cached per run, invalidated by lstats_refresh
  # after any command that can change link state.
  if [[ $LSTATS_DONE -eq 0 ]]; then
    LSTATS_CACHE=$("$ASTERISK" -rx "rpt lstats $MAIN_NODE" 2>/dev/null) || LSTATS_CACHE=""
    LSTATS_DONE=1
  fi
  printf '%s' "$LSTATS_CACHE"
}
lstats_refresh() { LSTATS_DONE=0; LSTATS_CACHE=""; }

linked_state() {
  # $1 = node number -> yes|no|unknown (linked to MAIN_NODE per Asterisk?)
  local node="$1" out
  out=$(lstats)
  [[ -n "$out" ]] || { printf 'unknown'; return; }
  if printf '%s' "$out" | grep -Eq "(^|[^0-9])${node}([^0-9]|$)"; then
    printf 'yes'
  else
    printf 'no'
  fi
}

print_state() {
  printf 'service=%s\n' "$(svc)"
  printf 'reflector=%s\n' "$(current_reflector)"
  printf 'module=%s\n' "$(current_module)"
  printf 'address=%s\n' "$(ini_get "M17 Network" "Address")"
  printf 'port=%s\n' "$(ini_get "M17 Network" "DstPort")"
  printf 'linked=%s\n' "$(linked_state "$M17_NODE")"
  printf 'linked1999=%s\n' "$(linked_state "$DVSWITCH_NODE")"
  printf 'ack=%s\n' "$(ack_state)"
  [[ -n "${1:-}" ]] && printf 'note=%s\n' "$1"
  return 0
}

# ---------- reflector resolution (DVRef registry, cached) -----------------
refresh_reflectors() {
  # Refresh the raw DVRef cache if missing or older than 24h. Best effort:
  # a stale cache beats none. DVRef rate-limits per IP, hence the cache.
  local age=999999 now tmp
  if [[ -f "$REFLECTORS_JSON" ]]; then
    age=$(( $(date +%s) - $(stat -c %Y "$REFLECTORS_JSON" 2>/dev/null || echo 0) ))
  fi
  if [[ $age -lt 86400 ]]; then return 0; fi
  tmp=$(mktemp) || return 1
  if "$CURL" -s --max-time 20 \
       -H "X-DVRef-Callsign: KF0RIZ" \
       -H "X-DVRef-Contact: https://github.com/Beerssam/Projects" \
       "$DVREF_URL" -o "$tmp" 2>/dev/null \
     && python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["data"]["reflectors"]' "$tmp" 2>/dev/null; then
    mkdir -p "$(dirname "$REFLECTORS_JSON")" 2>/dev/null
    mv "$tmp" "$REFLECTORS_JSON" 2>/dev/null || { rm -f "$tmp"; return 1; }
    return 0
  fi
  rm -f "$tmp"
  return 1
}

resolve_reflector() {
  # $1 = reflector name (e.g. M17-M17, or bare designator). Prints
  # "<host> <port> <canonical-name> <modules-csv>" or nothing. Host = the
  # reflector's published dns name when it has one, else its static IPv4.
  refresh_reflectors || true
  [[ -r "$REFLECTORS_JSON" ]] || return 1
  python3 - "$REFLECTORS_JSON" "$1" <<'PYEOF'
import json, sys
path, want = sys.argv[1], sys.argv[2].strip().upper()
if want.startswith("M17-"):
    want = want[4:]
try:
    refs = json.load(open(path))["data"]["reflectors"]
except Exception:
    sys.exit(1)
for r in refs:
    if str(r.get("designator", "")).upper() == want:
        host = r.get("dns") or r.get("ipv4")
        if not host:
            sys.exit(1)
        port = r.get("port") or 17000
        mods = ",".join(r.get("modules") or [])
        print("%s %s M17-%s %s" % (host, port, r.get("designator"), mods))
        sys.exit(0)
sys.exit(1)
PYEOF
}

# ---------- ACKN verification ---------------------------------------------
ACKN_FILE=""; ACKN_SIZE=0
snapshot_ackn() {
  ACKN_FILE=$(ls -t "$M17_LOG_DIR"/USRP2M17-*.log 2>/dev/null | head -1)
  if [[ -n "$ACKN_FILE" ]]; then
    ACKN_SIZE=$(stat -c %s "$ACKN_FILE" 2>/dev/null || echo 0)
  else
    ACKN_SIZE=0
  fi
}

wait_ackn() {
  # $1 = max seconds. Returns 0 once "Received ACKN" appears in the bridge
  # log beyond the pre-restart snapshot offset; 2 on "Received NACK" (the
  # reflector refused -- e.g. a module it does not have); 1 on timeout or
  # if the service dies.
  local max="${1:-15}" waited=0 f off
  while [[ $waited -lt $max ]]; do
    sleep 1; waited=$((waited+1))
    [[ "$(svc)" == "active" ]] || return 1
    f=$(ls -t "$M17_LOG_DIR"/USRP2M17-*.log 2>/dev/null | head -1)
    [[ -n "$f" ]] || continue
    off=0; [[ "$f" == "$ACKN_FILE" ]] && off=$ACKN_SIZE
    if tail -c +"$((off+1))" "$f" 2>/dev/null | grep -q "Received NACK"; then
      return 2
    fi
    if tail -c +"$((off+1))" "$f" 2>/dev/null | grep -q "Received ACKN"; then
      return 0
    fi
  done
  return 1
}

restart_and_ackn() {
  # Restart the service and wait for the reflector's ACKN, retrying
  # through NACKs. Why retries: USRP2M17 never sends DISC when it exits
  # (its writeUnlink() is dead code upstream; the SIGTERM exit just closes
  # the socket), so a restart-while-connected leaves the reflector holding
  # our previous session, and it NACKs the new CONN as a duplicate until
  # that session times out. Sam hit exactly this on his first panel switch
  # (Oct 23 2026). The retries wait out the reflector's session timeout.
  # Returns wait_ackn's code for the final attempt: 0 ACKN, 2 NACK,
  # 1 timeout/dead. (systemctl restart also starts a stopped service.)
  local rc delay
  snapshot_ackn
  "$SYSTEMCTL" restart "$SERVICE" 2>/dev/null || return 1
  wait_ackn 15; rc=$?
  [[ $rc -eq 0 ]] && return 0
  for delay in ${M17_NACK_DELAYS:-30 45}; do
    [[ $rc -eq 2 ]] || return $rc
    sleep "$delay"
    snapshot_ackn
    "$SYSTEMCTL" restart "$SERVICE" 2>/dev/null || return 1
    wait_ackn 15; rc=$?
    [[ $rc -eq 0 ]] && return 0
  done
  return $rc
}

fail() { printf 'note=%s\n' "$1"; exit 1; }

# ---------- node link control (Asterisk) ------------------------------------
wait_link_state() {
  # $1 = node, $2 = wanted state (yes|no). Polls up to ~5s with fresh
  # lstats each round; prints the final observed state.
  local node="$1" want="$2" waited=0 state=""
  while [[ $waited -lt 6 ]]; do
    state=$(linked_state "$node")
    [[ "$state" == "$want" ]] && break
    sleep 1; waited=$((waited+1)); lstats_refresh
  done
  printf '%s' "$state"
}

rpt_fun() {
  # $1 = function code (e.g. *31998). Fails the run if Asterisk errors.
  "$ASTERISK" -rx "rpt fun $MAIN_NODE $1" >/dev/null 2>&1 \
    || fail "asterisk command failed (rpt fun $MAIN_NODE $1)"
  lstats_refresh
}

link_node() {
  # $1 = node to link to MAIN_NODE. Mutual exclusion: if the OTHER
  # pseudo-node is linked, unlink it first and refuse to proceed if that
  # unlink does not verify (never leave both linked).
  local node="$1" other state note
  if [[ "$node" == "$M17_NODE" ]]; then other="$DVSWITCH_NODE"; else other="$M17_NODE"; fi
  note="node $node linked"
  if [[ "$(linked_state "$other")" == "yes" ]]; then
    rpt_fun "*1${other}"
    state=$(wait_link_state "$other" "no")
    [[ "$state" == "no" ]] \
      || fail "could not unlink node $other first (asterisk reports: $state) -- not linking $node"
    note="node $node linked (node $other unlinked first)"
  fi
  rpt_fun "*3${node}"
  state=$(wait_link_state "$node" "yes")
  if [[ "$state" == "yes" ]]; then
    print_state "$note"
  else
    fail "link state did not become yes after *3${node} (asterisk reports: $state)"
  fi
}

unlink_node() {
  # $1 = node to unlink from MAIN_NODE.
  local node="$1" state
  rpt_fun "*1${node}"
  state=$(wait_link_state "$node" "no")
  if [[ "$state" == "no" ]]; then
    print_state "node $node unlinked"
  else
    fail "link state did not become no after *1${node} (asterisk reports: $state)"
  fi
}

# ---------- ops -------------------------------------------------------------
op="${1:-}"
case "$op" in
  status)
    print_state
    ;;
  switch)
    name="${2:-}"; module="${3:-}"
    name_re='^[A-Za-z0-9][A-Za-z0-9-]{0,23}$'
    if ! [[ "$name" =~ $name_re ]]; then
      printf 'note=invalid reflector name: %s\n' "$name"; exit 2
    fi
    if ! [[ "$module" =~ ^[A-Z]$ ]]; then
      printf 'note=invalid module (single letter A-Z): %s\n' "$module"; exit 2
    fi
    [[ -r "$M17_INI" ]] || fail "not readable: $M17_INI"
    resolved=$(resolve_reflector "$name") || fail "reflector not found in DVRef registry: $name"
    read -r host port canon modlist <<< "$resolved"
    [[ -n "$host" && -n "$canon" ]] || fail "could not resolve reflector: $name"
    if [[ -n "$modlist" && ",$modlist," != *",$module,"* ]]; then
      fail "$canon has no module $module (it has: $modlist)"
    fi
    ts=$(date +%Y%m%d-%H%M%S)
    cp "$M17_INI" "$M17_INI.bak.$ts" || fail "ini backup failed"
    ini_set "M17 Network" "Name" "$canon $module" || fail "ini write failed (Name)"
    ini_set "M17 Network" "Address" "$host" || fail "ini write failed (Address)"
    ini_set "M17 Network" "DstPort" "$port" || fail "ini write failed (DstPort)"
    restart_and_ackn; wrc=$?
    if [[ $wrc -eq 0 ]]; then
      print_state "switched to $canon module $module; reflector acknowledged"
    elif [[ $wrc -eq 2 ]]; then
      fail "the reflector refused the connection (NACK) for $canon module $module even after retries -- it may still be holding a previous session; wait a minute, then press Start Bridge"
    else
      fail "switched ini to $canon $module and restarted, but no ACKN from the reflector"
    fi
    ;;
  connect)
    if [[ "$(svc)" == "active" ]]; then
      print_state "bridge already running"
    else
      restart_and_ackn; wrc=$?
      if [[ $wrc -eq 0 ]]; then
        print_state "bridge started; reflector acknowledged"
      elif [[ $wrc -eq 2 ]]; then
        fail "the reflector refused the connection (NACK) even after retries -- it may still be holding a previous session; wait a minute and press Start Bridge again"
      else
        fail "bridge started but no ACKN from the reflector"
      fi
    fi
    ;;
  disconnect)
    "$SYSTEMCTL" stop "$SERVICE" 2>/dev/null || fail "$SERVICE stop failed"
    print_state "bridge stopped (reflector disconnected)"
    ;;
  link)      link_node "$M17_NODE" ;;
  unlink)    unlink_node "$M17_NODE" ;;
  link1999)  link_node "$DVSWITCH_NODE" ;;
  unlink1999) unlink_node "$DVSWITCH_NODE" ;;
  *)
    printf 'note=usage: m17-switch.sh status|switch <reflector> <module>|connect|disconnect|link|unlink|link1999|unlink1999\n'
    exit 2
    ;;
esac
exit 0

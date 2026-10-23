#!/usr/bin/env bash
# install-m17.sh -- install the USRP2M17 M17 bridge on the AllStar node.
#
# Run with sudo on the node, AFTER build-usrp2m17.sh:
#   sudo bash allstar-dmr/m17/install-m17.sh [--dry-run]
#
# What it does:
#   1. Verifies preconditions and STOPS on any mismatch (binary built,
#      rpt.conf has the expected [1999] USRP stanza, node 1998 unused,
#      USRP/M17 ports free).
#   2. Backs up rpt.conf (and any ini/unit it replaces) with a timestamp.
#   3. Adds private node 1998 to rpt.conf: a [nodes] line, plus a [1998]
#      stanza mirrored from [1999] with the USRP port pair changed to
#      34002:32002.
#   4. Installs /etc/USRP2M17.ini (only if absent -- an existing ini is
#      Sam's, possibly dashboard-switched, and is left alone) and the
#      usrp2m17 systemd unit; primes the DVRef reflector cache.
#   5. Restarts Asterisk once, enables + starts usrp2m17, and verifies:
#      both services active, rpt.conf read-back correct, and the bridge
#      log shows "Received ACKN" from the reflector.
#
# --dry-run prints the full plan (including the exact stanza it would add)
# and changes nothing.
#
# Env overrides (fixture tests only): M17_ROOT prefixes every target path;
# RPT_CONF, SYSTEMCTL, ASTERISK, SS_BIN override individual paths/tools.
set -uo pipefail

ROOT="${M17_ROOT:-}"
if [[ -z "$ROOT" && $EUID -ne 0 ]]; then
  echo "Run as root (sudo)." >&2; exit 1
fi

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INI_SRC="$SCRIPT_DIR/USRP2M17.ini"
UNIT_SRC="$SCRIPT_DIR/usrp2m17.service"
RPT_CONF="${RPT_CONF:-$ROOT/etc/asterisk/rpt.conf}"
INI_DEST="$ROOT/etc/USRP2M17.ini"
UNIT_DEST="$ROOT/etc/systemd/system/usrp2m17.service"
BIN_CHECK="$ROOT/usr/local/bin/USRP2M17"
LOG_DIR="$ROOT/var/log/usrp2m17"
LIB_DIR="$ROOT/var/lib/usrp2m17"
CGI_HELPER="$ROOT/var/www/cgi-bin/m17-switch.sh"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
ASTERISK="${ASTERISK:-asterisk}"
SS_BIN="${SS_BIN:-ss}"
MAIN_NODE=625730
M17_NODE=1998
USRP_PAIR_NEW="USRP/127.0.0.1:34002:32002"
USRP_PAIR_1999="USRP/127.0.0.1:34001:32001"

say()  { echo "== $*"; }
plan() { echo "   [dry-run] $*"; }
die()  { echo "!! $*" >&2; exit 1; }

[[ -f "$INI_SRC" ]]  || die "Missing package file: $INI_SRC"
[[ -f "$UNIT_SRC" ]] || die "Missing package file: $UNIT_SRC"
[[ -x "$BIN_CHECK" ]] || die "USRP2M17 binary not found at $BIN_CHECK -- run build-usrp2m17.sh first"
[[ -f "$RPT_CONF" ]] || die "rpt.conf not found: $RPT_CONF"

# ---- inspect rpt.conf ------------------------------------------------------
sec1999=$(awk '/^\[1999\]/{f=1} /^\[/{if(f && $0 !~ /^\[1999\]/) exit} f' "$RPT_CONF")
[[ -n "$sec1999" ]] || die "no [1999] stanza in $RPT_CONF -- unexpected node config, stopping"
printf '%s' "$sec1999" | grep -qF "rxchannel = $USRP_PAIR_1999" \
  || die "[1999] does not use the expected rxchannel $USRP_PAIR_1999 -- stopping"

stanza_done=0
if grep -q '^\[1998\]' "$RPT_CONF"; then
  sec1998=$(awk '/^\[1998\]/{f=1} /^\[/{if(f && $0 !~ /^\[1998\]/) exit} f' "$RPT_CONF")
  printf '%s' "$sec1998" | grep -qF "rxchannel = $USRP_PAIR_NEW" \
    || die "[1998] already exists but does not use $USRP_PAIR_NEW -- stopping (resolve manually)"
  stanza_done=1
  say "node 1998 stanza already present and correct, will skip"
fi

nodes_done=0
if grep -Eq '^1998[[:space:]]*=' "$RPT_CONF"; then
  grep -Eq '^1998[[:space:]]*=[[:space:]]*radio@127\.0\.0\.1/1998,NONE' "$RPT_CONF" \
    || die "[nodes] already has a 1998 line with an unexpected target -- stopping"
  nodes_done=1
  say "[nodes] 1998 line already present and correct, will skip"
fi
grep -q '^\[nodes\]' "$RPT_CONF" || die "no [nodes] section in $RPT_CONF -- stopping"

# The stanza we will add: [1999]'s header/body with node number and the
# USRP port pair swapped. Built now so --dry-run shows it verbatim.
new_stanza=$(printf '%s\n' "$sec1999" \
  | sed -e 's/^\[1999\]/[1998]/' \
        -e "s|rxchannel = $USRP_PAIR_1999|rxchannel = $USRP_PAIR_NEW|")

# ---- port check (real runs only) -------------------------------------------
if [[ $DRY -eq 0 && -z "$ROOT" ]]; then
  bound=$("$SS_BIN" -uln 2>/dev/null | grep -E ':(34002|32002|32012)[[:space:]]' || true)
  if [[ -n "$bound" ]] && ! "$SYSTEMCTL" is-active --quiet usrp2m17 2>/dev/null; then
    echo "$bound" >&2
    die "one or more of UDP 34002/32002/32012 is already bound and usrp2m17 is not running -- stopping"
  fi
fi

TS=$(date +%Y%m%d-%H%M%S)

if [[ $DRY -eq 1 ]]; then
  say "DRY RUN -- nothing will be changed"
  plan "backup $RPT_CONF -> $RPT_CONF.bak.$TS"
  [[ $nodes_done -eq 0 ]]  && plan "insert into [nodes]: 1998 = radio@127.0.0.1/1998,NONE"
  if [[ $stanza_done -eq 0 ]]; then
    plan "append stanza to $RPT_CONF:"
    printf '%s\n' "$new_stanza" | sed 's/^/     /'
  fi
  if [[ -f "$INI_DEST" ]]; then plan "keep existing $INI_DEST (not overwritten)"
  else plan "install $INI_DEST from package template"; fi
  plan "install $UNIT_DEST"
  plan "mkdir -p $LOG_DIR $LIB_DIR; prime DVRef reflector cache"
  plan "systemctl daemon-reload; enable usrp2m17"
  plan "restart asterisk (momentary link drop), start usrp2m17"
  plan "verify: services active, rpt.conf read-back, 'Received ACKN' in bridge log"
  exit 0
fi

# ---- apply ------------------------------------------------------------------
say "backing up $RPT_CONF -> $RPT_CONF.bak.$TS"
cp "$RPT_CONF" "$RPT_CONF.bak.$TS" || die "rpt.conf backup failed"
ROLLBACK="rollback: cp $RPT_CONF.bak.$TS $RPT_CONF && $SYSTEMCTL restart asterisk"

tmp=$(mktemp) || die "mktemp failed"
if [[ $nodes_done -eq 0 ]]; then
  say "adding 1998 to [nodes]"
  awk '
    /^\[nodes\]/ { innodes = 1; print; next }
    /^\[/ { if (innodes && !done) { print "1998 = radio@127.0.0.1/1998,NONE"; done = 1 } innodes = 0; print; next }
    { print }
    END { if (innodes && !done) print "1998 = radio@127.0.0.1/1998,NONE" }
  ' "$RPT_CONF" > "$tmp" || { rm -f "$tmp"; die "nodes insert failed; $ROLLBACK"; }
  grep -Eq '^1998[[:space:]]*=[[:space:]]*radio@127\.0\.0\.1/1998,NONE' "$tmp" \
    || { rm -f "$tmp"; die "nodes insert did not land in the temp copy; $ROLLBACK"; }
  cat "$tmp" > "$RPT_CONF" || { rm -f "$tmp"; die "rpt.conf write failed; $ROLLBACK"; }
fi
rm -f "$tmp"

if [[ $stanza_done -eq 0 ]]; then
  say "appending [1998] stanza (mirrored from [1999])"
  { printf '\n'; printf '%s\n' "$new_stanza"; } >> "$RPT_CONF" \
    || die "stanza append failed; $ROLLBACK"
fi

mkdir -p "$LOG_DIR" "$LIB_DIR" "$(dirname "$INI_DEST")" "$(dirname "$UNIT_DEST")" \
  || die "mkdir failed"
if [[ -f "$INI_DEST" ]]; then
  say "keeping existing $INI_DEST (not overwritten)"
else
  say "installing $INI_DEST"
  cp "$INI_SRC" "$INI_DEST" || die "ini install failed; $ROLLBACK"
fi
if [[ -f "$UNIT_DEST" ]] && ! cmp -s "$UNIT_SRC" "$UNIT_DEST"; then
  cp "$UNIT_DEST" "$UNIT_DEST.bak.$TS"
  say "backed up existing unit"
fi
cp "$UNIT_SRC" "$UNIT_DEST" || die "unit install failed; $ROLLBACK"

if [[ -z "$ROOT" ]]; then
  say "priming DVRef reflector cache (best effort)"
  curl -s --max-time 20 \
    -H "X-DVRef-Callsign: KF0RIZ" \
    -H "X-DVRef-Contact: https://github.com/Beerssam/Projects" \
    "https://dvref.com/api/v2/mrefd/reflectors/" \
    -o "$LIB_DIR/reflectors.json" 2>/dev/null \
    || echo "   (cache prime failed; the dashboard helper will fetch on first use)"
fi

say "daemon-reload + enable usrp2m17"
"$SYSTEMCTL" daemon-reload || die "daemon-reload failed; $ROLLBACK"
"$SYSTEMCTL" enable usrp2m17 >/dev/null 2>&1 || die "enable failed; $ROLLBACK"

say "restarting asterisk (momentary link drop)"
"$SYSTEMCTL" restart asterisk || die "asterisk restart failed; $ROLLBACK"
waited=0
until "$SYSTEMCTL" is-active --quiet asterisk 2>/dev/null || [[ $waited -ge 15 ]]; do
  sleep 1; waited=$((waited+1))
done
"$SYSTEMCTL" is-active --quiet asterisk || die "asterisk did not come back active; $ROLLBACK"

# Snapshot the bridge log so the ACKN check only counts this start.
logf=$(ls -t "$LOG_DIR"/USRP2M17-*.log 2>/dev/null | head -1)
off=0; [[ -n "$logf" ]] && off=$(stat -c %s "$logf" 2>/dev/null || echo 0)

say "starting usrp2m17"
"$SYSTEMCTL" restart usrp2m17 || die "usrp2m17 start failed; $ROLLBACK"

say "waiting for reflector ACKN (up to 20s)"
ackn=0; waited=0
while [[ $waited -lt 20 ]]; do
  sleep 1; waited=$((waited+1))
  f=$(ls -t "$LOG_DIR"/USRP2M17-*.log 2>/dev/null | head -1)
  [[ -n "$f" ]] || continue
  o=0; [[ "$f" == "$logf" ]] && o=$off
  if tail -c +"$((o+1))" "$f" 2>/dev/null | grep -q "Received ACKN"; then ackn=1; break; fi
done

# ---- verify -----------------------------------------------------------------
ok=1
"$SYSTEMCTL" is-active --quiet usrp2m17 || { echo "!! usrp2m17 not active" >&2; ok=0; }
grep -q '^\[1998\]' "$RPT_CONF" || { echo "!! [1998] missing on read-back" >&2; ok=0; }
grep -Eq '^1998[[:space:]]*=' "$RPT_CONF" || { echo "!! 1998 [nodes] line missing on read-back" >&2; ok=0; }
[[ $ok -eq 1 ]] || die "verification failed; $ROLLBACK"

if [[ $ackn -eq 1 ]]; then
  say "verified: usrp2m17 active and the reflector acknowledged (ACKN)"
else
  echo "!! usrp2m17 is active but no ACKN seen within 20s -- check $LOG_DIR and" >&2
  echo "   journalctl -u usrp2m17. The install itself is complete; the reflector" >&2
  echo "   connection may just be slow or the reflector may be down." >&2
fi

if [[ ! -f "$CGI_HELPER" ]]; then
  echo
  echo "Note: the dashboard M17 panel helper is not installed yet."
  echo "Run (or re-run): sudo bash allstar-dmr/dashboard/install.sh"
  echo "The bridge works without it; the panel is the control surface."
fi

echo
echo "Done. Try it: link node 1998 to $MAIN_NODE (or use the dashboard M17"
echo "panel) and key up -- you are on M17-M17 module A by default."

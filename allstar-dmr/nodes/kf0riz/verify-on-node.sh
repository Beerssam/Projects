#!/usr/bin/env bash
# verify-on-node.sh -- post-deploy health check for the KF0RIZ multi-mode DMR
# chain on the ASL3 node.
#
# Run with sudo AFTER deploy-on-node.sh has restarted the bridge chain, and give
# the networks ~30 seconds to log in first:
#   cd ~/Projects/allstar-dmr/nodes/kf0riz && sudo bash verify-on-node.sh
#
# What it checks:
#   1. No __SET_...__ password markers left in the LIVE configs (silent killer).
#   2. The three daemons are actually running: DMRGateway, MMDVM_Bridge, Analog_Bridge.
#   3. The localhost bridge leg has its UDP ports bound (no bind conflict).
#   4. For every ENABLED DMRGateway network stanza, the DMRGateway log shows
#      recent evidence of a successful login ("connected") to that network,
#      and no recent login failures.
#
# Flags (rarely needed):
#   --config-dir DIR   read configs from DIR instead of the live install
#                      (e.g. to re-check a /root/dmr-config-backup-*/ copy).
#   --log-dir DIR      override the DMRGateway log directory.
#
# Exit 0 when everything passes, 1 when anything needs attention.
set -u

CONFIG_DIR=""
LOG_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config-dir) CONFIG_DIR="$2"; shift 2 ;;
    --log-dir)    LOG_DIR="$2";    shift 2 ;;
    *) echo "usage: $0 [--config-dir DIR] [--log-dir DIR]" >&2; exit 2 ;;
  esac
done

fail_count=0; warn_count=0
ok()   { echo "  ok:   $1"; }
bad()  { fail_count=$((fail_count+1)); echo "  FAIL: $1"; }
warn() { warn_count=$((warn_count+1)); echo "  warn: $1"; }

# ini <file> <section> <key> -> value (first match)
ini() {
  awk -v sec="$2" -v key="$3" '
    /^\[.*\]/ { cur=$0; gsub(/^\[|\]$/, "", cur) }
    cur==sec && $0 ~ "^"key"=" { sub("^"key"=", ""); print; exit }
  ' "$1"
}

# ---- locate the live configs ---------------------------------------------
if [[ -z "$CONFIG_DIR" ]]; then
  DG_DIR=/opt/MMDVM_Bridge
  [[ -d "$DG_DIR" ]] || DG_DIR=/opt/DMRGateway
  CONFIG_DIR=""
  [[ -f "$DG_DIR/DMRGateway.ini" ]] && CONFIG_DIR="$DG_DIR"
  [[ -z "$CONFIG_DIR" ]] && { bad "no live DMRGateway.ini found in /opt/MMDVM_Bridge or /opt/DMRGateway (is DVSwitch Server installed?)"; }
else
  DG_DIR="$CONFIG_DIR"
fi
MM_INI="$CONFIG_DIR/MMDVM_Bridge.ini"
AB_INI="$CONFIG_DIR/Analog_Bridge.ini"
DG_INI="$DG_DIR/DMRGateway.ini"
[[ -n "$CONFIG_DIR" && -f "$DG_INI" ]] || { echo "aborting: DMRGateway.ini not found." >&2; exit 2; }

echo "checking live configs in $DG_DIR"
[[ -f "$MM_INI" ]] || bad "MMDVM_Bridge.ini missing in $CONFIG_DIR"
[[ -f "$AB_INI" ]] || bad "Analog_Bridge.ini missing in $CONFIG_DIR"

# ---- 1. no password markers left ------------------------------------------
echo "- password markers:"
if grep -q '__SET_[A-Za-z_]*__' "$DG_INI" "$MM_INI" "$AB_INI" 2>/dev/null; then
  bad "a __SET_...__ marker is still in the live configs -- fill in the hotspot password(s) and re-run deploy-on-node.sh"
else
  ok "no __SET_...__ markers in the live configs"
fi

# ---- 2. daemons running ----------------------------------------------------
echo "- daemon processes:"
for d in DMRGateway MMDVM_Bridge Analog_Bridge; do
  # [X]... pattern so pgrep never matches this script's own command line
  pat="[${d:0:1}]${d:1}"
  if pgrep -f "$pat" >/dev/null 2>&1; then
    ok "$d is running (pid $(pgrep -f "$pat" | head -1))"
  else
    bad "$d is NOT running -- restart the bridge chain: DMRGateway -> MMDVM_Bridge -> Analog_Bridge"
  fi
done

# ---- 3. localhost bridge leg UDP binds -------------------------------------
# DMRGateway binds [General] LocalPort; MMDVM_Bridge binds [DMR Network] Local.
# (There is no unnumbered [DMR Network] section in current DMRGateway.)
echo "- localhost bridge leg:"
mm_local=$(ini "$MM_INI" "DMR Network" "Local")
dg_local=$(ini "$DG_INI" "General" "LocalPort")
[[ -z "$dg_local" ]] && dg_local=62031
if command -v ss >/dev/null 2>&1; then
  for p in "$mm_local" "$dg_local"; do
    if [[ -n "$p" ]] && ss -uln 2>/dev/null | grep -qE "[:.]$p[[:space:]]"; then
      ok "UDP port $p is bound"
    else
      bad "UDP port $p is not bound -- a daemon died or the ports are crossed"
    fi
  done
else
  warn "ss not found, skipping bind check"
fi

# ---- 4. per-network login evidence from the DMRGateway log -----------------
echo "- network logins:"
if [[ -z "$LOG_DIR" ]]; then
  LOG_DIR=$(ini "$DG_INI" "Log" "FilePath"); [[ -z "$LOG_DIR" ]] && LOG_DIR=/var/log/mmdvm
  LOG_ROOT=$(ini "$DG_INI" "Log" "FileRoot"); [[ -z "$LOG_ROOT" ]] && LOG_ROOT=DMRGateway
else
  LOG_ROOT=DMRGateway
fi
LOG_FILE=$(ls -t "$LOG_DIR/${LOG_ROOT}"-*.log 2>/dev/null | head -1)
[[ -z "$LOG_FILE" ]] && LOG_FILE=$(ls -t "$LOG_DIR"/*.log 2>/dev/null | head -1)
if [[ -z "$LOG_FILE" || ! -r "$LOG_FILE" ]]; then
  warn "no readable DMRGateway log in $LOG_DIR (try sudo)"
else
  echo "  log: $LOG_FILE"
  RECENT=$(tail -n 5000 "$LOG_FILE")

  # enabled [DMR Network N] stanzas (N>=1)
  mapfile -t net_sections < <(grep -oE '^\[DMR Network [0-9]+\]' "$DG_INI" || true)
  n=0
  for sec in "${net_sections[@]}"; do
    s="${sec#[}"; s="${s%]}"   # strip the brackets -> e.g. "DMR Network 1"
    name=$(ini "$DG_INI" "$s" "Name");   [[ -z "$name" ]] && name="$s"
    en=$(ini "$DG_INI" "$s" "Enabled")
    addr=$(ini "$DG_INI" "$s" "Address")
    [[ "$en" == "1" ]] || { echo "  (skipping disabled stanza $name)"; continue; }
    n=$((n+1))
    line=$(echo "$RECENT" | grep -i -- "$name" | tail -1)
    if [[ -z "$line" ]]; then
      bad "$name ($addr): no log lines at all -- daemon may not have started this stanza"
    elif echo "$line" | grep -qiE 'fail|reject|refus|denied|timed out|not authorized|login failed'; then
      bad "$name ($addr): latest log line looks like a FAILED login:"
      echo "        ${line:0:200}"
    elif echo "$line" | grep -qiE 'connected|logged in|login successful'; then
      ok "$name ($addr): connected -- ${line:0:140}"
    else
      bad "$name ($addr): could not confirm a login from the latest log line:"
      echo "        ${line:0:200}"
    fi
  done
  [[ "$n" -gt 0 ]] || warn "no enabled DMR network stanzas found in $DG_INI"

  # global sweep for failure keywords in the recent window
  fails=$(echo "$RECENT" | grep -ciE 'DMR Network.*(fail|reject|refus|denied|timed out|not authorized)' || true)
  [[ "$fails" -gt 0 ]] && warn "$fails recent log line(s) mention network failures -- scroll above for detail"
fi

# ---- summary ----------------------------------------------------------------
echo
if [[ "$fail_count" -gt 0 ]]; then
  echo "RESULT: $fail_count check(s) FAILED, $warn_count warning(s). Do not trust the chain until the FAILs are resolved."
  exit 1
elif [[ "$warn_count" -gt 0 ]]; then
  echo "RESULT: passed with $warn_count warning(s)."
  exit 0
else
  echo "RESULT: all checks passed. The multi-mode chain is up and logged in."
  exit 0
fi

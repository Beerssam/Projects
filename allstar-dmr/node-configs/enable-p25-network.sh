#!/usr/bin/env bash
# enable-p25-network.sh -- turn on the P25 network leg in MMDVM_Bridge.
#
# State this expects on the KF0RIZ node (verified from the repo config and
# the Oct 2026 gateway plumbing work):
#   * [P25] mode is already Enable=1 with NAC=293.
#   * P25Gateway is installed and plumbed to 127.0.0.1:32010.
#   * [P25 Network] already points at GatewayPort=32010 / LocalPort=32011,
#     but Enable is still 0, so dashboard P25 tunes have nowhere to go.
#
# This script changes exactly one config value:
#   [P25 Network] Enable: 0 -> 1
# in /opt/MMDVM_Bridge/MMDVM_Bridge.ini. It verifies every assumption
# first and stops without changing anything if the live file does not
# match. It backs up the ini before editing, restarts mmdvm_bridge,
# makes sure p25gateway is active, and restores the backup automatically
# if the bridge does not come back.
#
# Usage: sudo bash enable-p25-network.sh
# Env overrides (fixture testing): MMDVM_INI, SYSTEMCTL, ALLOW_NONROOT,
#   P25_GATEWAY_SETTLE, P25_BRIDGE_SETTLE

set -u

INI="${MMDVM_INI:-/opt/MMDVM_Bridge/MMDVM_Bridge.ini}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
BACKUP=""

fail() { echo "ERROR: $1" >&2; exit 1; }
info() { echo "== $1"; }

if [[ "${ALLOW_NONROOT:-0}" != "1" && $EUID -ne 0 ]]; then
  fail "run this with sudo"
fi
[[ -f "$INI" ]] || fail "$INI not found -- nothing changed"

ini_get() {
  # $1 = section, $2 = key. Prints the trimmed value ("" when absent).
  python3 - "$INI" "$1" "$2" <<'PYEOF' 2>/dev/null
import configparser, sys
path, section, key = sys.argv[1], sys.argv[2], sys.argv[3]
cp = configparser.ConfigParser(strict=False, interpolation=None)
cp.optionxform = str
try:
    cp.read(path)
    value = cp.get(section, key, fallback="")
except Exception:
    value = ""
print(str(value).split(";", 1)[0].strip())
PYEOF
}

section_count() {
  grep -c "^\[$1\]$" "$INI" 2>/dev/null || true
}

expect_value() {
  # $1 = section, $2 = key, $3 = expected value
  local got
  got=$(ini_get "$1" "$2")
  if [[ "$got" != "$3" ]]; then
    fail "unexpected $INI [$1] $2: expected '$3', found '${got:-<missing>}' -- nothing changed"
  fi
}

service_exists() {
  "$SYSTEMCTL" cat "$1" >/dev/null 2>&1
}

service_active() {
  "$SYSTEMCTL" is-active --quiet "$1" >/dev/null 2>&1
}

ensure_gateway() {
  if service_active p25gateway; then
    info "p25gateway is already active"
    return 0
  fi
  info "p25gateway is not active -- starting it"
  "$SYSTEMCTL" restart p25gateway >/dev/null 2>&1 || return 1
  sleep "${P25_GATEWAY_SETTLE:-2}"
  service_active p25gateway
}

restart_bridge() {
  "$SYSTEMCTL" restart mmdvm_bridge >/dev/null 2>&1 || return 1
  sleep "${P25_BRIDGE_SETTLE:-3}"
  service_active mmdvm_bridge
}

rollback_config() {
  # Restore the pre-change ini and restart the bridge on the old config.
  if [[ -n "$BACKUP" && -f "$BACKUP" ]]; then
    echo "Restoring backup: $BACKUP" >&2
    cp -p "$BACKUP" "$INI"
    "$SYSTEMCTL" restart mmdvm_bridge >/dev/null 2>&1 || true
    sleep "${P25_BRIDGE_SETTLE:-3}"
  fi
}

# ---- Preflight: the live config must match the expected P25 plumbing ----
info "checking $INI"
[[ "$(section_count 'P25')" == "1" ]] || fail "expected exactly one [P25] section -- nothing changed"
[[ "$(section_count 'P25 Network')" == "1" ]] || fail "expected exactly one [P25 Network] section -- nothing changed"

expect_value "P25" "Enable" "1"
expect_value "P25" "NAC" "293"
expect_value "P25 Network" "GatewayAddress" "127.0.0.1"
expect_value "P25 Network" "GatewayPort" "32010"
expect_value "P25 Network" "LocalAddress" "127.0.0.1"
expect_value "P25 Network" "LocalPort" "32011"

P25_ENABLE=$(ini_get "P25 Network" "Enable")
[[ "$P25_ENABLE" == "0" || "$P25_ENABLE" == "1" ]] || \
  fail "unexpected [P25 Network] Enable value '${P25_ENABLE:-<missing>}' -- nothing changed"

# A bridge restart must not walk into the known empty-DMR-password assert.
DMR_PASSWORD=$(ini_get "DMR Network" "Password")
[[ -n "$DMR_PASSWORD" ]] || fail "[DMR Network] Password is empty -- fix that before restarting mmdvm_bridge; nothing changed"
[[ "$DMR_PASSWORD" != __SET_* ]] || fail "[DMR Network] Password is still an unfilled __SET_ marker -- nothing changed"

service_exists mmdvm_bridge || fail "systemd unit mmdvm_bridge not found -- nothing changed"
service_exists p25gateway || fail "systemd unit p25gateway not found -- nothing changed"

if [[ "$P25_ENABLE" == "1" ]]; then
  info "[P25 Network] is already Enable=1 -- no config change needed"
  ensure_gateway || fail "p25gateway could not be started"
  if service_active mmdvm_bridge; then
    info "mmdvm_bridge is active"
  else
    restart_bridge || fail "mmdvm_bridge is not active and a restart did not recover it"
    info "mmdvm_bridge restarted and is active"
  fi
  echo "Done. P25 was already enabled; both services are active."
  exit 0
fi

# ---- The one change -------------------------------------------------------
echo "Planned change:"
echo "  File:    $INI"
echo "  Change:  [P25 Network] Enable: 0 -> 1 (only this line)"
echo "  Restart: mmdvm_bridge; p25gateway will be started first if inactive"
echo "  Other configs and services are not changed."

BACKUP="$INI.bak.p25-$(date +%Y%m%d-%H%M%S)"
cp -p "$INI" "$BACKUP" || fail "backup to $BACKUP failed -- nothing changed"
info "backup taken: $BACKUP"

if ! python3 - "$INI" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    lines = f.readlines()
section = None
changed = 0
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        section = stripped[1:-1]
        continue
    if section == "P25 Network" and line.lstrip().lower().startswith("enable"):
        if "=" not in line:
            continue
        prefix = line[:line.index("=") + 1]
        ending = "\n" if line.endswith("\n") else ""
        lines[i] = prefix + "1" + ending
        changed += 1
        break
if changed != 1:
    sys.exit("expected to change exactly one Enable line, changed %d" % changed)
with open(path, "w") as f:
    f.writelines(lines)
PYEOF
then
  cp -p "$BACKUP" "$INI" 2>/dev/null || true
  fail "edit did not complete -- backup restored"
fi

# Re-verify the whole expected state after the edit.
expect_value "P25 Network" "Enable" "1"
expect_value "P25 Network" "GatewayPort" "32010"
expect_value "P25 Network" "LocalPort" "32011"
info "config updated and re-verified"

# Gateway first (if it needs starting), then the bridge on the new config.
if ! ensure_gateway; then
  rollback_config
  fail "p25gateway could not be started -- config rolled back"
fi
if ! restart_bridge; then
  rollback_config
  fail "mmdvm_bridge did not come back after enabling P25 -- config rolled back"
fi
info "mmdvm_bridge restarted and is active"

if command -v ss >/dev/null 2>&1; then
  ports=$(ss -H -uln 2>/dev/null | awk '{print $5}' | grep -E ':(32010|32011)$' | sort -u | tr '\n' ' ' || true)
  echo "UDP sockets observed for the P25 pair: ${ports:-none reported by ss; service state above is the liveness check}"
fi

echo
echo "Done. P25 is enabled."
echo "Test: dashboard -> P25 mode -> search/select a TG (e.g. 10200 North America) -> Tune -> key up."
echo "Rollback: sudo cp $BACKUP $INI && sudo systemctl restart mmdvm_bridge"

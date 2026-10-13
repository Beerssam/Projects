#!/usr/bin/env bash
# deploy-on-node.sh -- install the KF0RIZ multi-mode DMR configs on the ASL3 node.
#
# Run with sudo FROM A FRESH `git pull` of this repo on the node:
#   cd ~/Projects/allstar-dmr/nodes/kf0riz && sudo bash deploy-on-node.sh
#
# What it does, in order:
#   0. Checks DMRGateway is installed (it is NOT part of DVSwitch -- run
#      ../../scripts/build-dmrgateway.sh first if it is missing)
#   1. Backs up the node's live configs to /root/dmr-config-backup-<timestamp>/
#   2. Installs the dmrgateway.service systemd unit (if not already present)
#   3. Stages the new configs and fills the __SET_...__ password markers --
#      first reusing any passwords the node already has (an existing
#      DMRGateway.ini, or the stock MMDVM_Bridge.ini), only asking for ones
#      that are missing. Typed input is hidden, never written to disk or
#      committed.
#   4. Runs the repo's validate-dmr-configs.sh against the staged files
#   5. Copies the staged files over /opt/...
#   6. Restarts the bridge chain in order: DMRGateway -> MMDVM_Bridge -> Analog_Bridge
#
# If anything looks wrong it stops BEFORE touching the node. You can re-run it.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$SCRIPT_DIR"
STAGE="$(mktemp -d)"

fail() { echo "ERROR: $1" >&2; exit 1; }
info() { echo "== $1"; }

# ini_password FILE SECTION -- print the Password= value from [SECTION] of an
# ini file, with surrounding quotes stripped. Ignores __SET_...__ markers (they
# mean "not filled in") and prints nothing when the value is missing.
ini_password() {
  [[ -f "$1" ]] || return 0
  awk -v sec="$2" '
    /^\[/ { cur = $0; sub(/^\[/,"",cur); sub(/\]$/,"",cur) }
    cur == sec && /^[[:space:]]*Password[[:space:]]*=/ {
      v = $0; sub(/^[^=]*=/,"",v)
      gsub(/^[[:space:]]+|[[:space:]]+$/,"",v)
      sub(/^"/,"",v); sub(/"$/,"",v)
      if (v != "" && v !~ /^__SET_[A-Za-z0-9_]+__$/) print v
      exit
    }
  ' "$1"
}

# set_password FILE MARKER VALUE -- replace the whole line Password="MARKER"
# with Password="VALUE". awk string assignment is literal, so passwords
# containing &, \, quotes or spaces are written safely (sed would mangle them).
set_password() {
  awk -v m="$2" -v p="$3" '
    $0 == "Password=\"" m "\"" { $0 = "Password=\"" p "\"" }
    { print }
  ' "$1" > "$1.new" && mv "$1.new" "$1"
}

[[ $EUID -eq 0 ]] || fail "run this with sudo"
for f in DMRGateway.ini MMDVM_Bridge.ini Analog_Bridge.ini dmrgateway.service; do
  [[ -f "$SRC_DIR/$f" ]] || fail "source file missing: $SRC_DIR/$f"
done

# 0. DMRGateway must be installed (it does not come with DVSwitch).
[[ -x /usr/local/bin/DMRGateway ]] || fail "DMRGateway not found at /usr/local/bin/DMRGateway -- run: sudo bash $SCRIPT_DIR/../../scripts/build-dmrgateway.sh first"

DG_DIR=/opt/DMRGateway
mkdir -p "$DG_DIR" || fail "cannot create $DG_DIR"
DG_DST="$DG_DIR/DMRGateway.ini"
MM_DST=/opt/MMDVM_Bridge/MMDVM_Bridge.ini
AB_DST=/opt/Analog_Bridge/Analog_Bridge.ini
for d in "$DG_DIR" "$(dirname "$MM_DST")" "$(dirname "$AB_DST")"; do
  [[ -d "$d" ]] || fail "expected install dir missing: $d (is DVSwitch Server installed?)"
done
# NOTE: /opt/MMDVM_Bridge/DVSwitch.ini is intentionally left alone -- the stock
# [DMR] partner ports (txPort=31100/rxPort=31103) are already correct.

# Install the systemd unit for DMRGateway. Overwrite if it exists but points
# to the wrong config path (e.g. /etc/dmrgateway vs /opt/DMRGateway).
UNIT_SRC="$SRC_DIR/dmrgateway.service"
UNIT_DST="/etc/systemd/system/dmrgateway.service"
NEED_UNIT=0
if [[ ! -f "$UNIT_DST" ]]; then
  NEED_UNIT=1
elif ! grep -q "ExecStart=/usr/local/bin/DMRGateway /opt/DMRGateway/DMRGateway.ini" "$UNIT_DST"; then
  info "existing dmrgateway.service points to wrong config path -- replacing"
  NEED_UNIT=1
fi
if [[ $NEED_UNIT -eq 1 ]]; then
  info "installing dmrgateway.service systemd unit"
  cp -p "$UNIT_SRC" "$UNIT_DST"
  systemctl daemon-reload
  systemctl enable dmrgateway.service
else
  info "dmrgateway.service already installed"
fi

# 1. Backup live configs.
TS=$(date +%Y%m%d-%H%M%S)
BACKUP="/root/dmr-config-backup-$TS"
mkdir -p "$BACKUP" || fail "cannot create $BACKUP"
info "backing up live configs to $BACKUP"
for f in "$DG_DST" "$MM_DST" "$AB_DST"; do
  [[ -f "$f" ]] && cp -p "$f" "$BACKUP/" && echo "  saved $(basename "$f")"
done

# 2. Stage copies and fill in passwords. First try to reuse passwords the node
#    already has, so nothing has to be re-entered:
#      BrandMeister: [DMR Network 1] of an existing /opt/DMRGateway/DMRGateway.ini,
#                    else [DMR Network] of the stock /opt/MMDVM_Bridge/MMDVM_Bridge.ini
#      TGIF        : [DMR Network 2] of an existing /opt/DMRGateway/DMRGateway.ini
# NOTE: the repo's Analog_Bridge.ini is staged for VALIDATION ONLY. The node's
# live Analog_Bridge.ini is never overwritten (Oct 13 2026: an earlier version
# of this script wiped Sam's multi-mode Analog_Bridge.ini); it is installed
# only when the node has none at all.
cp -p "$SRC_DIR"/DMRGateway.ini "$SRC_DIR"/MMDVM_Bridge.ini "$SRC_DIR"/Analog_Bridge.ini "$STAGE/" \
  || fail "cannot stage configs"

BM_PW=""; TGIF_PW=""; BM_SRC=""; TGIF_SRC=""
if [[ -f "$DG_DST" ]]; then
  BM_PW="$(ini_password "$DG_DST" "DMR Network 1")"
  [[ -n "$BM_PW" ]] && BM_SRC="$DG_DST"
  TGIF_PW="$(ini_password "$DG_DST" "DMR Network 2")"
  [[ -n "$TGIF_PW" ]] && TGIF_SRC="$DG_DST"
fi
if [[ -z "$BM_PW" && -f "$MM_DST" ]]; then
  BM_PW="$(ini_password "$MM_DST" "DMR Network")"
  [[ -n "$BM_PW" ]] && BM_SRC="$MM_DST"
fi

echo
if [[ -n "$BM_PW" ]]; then
  info "reusing BrandMeister hotspot password found in $BM_SRC (no need to re-enter)"
else
  read -r -s -p "BrandMeister hotspot security password: " BM_PW; echo
fi
if [[ -n "$TGIF_PW" ]]; then
  info "reusing TGIF password found in $TGIF_SRC (no need to re-enter)"
else
  read -r -s -p "TGIF hotspot password: " TGIF_PW; echo
fi
[[ -n "$BM_PW" && -n "$TGIF_PW" ]] || fail "empty password(s) -- aborting, nothing changed"

set_password "$STAGE/DMRGateway.ini" "__SET_BM_HOTSPOT_PASSWORD__" "$BM_PW"
set_password "$STAGE/DMRGateway.ini" "__SET_TGIF_PASSWORD__" "$TGIF_PW"
if grep -q '^Password=.*__SET_' "$STAGE/DMRGateway.ini"; then
  fail "password substitution did not complete -- aborting, nothing changed"
fi
info "passwords substituted in staged copy"

# 3. Validate the staged set.
VALIDATOR="$SCRIPT_DIR/../../scripts/validate-dmr-configs.sh"
if [[ -x "$VALIDATOR" || -f "$VALIDATOR" ]]; then
  info "validating staged configs"
  bash "$VALIDATOR" "$STAGE" || fail "validation failed -- aborting, nothing changed"
else
  echo "warn: validator not found at $VALIDATOR, skipping"
fi

# 4. Install. The node's existing Analog_Bridge.ini is PRESERVED -- the repo
#    copy is a reference for fresh installs only (see step 2 note).
info "installing configs"
cp -p "$STAGE/DMRGateway.ini" "$DG_DST"
cp -p "$STAGE/MMDVM_Bridge.ini" "$MM_DST"
if [[ -f "$AB_DST" ]]; then
  info "preserving existing $AB_DST -- repo Analog_Bridge.ini not installed"
else
  info "no existing $AB_DST -- installing repo reference copy"
  cp -p "$STAGE/Analog_Bridge.ini" "$AB_DST"
fi
rm -rf "$STAGE"
unset BM_PW TGIF_PW BM_SRC TGIF_SRC

# 5. Restart the bridge chain in order. Unit names vary by install, so only
#    restart units that actually exist; report anything we could not find.
info "restarting bridge chain (DMRGateway -> MMDVM_Bridge -> Analog_Bridge)"
for unit in dmrgateway mmdvm_bridge analog_bridge; do
  if systemctl cat "$unit" >/dev/null 2>&1; then
    systemctl restart "$unit" && echo "  restarted $unit"
  else
    echo "  note: systemd unit '$unit' not found -- restart it manually if it runs another way"
  fi
done

echo
info "done. Backup is in $BACKUP."
echo "Test it:  sudo /opt/MMDVM_Bridge/dvswitch.sh tune 91"
echo "If something is off, restore with:  sudo cp $BACKUP/*.ini <back to /opt/...> && restart the chain."

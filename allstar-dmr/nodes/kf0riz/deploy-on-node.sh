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
#   3. Stages the new configs, asks for the two hotspot passwords (typed, hidden,
#      never written to disk or committed), and substitutes the __SET_...__ markers
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

# Install the systemd unit for DMRGateway if it is not already there.
if [[ ! -f /etc/systemd/system/dmrgateway.service ]]; then
  info "installing dmrgateway.service systemd unit"
  cp -p "$SRC_DIR/dmrgateway.service" /etc/systemd/system/dmrgateway.service
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

# 2. Stage copies and fill in passwords.
cp -p "$SRC_DIR"/DMRGateway.ini "$SRC_DIR"/MMDVM_Bridge.ini "$SRC_DIR"/Analog_Bridge.ini "$STAGE/" \
  || fail "cannot stage configs"

sed_escape() { printf '%s' "$1" | sed 's/[&/\]/\\&/g'; }

echo
echo "Enter hotspot passwords (input hidden; never stored or committed)."
echo "Leave blank to abort."
read -r -s -p "BrandMeister hotspot security password: " BM_PW; echo
read -r -s -p "TGIF hotspot password: " TGIF_PW; echo
[[ -n "$BM_PW" && -n "$TGIF_PW" ]] || fail "empty password(s) -- aborting, nothing changed"

sed -i "s/^Password=\"__SET_BM_HOTSPOT_PASSWORD__\"$/Password=\"$(sed_escape "$BM_PW")\"/" "$STAGE/DMRGateway.ini"
sed -i "s/^Password=\"__SET_TGIF_PASSWORD__\"$/Password=\"$(sed_escape "$TGIF_PW")\"/" "$STAGE/DMRGateway.ini"
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

# 4. Install.
info "installing configs"
cp -p "$STAGE/DMRGateway.ini" "$DG_DST"
cp -p "$STAGE/MMDVM_Bridge.ini" "$MM_DST"
cp -p "$STAGE/Analog_Bridge.ini" "$AB_DST"
rm -rf "$STAGE"
unset BM_PW TGIF_PW

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

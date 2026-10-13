#!/usr/bin/env bash
# build-dmrgateway.sh -- build and install DMRGateway from source.
#
# DMRGateway is NOT in the DVSwitch apt repo and NOT configured by the dvs
# menu, so multi-mode DMR needs this separate step. Run with sudo on the node:
#   sudo bash scripts/build-dmrgateway.sh
#
# Clones/updates github.com/g4klx/DMRGateway into /opt/DMRGateway-src,
# builds it, and installs the binary to /usr/local/bin/DMRGateway.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }

echo "== installing build dependencies"
apt update
apt install -y git build-essential patch libmosquitto-dev nlohmann-json3-dev

SRC=/opt/DMRGateway-src
# Use a known-stable commit (20240831, GitID #29397cf).
# NOTE (Oct 13 2026): vanilla DMRGateway at ANY commit cannot talk to DVSwitch
# MMDVM_Bridge -- MMDVM_Bridge always logs in with the direct-mode "RPTL"
# handshake (it has no MMDVMHost-style Type=Gateway option), while DMRGateway's
# local side only accepts the "DMRC" config packet. Result: "Unknown packet
# from the MMDVM" forever and the gateway never starts its DMR networks
# (it waits for the local login first). See scripts/dmrgateway-rptl-login.patch,
# applied below, which emulates the network side of the RPTL handshake.
# (g4klx/DMRGateway issue #107 is the same failure with MMDVMHost Type=Direct.)
STABLE_COMMIT="29397cf"
PATCH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dmrgateway-rptl-login.patch"
if [[ -d "$SRC/.git" ]]; then
  echo "== updating existing source in $SRC"
  git -C "$SRC" fetch
else
  echo "== cloning DMRGateway source"
  git clone https://github.com/g4klx/DMRGateway.git "$SRC"
fi
cd "$SRC"
echo "== checking out stable commit $STABLE_COMMIT"
git checkout "$STABLE_COMMIT" 2>/dev/null || {
  echo "Commit $STABLE_COMMIT not found, trying master (may be incompatible)"
  git checkout master
}

if grep -q 'MMDVM, RPTL login from' MMDVMNetwork.cpp 2>/dev/null; then
  echo "== MMDVM_Bridge RPTL login patch already applied, skipping"
else
  echo "== applying MMDVM_Bridge RPTL login patch"
  [[ -f "$PATCH" ]] || { echo "Patch file missing: $PATCH" >&2; exit 1; }
  patch -p1 < "$PATCH"
fi

echo "== building"
make -j"$(nproc)"

echo "== installing to /usr/local/bin/DMRGateway"
make install
/usr/local/bin/DMRGateway --version

echo
echo "Installed. Next:"
echo "  1. sudo mkdir -p /opt/DMRGateway"
echo "  2. Copy nodes/kf0riz/DMRGateway.ini to /opt/DMRGateway/DMRGateway.ini"
echo "     (or run nodes/kf0riz/deploy-on-node.sh, which does steps 2-5)"
echo "  3. Fill in the __SET_...__ password markers in that file"
echo "  4. Install the systemd unit: nodes/kf0riz/dmrgateway.service ->"
echo "     /etc/systemd/system/dmrgateway.service, then"
echo "     sudo systemctl daemon-reload && sudo systemctl enable --now dmrgateway"

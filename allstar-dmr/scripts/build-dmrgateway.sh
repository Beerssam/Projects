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
apt install -y git build-essential

SRC=/opt/DMRGateway-src
if [[ -d "$SRC/.git" ]]; then
  echo "== updating existing source in $SRC"
  git -C "$SRC" pull --ff-only
else
  echo "== cloning DMRGateway source"
  git clone https://github.com/g4klx/DMRGateway.git "$SRC"
  cd "$SRC"
fi

echo "== building"
cd "$SRC"
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

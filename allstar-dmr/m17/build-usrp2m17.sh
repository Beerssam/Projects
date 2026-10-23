#!/usr/bin/env bash
# build-usrp2m17.sh -- build and install USRP2M17 from source.
#
# USRP2M17 (from nostar/MMDVM_CM, Tom N7TAE) bridges an M17 reflector to an
# AllStar USRP node. It is not packaged anywhere, so -- like DMRGateway --
# it is built from source on the node. Run with sudo on the node:
#   sudo bash allstar-dmr/m17/build-usrp2m17.sh
#
# Clones/updates github.com/nostar/MMDVM_CM into /opt/MMDVM_CM-src, builds
# the USRP2M17 subdirectory (Codec2 is bundled in the tree; the binary links
# only libm/pthread), and installs it to /usr/local/bin/USRP2M17.
#
# Env overrides (used by off-node fixture tests; defaults are the node paths):
#   SRC, BIN, SKIP_APT=1
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }

if [[ "${SKIP_APT:-0}" != "1" ]]; then
  echo "== installing build dependencies"
  apt update
  apt install -y git build-essential
fi

SRC="${SRC:-/opt/MMDVM_CM-src}"
BIN="${BIN:-/usr/local/bin/USRP2M17}"
# Pinned to the commit verified on Muse's VM Oct 23 2026 (built + ran).
STABLE_COMMIT="1dd5383c53d4780b3074cde495d8987ba878ce7b"

if [[ -d "$SRC/.git" ]]; then
  echo "== updating existing source in $SRC"
  git -C "$SRC" fetch
else
  echo "== cloning MMDVM_CM source"
  git clone https://github.com/nostar/MMDVM_CM.git "$SRC"
fi
cd "$SRC"
echo "== checking out stable commit $STABLE_COMMIT"
git checkout "$STABLE_COMMIT" 2>/dev/null || {
  echo "Commit $STABLE_COMMIT not found, trying master (may be incompatible)"
  git checkout master
}

# Compiler-compat patches (idempotent). GCC 13+ no longer transitively
# provides <cstdint>, so uint32_t/uint16_t/uint8_t are undeclared in two
# headers. The node (bookworm, GCC 12) may not need these; applying them is
# harmless either way. Same grep-marker pattern as build-dmrgateway.sh.
for hdr in USRP2M17/Conf.h USRP2M17/ModeConv.h; do
  if grep -q '#include <cstdint>' "$hdr"; then
    echo "== <cstdint> already in $hdr, skipping"
  else
    echo "== adding <cstdint> to $hdr"
    sed -i '0,/#include/s//#include <cstdint>\n#include/' "$hdr"
  fi
done

echo "== building USRP2M17"
make -C USRP2M17 -j"$(nproc)"

echo "== installing to $BIN"
install -m 755 USRP2M17/USRP2M17 "$BIN"
"$BIN" -v || true

echo
echo "Installed. Next: sudo bash allstar-dmr/m17/install-m17.sh"
echo "(installs the ini + systemd unit, adds private node 1998 to rpt.conf,"
echo " restarts Asterisk once, and verifies the reflector connection)"

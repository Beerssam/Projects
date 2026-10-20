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

# Patch set applied by this script, in order (Oct 19 2026):
#   1. dmrgateway-rptl-login.patch      (Oct 13: MMDVM_Bridge RPTL handshake)
#   2. dmrgateway-scan-rewrite.patch    (Oct 13: TGIF scan TG rewrite)
#   3. dmrgateway-scan-logchange.patch  (Oct 14: scan log throttling)
#   4. dmrgateway-private-call.patch    (Oct 15: 9990 group->private conversion)
#   5. dmrgateway-rptc-passthrough.patch (Oct 19: BM RPTC passthrough)
#   6. dmrgateway-rptc-wirelog.patch     (Oct 20: RPTC payload source +
#                                         per-send wire logging)
#   7. dmrgateway-rptcl-guard.patch      (Oct 20: RPTCL/RPTC prefix
#                                         collision -- the BM root cause)

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
# STABLE_COMMIT="29397cf" plus the RPTL patch is the known-good baseline.
#
# NOTE (Oct 13 2026): TGIF 777 is a "scan" TG -- the user tunes to 4000777 but
# TGIF returns traffic on other TGs (e.g. 4006282). MMDVM_Bridge's export
# filter (exportTG=0 in DVSwitch.ini, "follow the tuned TG") drops anything
# that doesn't match the tuned TG, so scan audio never reaches Analog_Bridge.
# MMDVM_Bridge is closed-source and can't be patched; instead
# scripts/dmrgateway-scan-rewrite.patch (applied below) makes DMRGateway
# rewrite inbound network TG to the last-seen TX TG per slot, with logging.
# TX path (MMDVM->network) is untouched.
STABLE_COMMIT="29397cf"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RPTL_PATCH="$SCRIPT_DIR/dmrgateway-rptl-login.patch"
SCAN_PATCH="$SCRIPT_DIR/dmrgateway-scan-rewrite.patch"
LOGCHANGE_PATCH="$SCRIPT_DIR/dmrgateway-scan-logchange.patch"
PRIVATECALL_PATCH="$SCRIPT_DIR/dmrgateway-private-call.patch"
RPTC_PATCH="$SCRIPT_DIR/dmrgateway-rptc-passthrough.patch"
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
  [[ -f "$RPTL_PATCH" ]] || { echo "Patch file missing: $RPTL_PATCH" >&2; exit 1; }
  patch -p1 < "$RPTL_PATCH"
fi

if grep -q 'processScanRewrite' DMRGateway.cpp 2>/dev/null; then
  echo "== TGIF scan rewrite patch already applied, skipping"
else
  echo "== applying TGIF scan rewrite patch"
  [[ -f "$SCAN_PATCH" ]] || { echo "Patch file missing: $SCAN_PATCH" >&2; exit 1; }
  patch -p1 < "$SCAN_PATCH"
fi

# Follow-up (Oct 14 2026): the scan rewrite logs once per voice frame
# (~17 lines/sec) while debugging. This keeps the rewrite on every frame
# but only logs when the (slot, dst -> tuned) mapping changes. Depends on
# the scan rewrite patch above, so it must come after it.
if grep -q 'm_scanLoggedDst' DMRGateway.h 2>/dev/null; then
  echo "== scan log-change patch already applied, skipping"
else
  echo "== applying scan log-change patch"
  [[ -f "$LOGCHANGE_PATCH" ]] || { echo "Patch file missing: $LOGCHANGE_PATCH" >&2; exit 1; }
  patch -p1 < "$LOGCHANGE_PATCH"
fi

# (Oct 15 2026): the DVSwitch chain (dvswitch.sh tune -> MMDVM_Bridge) can
# only emit group-call frames, so there is no way to place a real private
# call (e.g. BrandMeister Parrot 9990) from the dashboard tune path.
# scripts/dmrgateway-private-call.patch (applied below) converts group-call
# frames addressed to service TGs (9990) into private calls before the
# rewrite rules are tried, so the existing PCRewrite rules route them.
# Depends on nothing else, but kept last for a stable patch order.
if grep -q 'convertToPrivateCall' DMRGateway.cpp 2>/dev/null; then
  echo "== private-call patch already applied, skipping"
else
  echo "== applying private-call patch"
  [[ -f "$PRIVATECALL_PATCH" ]] || { echo "Patch file missing: $PRIVATECALL_PATCH" >&2; exit 1; }
  patch -p1 < "$PRIVATECALL_PATCH"
fi

# (Oct 19-20 2026): BrandMeister fix. DMRGateway rebuilt the RPTC config
# message by hand in CDMRGateway::getConfig(), reading the tail fields
# (flags byte, software name/version, package ID) from wrong offsets of the
# MMDVM_Bridge RPTC payload (MMDVM_Bridge formats latitude without a '+'
# sign, so the sprintf layout grabbed garbage there). TGIF/KS-DMR ignore
# those fields; BrandMeister validates them and rejected the login ~50ms
# after the RPTC ("Login to the master has failed"). A direct
# MMDVM_Bridge->BM connection proved the MMDVM's own 294-byte RPTC is
# accepted, so getConfig() now passes it through verbatim.
# Primary vehicle is scripts/dmrgateway-rptc-passthrough.patch (repo
# convention); the python fallback below covers the case where the patch
# context ever drifts from the pinned commit. Both are idempotent via the
# same marker comment. Kept last: it touches nothing the patches above
# depend on.
PASSTHROUGH_PATCH="$SCRIPT_DIR/dmrgateway-rptc-passthrough.patch"
PASSTHROUGH_PY="$SCRIPT_DIR/dmrgateway-rptl-passthrough.py"
if grep -q 'RPTL/DVSwitch fix: pass the MMDVM' DMRGateway.cpp 2>/dev/null; then
  echo "== RPTC passthrough already applied, skipping"
elif [[ -f "$PASSTHROUGH_PATCH" ]] && patch -p1 --dry-run --silent < "$PASSTHROUGH_PATCH" 2>/dev/null; then
  echo "== applying RPTC passthrough patch (BrandMeister fix)"
  patch -p1 < "$PASSTHROUGH_PATCH"
else
  echo "== passthrough patch did not apply cleanly, using python fallback"
  [[ -f "$PASSTHROUGH_PY" ]] || { echo "Fallback script missing: $PASSTHROUGH_PY" >&2; exit 1; }
  python3 "$PASSTHROUGH_PY" DMRGateway.cpp
fi

# (Oct 19 2026): vanilla getConfig() REBUILDS the RPTC it sends upstream
# with an sprintf whose tail fields (flags byte, software, package) are
# read from m_config offsets 30/31/71 -- correct for an MMDVMHost layout,
# wrong for MMDVM_Bridge, which writes its latitude unsigned
# ("39.00999..."), so those fields come out as garbage. Lenient networks
# (TGIF, KS-DMR) accept the mangled RPTC; BrandMeister validates strictly
# and rejected the login ~50ms after the RPTC ("Login to the master has
# failed") even though the password was right -- BM direct from
# MMDVM_Bridge worked fine. scripts/dmrgateway-rptc-passthrough.patch
# makes getConfig() pass the MMDVM's captured RPTC payload through
# verbatim instead. Verified Oct 19 2026: "BM_3103, Logged into the
# master successfully" and BM self-care "Repeater 320968633 verified".
# Must be applied AFTER the other DMRGateway.cpp patches.
if grep -q 'MMDVM passthrough' DMRGateway.cpp 2>/dev/null; then
  echo "== RPTC passthrough patch already applied, skipping"
else
  echo "== applying RPTC passthrough patch"
  [[ -f "$RPTC_PATCH" ]] || { echo "Patch file missing: $RPTC_PATCH" >&2; exit 1; }
  patch -p1 < "$RPTC_PATCH"
fi

# (Oct 20 2026): RPTC wire log + payload source hardening. After the
# 21:36 redeploy (all three networks enabled), BM logins timed out 60s
# after "Sending configuration" with no BM self-care entry, while the
# passthrough "configuration message" line stopped appearing in the
# journal entirely -- the RPTC path had no trustworthy observability.
# This patch: (a) getConfig() takes the payload from the gateway's own
# captured copy (m_config/m_configLen, filled by run()'s startup wait
# loop, which only proceeds once the full RPTC has been captured)
# instead of re-reading the repeater object at network-creation time;
# (b) CDMRNetwork::setConfig logs the stored config size at creation;
# (c) CDMRNetwork::writeConfig logs the exact RPTC size on EVERY send
# (including the silent retry resends) and errors loudly if the stored
# config is empty. Marker: 'RPTC config stored' in DMRNetwork.cpp.
# Must come after the passthrough patch (it edits its getConfig body).
WIRELOG_PATCH="$SCRIPT_DIR/dmrgateway-rptc-wirelog.patch"
if grep -q 'RPTC config stored' DMRNetwork.cpp 2>/dev/null; then
  echo "== RPTC wire-log patch already applied, skipping"
else
  echo "== applying RPTC wire-log patch"
  [[ -f "$WIRELOG_PATCH" ]] || { echo "Patch file missing: $WIRELOG_PATCH" >&2; exit 1; }
  patch -p1 < "$WIRELOG_PATCH"
fi

# (Oct 20 2026): THE BrandMeister root cause. In CMMDVMNetwork::clock()
# (added by the RPTL patch), the config capture matches any packet
# starting with "RPTC" and stores length-8 bytes, first packet only.
# The 9-byte RPTCL logout that MMDVM_Bridge sends when it stops or
# restarts also starts with "RPTC" -- and the dedicated RPTCL branch
# sat AFTER the RPTC branch, unreachable. A restart therefore latched
# a 1-byte "config" before the real 294-byte RPTC arrived, and every
# network sent a 9-byte RPTC from then on. BM silently discards those
# (60s timeout, no self-care entry); TGIF/KS-DMR do not validate the
# config and logged in fine -- which is why BM broke exactly when the
# multi-network setup was redeployed (joint restart order: gateway
# first, then MMDVM_Bridge logs out its old session into it) while
# the 20:20 single-network test, built with both services stopped,
# logged in clean. Fix: match RPTCL BEFORE RPTC, and only store an
# RPTC whose length shows a real payload (> 9 bytes). Marker:
# 'must be matched BEFORE RPTC' in MMDVMNetwork.cpp. Applies last;
# touches only MMDVMNetwork.cpp.
RPTCL_PATCH="$SCRIPT_DIR/dmrgateway-rptcl-guard.patch"
if grep -q 'must be matched BEFORE RPTC' MMDVMNetwork.cpp 2>/dev/null; then
  echo "== RPTCL guard patch already applied, skipping"
else
  echo "== applying RPTCL guard patch"
  [[ -f "$RPTCL_PATCH" ]] || { echo "Patch file missing: $RPTCL_PATCH" >&2; exit 1; }
  patch -p1 < "$RPTCL_PATCH"
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

#!/usr/bin/env bash
# Install DVSwitch Server on Debian 12 (bookworm) / AllStarLink ASL3.
# Run as root:  sudo bash scripts/install-dvswitch-bookworm.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

if ! grep -q 'bookworm' /etc/os-release 2>/dev/null; then
  echo "WARNING: this script is for Debian 12 bookworm (ASL3). Detected:" >&2
  grep PRETTY_NAME /etc/os-release >&2 || true
  read -rp "Continue anyway? [y/N] " ans
  [[ "$ans" == [Yy]* ]] || exit 1
fi

cd /tmp
wget -O bookworm dvswitch.org/bookworm
chmod +x bookworm
./bookworm
apt update
apt install -y dvswitch-server

echo
echo "Installed. Next (as root):  cd /usr/local/dvs && ./dvs"
echo "Use the menu to get single-network DMR working BEFORE layering"
echo "the multi-mode templates from this project on top."
echo "Do NOT use dvswitch.org/trixie on ASL3/bookworm systems."

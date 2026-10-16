#!/usr/bin/env bash
# enable-ysf-mode.sh -- Enable System Fusion (YSF/FCS) in MMDVM_Bridge
#
# This adds the [System Fusion] mode section and enables [System Fusion Network]
# in /opt/MMDVM_Bridge/MMDVM_Bridge.ini so that `dvswitch.sh mode YSF` and
# `dvswitch.sh tune <reflector>` actually work.
#
# Background: The node's MMDVM_Bridge.ini was DMR-only (no [System Fusion]
# mode section, [System Fusion Network] Enable=0). The dvswitch.sh mode
# command only changes Analog_Bridge's codec and TLV ports -- it does NOT
# reconfigure MMDVM_Bridge. Without the mode section, MMDVM_Bridge ignores
# YSF entirely, which is why YSF tune commands went nowhere.
#
# Usage: sudo bash enable-ysf-mode.sh
# The script backs up the original ini, applies changes, and restarts
# mmdvm_bridge. DMR config is untouched.

set -e
INI="/opt/MMDVM_Bridge/MMDVM_Bridge.ini"
BACKUP="/opt/MMDVM_Bridge/MMDVM_Bridge.ini.bak-ysf-$(date +%Y%m%d-%H%M%S)"

if [[ ! -f "$INI" ]]; then
  echo "ERROR: $INI not found"
  exit 1
fi

echo "Backing up to $BACKUP"
cp "$INI" "$BACKUP"

# 1. Add [System Fusion] mode section if missing (insert before [DMR Network])
if ! grep -q "^\[System Fusion\]$" "$INI"; then
  echo "Adding [System Fusion] mode section..."
  python3 << 'PYEOF'
import re
ini_path = "/opt/MMDVM_Bridge/MMDVM_Bridge.ini"
with open(ini_path) as f:
    content = f.read()

ysf_mode = """[System Fusion]
Enable=1

"""

# Insert before [DMR Network] (or at end of mode sections)
if "[DMR Network]" in content:
    content = content.replace("[DMR Network]", ysf_mode + "[DMR Network]", 1)
else:
    content = content.rstrip() + "\n\n" + ysf_mode

with open(ini_path, "w") as f:
    f.write(content)
print("Added [System Fusion] section")
PYEOF
else
  echo "[System Fusion] already exists, ensuring Enable=1..."
  sed -i '/^\[System Fusion\]/,/^\[/ s/^Enable=.*/Enable=1/' "$INI"
fi

# 2. Enable [System Fusion Network] and set ports for YSFGateway
echo "Configuring [System Fusion Network]..."
python3 << 'PYEOF'
import re
ini_path = "/opt/MMDVM_Bridge/MMDVM_Bridge.ini"
with open(ini_path) as f:
    content = f.read()

# Replace the [System Fusion Network] section
pattern = r'\[System Fusion Network\].*?(?=\n\[|\Z)'
replacement = """[System Fusion Network]
Enable=1
LocalAddress=127.0.0.1
LocalPort=3210
GatewayAddress=127.0.0.1
GatewayPort=3200
Debug=0
"""
content = re.sub(pattern, replacement.strip(), content, flags=re.DOTALL)

with open(ini_path, "w") as f:
    f.write(content)
print("Configured [System Fusion Network] -> YSFGateway 127.0.0.1:3200")
PYEOF

echo ""
echo "Changes applied. Restarting mmdvm_bridge..."
systemctl restart mmdvm_bridge
sleep 3

echo ""
echo "Verifying..."
if systemctl is-active --quiet mmdvm_bridge; then
  echo "mmdvm_bridge is running"
else
  echo "WARNING: mmdvm_bridge failed to start! Restoring backup..."
  cp "$BACKUP" "$INI"
  systemctl restart mmdvm_bridge
  echo "Restored from $BACKUP"
  exit 1
fi

echo ""
echo "Done. Test with:"
echo "  sudo /opt/MMDVM_Bridge/dvswitch.sh mode YSF"
echo "  sudo /opt/MMDVM_Bridge/dvswitch.sh tune 900155  # FCS00155"
echo ""
echo "Backup saved at: $BACKUP"

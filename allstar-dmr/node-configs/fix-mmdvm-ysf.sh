#!/usr/bin/env bash
# fix-mmdvm-ysf.sh -- Add YSF support to MMDVM_Bridge without breaking it
#
# This script adds the [System Fusion] mode section to MMDVM_Bridge.ini
# correctly (unlike the broken enable-ysf-mode.sh v1).
#
# Usage: sudo bash fix-mmdvm-ysf.sh
#
# What it does:
#   1. Backs up /opt/MMDVM_Bridge/MMDVM_Bridge.ini
#   2. Adds [System Fusion] Enable=1 (if missing)
#   3. Configures [System Fusion Network] for YSFGateway
#   4. Restarts mmdvm_bridge and verifies it's active
#
# P25/NXDN are left disabled (Enable=0) - they cause SIGABRT if enabled
# with incomplete parameters. YSF is the priority.

set -e
INI="/opt/MMDVM_Bridge/MMDVM_Bridge.ini"
BACKUP="/opt/MMDVM_Bridge/MMDVM_Bridge.ini.bak-ysf-fix-$(date +%Y%m%d-%H%M%S)"

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)."; exit 1; }
[[ -f "$INI" ]] || { echo "ERROR: $INI not found"; exit 1; }

echo "== Backing up to $BACKUP"
cp "$INI" "$BACKUP"

# 1. Add [System Fusion] mode section if missing
if ! grep -q "^\[System Fusion\]$" "$INI"; then
    echo "== Adding [System Fusion] mode section..."
    # Insert before [DMR] line (not [DMR Network], to avoid the annotated header issue)
    # Use awk for safe insertion
    awk '
        /^\[DMR\]$/ && !done {
            print "[System Fusion]"
            print "Enable=1"
            print ""
            done=1
        }
        { print }
    ' "$INI" > "${INI}.tmp" && mv "${INI}.tmp" "$INI"
    echo "   Added."
else
    echo "== [System Fusion] already exists, ensuring Enable=1..."
    sed -i '/^\[System Fusion\]/,/^\[/ s/^Enable=.*/Enable=1/' "$INI"
fi

# 2. Configure [System Fusion Network]
echo "== Configuring [System Fusion Network]..."
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
Debug=0"""
content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open(ini_path, "w") as f:
    f.write(content)
print("   Configured -> YSFGateway 127.0.0.1:3200")
PYEOF

# 3. Verify no duplicate sections
echo "== Checking for duplicate sections..."
dups=$(grep -E "^\[.+\]$" "$INI" | sort | uniq -d)
if [[ -n "$dups" ]]; then
    echo "ERROR: Duplicate sections found:"
    echo "$dups"
    echo "Restoring backup..."
    cp "$BACKUP" "$INI"
    exit 1
fi
echo "   No duplicates."

# 4. Restart and verify
echo "== Restarting mmdvm_bridge..."
systemctl restart mmdvm_bridge
sleep 3

if systemctl is-active --quiet mmdvm_bridge; then
    echo "== SUCCESS: mmdvm_bridge is active"
    echo ""
    echo "Verify YSF is enabled:"
    echo "  sudo grep -i 'ysf:' /var/log/mmdvm/MMDVM_Bridge-\$(date +%Y-%m-%d).log | tail -3"
    echo ""
    echo "Test YSF tune:"
    echo "  sudo /opt/MMDVM_Bridge/dvswitch.sh mode YSF"
    echo "  sudo /opt/MMDVM_Bridge/dvswitch.sh tune 900155  # FCS00155"
else
    echo "ERROR: mmdvm_bridge failed to start! Restoring backup..."
    cp "$BACKUP" "$INI"
    systemctl restart mmdvm_bridge
    echo "Restored from $BACKUP"
    exit 1
fi

echo ""
echo "Backup saved at: $BACKUP"

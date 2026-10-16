#!/usr/bin/env bash
# backup-node-configs.sh -- Backup node configs to GitHub
#
# Backs up critical DVSwitch/AllStar configs (passwords redacted) to the
# Beerssam/Projects repo under allstar-dmr/node-configs/backups/.
#
# Usage: bash backup-node-configs.sh
# Run manually after config changes, or via cron for regular backups.
#
# The script:
# 1. Copies configs to /tmp with passwords redacted
# 2. Commits to the local git repo (/home/ASL3/Projects)
# 3. Prints instructions for pushing (requires GitHub token, not password)
#
# NOTE: GitHub no longer accepts password auth. To push from the node:
#   1. Create a Personal Access Token at https://github.com/settings/tokens
#      (scope: repo)
#   2. Use it as the password when pushing, OR
#   3. Let Muse push via the API (preferred - no token needed on node)

set -e
REPO="/home/ASL3/Projects"
BACKUP_DIR="$REPO/allstar-dmr/node-configs/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "Backing up configs (passwords redacted)..."

# MMDVM_Bridge
if [[ -f /opt/MMDVM_Bridge/MMDVM_Bridge.ini ]]; then
  grep -v -i "password" /opt/MMDVM_Bridge/MMDVM_Bridge.ini \
    > "$BACKUP_DIR/MMDVM_Bridge.ini.$TIMESTAMP" 2>/dev/null || \
  cp /opt/MMDVM_Bridge/MMDVM_Bridge.ini "$BACKUP_DIR/MMDVM_Bridge.ini.$TIMESTAMP"
  echo "  MMDVM_Bridge.ini"
fi

# DVSwitch.ini
if [[ -f /opt/MMDVM_Bridge/DVSwitch.ini ]]; then
  grep -v -i "password" /opt/MMDVM_Bridge/DVSwitch.ini \
    > "$BACKUP_DIR/DVSwitch.ini.$TIMESTAMP" 2>/dev/null || \
  cp /opt/MMDVM_Bridge/DVSwitch.ini "$BACKUP_DIR/DVSwitch.ini.$TIMESTAMP"
  echo "  DVSwitch.ini"
fi

# Analog_Bridge (CRITICAL: never overwrite this with a restore!)
if [[ -f /opt/Analog_Bridge/Analog_Bridge.ini ]]; then
  grep -v -i "password" /opt/Analog_Bridge/Analog_Bridge.ini \
    > "$BACKUP_DIR/Analog_Bridge.ini.$TIMESTAMP" 2>/dev/null || \
  cp /opt/Analog_Bridge/Analog_Bridge.ini "$BACKUP_DIR/Analog_Bridge.ini.$TIMESTAMP"
  echo "  Analog_Bridge.ini (REFERENCE ONLY - never auto-restore)"
fi

# DMRGateway
if [[ -f /opt/DMRGateway/DMRGateway.ini ]]; then
  grep -v -i "password" /opt/DMRGateway/DMRGateway.ini \
    > "$BACKUP_DIR/DMRGateway.ini.$TIMESTAMP" 2>/dev/null || \
  cp /opt/DMRGateway/DMRGateway.ini "$BACKUP_DIR/DMRGateway.ini.$TIMESTAMP"
  echo "  DMRGateway.ini"
fi

# YSFGateway
if [[ -f /opt/YSFGateway/YSFGateway.ini ]]; then
  grep -v -i "password" /opt/YSFGateway/YSFGateway.ini \
    > "$BACKUP_DIR/YSFGateway.ini.$TIMESTAMP" 2>/dev/null || \
  cp /opt/YSFGateway/YSFGateway.ini "$BACKUP_DIR/YSFGateway.ini.$TIMESTAMP"
  echo "  YSFGateway.ini"
fi

# P25Gateway (if exists)
if [[ -f /opt/P25Gateway/P25Gateway.ini ]]; then
  grep -v -i "password" /opt/P25Gateway/P25Gateway.ini \
    > "$BACKUP_DIR/P25Gateway.ini.$TIMESTAMP" 2>/dev/null || \
  cp /opt/P25Gateway/P25Gateway.ini "$BACKUP_DIR/P25Gateway.ini.$TIMESTAMP"
  echo "  P25Gateway.ini"
fi

# NXDNGateway (if exists)
if [[ -f /opt/NXDNGateway/NXDNGateway.ini ]]; then
  grep -v -i "password" /opt/NXDNGateway/NXDNGateway.ini \
    > "$BACKUP_DIR/NXDNGateway.ini.$TIMESTAMP" 2>/dev/null || \
  cp /opt/NXDNGateway/NXDNGateway.ini "$BACKUP_DIR/NXDNGateway.ini.$TIMESTAMP"
  echo "  NXDNGateway.ini"
fi

# Keep only the last 10 backups of each file (prevent disk bloat)
for base in MMDVM_Bridge DVSwitch Analog_Bridge DMRGateway YSFGateway P25Gateway NXDNGateway; do
  ls -t "$BACKUP_DIR/$base.ini."* 2>/dev/null | tail -n +11 | xargs -r rm -f
done

cd "$REPO"
git add allstar-dmr/node-configs/backups/ 2>/dev/null || true

echo ""
echo "Backup complete: $BACKUP_DIR/*.$TIMESTAMP"
echo ""
echo "To push to GitHub, either:"
echo "  1. Ask Muse to push via API (preferred), or"
echo "  2. Configure a GitHub token on the node and run: git push"
echo ""
echo "To restore from backup (CAUTION):"
echo "  1. Copy the desired backup file to /tmp/"
echo "  2. Manually merge (do NOT blindly overwrite - check diffs first)"
echo "  3. NEVER auto-restore Analog_Bridge.ini - it contains node-specific tuning"

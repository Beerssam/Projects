#!/usr/bin/env bash
# restore-node.sh -- Guided restore of node configs from a backup set
#
# Companion to backup-node-configs.sh (v2) and RESTORE.md.
# Restores a timestamped backup set (from allstar-dmr/node-configs/backups/)
# onto a freshly built node: fresh ASL3 -> DVSwitch installed -> this script.
#
# Safety rules (same as always on this node):
#   * Diffs are shown (summary) BEFORE anything is written.
#   * Every live file it overwrites is first copied to a pre-restore
#     safety dir; the script prints that path.
#   * Analog_Bridge.ini is NEVER auto-restored (node-specific tuning) --
#     it is reported for manual diffing only.
#   * Secret values in the backups are __REDACTED__; after restoring, the
#     script lists every file/key that still needs a real value.
#
# Usage:
#   sudo bash restore-node.sh <TIMESTAMP> [--dry-run] [--yes]
#   sudo bash restore-node.sh latest [--dry-run]
# TIMESTAMP is the set suffix, e.g. 20261023-080002
# Test hooks: NODE_ROOT=/tmp/fake  REPO_DIR=/tmp/repo

set -u
ROOT="${NODE_ROOT:-}"
REPO="${REPO_DIR:-/home/ASL3/Projects}"
BACKUP_DIR="$REPO/allstar-dmr/node-configs/backups"

TS="${1:-}"
DRY=0; YES=0
for a in "$@"; do
  [[ "$a" == "--dry-run" ]] && DRY=1
  [[ "$a" == "--yes" ]] && YES=1
done

if [[ -z "$TS" ]]; then
  echo "Usage: restore-node.sh <TIMESTAMP|latest> [--dry-run] [--yes]"
  echo "Available sets:"
  ls "$BACKUP_DIR" | grep -oE "allstar\.[0-9]{8}-[0-9]{6}" | sed 's/allstar\.//' | sort -u | tail -5
  exit 1
fi
if [[ "$TS" == "latest" ]]; then
  TS=$(ls "$BACKUP_DIR" | grep -oE "allstar\.[0-9]{8}-[0-9]{6}" | sed 's/allstar\.//' | sort -u | tail -1)
  echo "Latest backup set: $TS"
fi

SET="$BACKUP_DIR/allstar.$TS"
if [[ ! -d "$SET" ]]; then
  echo "ERROR: backup set not found: $SET"
  exit 1
fi
SAFETY="$ROOT/root/pre-restore-$(date +%Y%m%d-%H%M%S)"
CHANGED=0; SKIPPED=0

# restore_file SRC DST -- diff, safety-copy, install one file.
restore_file() {
  local src="$1" dst="$2"
  [[ -f "$src" ]] || return 0
  if [[ -f "$dst" ]] && cmp -s "$src" "$dst"; then
    return 0  # already identical
  fi
  CHANGED=$((CHANGED+1))
  if [[ -f "$dst" ]]; then
    echo "  UPDATE  ${dst#$ROOT}  ($(diff "$dst" "$src" 2>/dev/null | grep -c '^[<>]') lines differ)"
  else
    echo "  NEW     ${dst#$ROOT}"
  fi
  [[ $DRY -eq 1 ]] && return 0
  mkdir -p "$(dirname "$dst")"
  if [[ -f "$dst" ]]; then
    mkdir -p "$SAFETY$(dirname "${dst#$ROOT}")"
    cp "$dst" "$SAFETY${dst#$ROOT}"
  fi
  cp "$src" "$dst"
}

# restore_tree SRCDIR DSTDIR -- restore_file every file in a tree.
# (process substitution, not a pipe: restore_file's counters must survive)
restore_tree() {
  local src="$1" dst="$2" rel
  [[ -d "$src" ]] || return 0
  while IFS= read -r rel; do
    rel="${rel#./}"
    restore_file "$src/$rel" "$dst/$rel"
  done < <(cd "$src" && find . -type f)
}

echo "=== Restore plan: backup set $TS ==="
[[ $DRY -eq 1 ]] && echo "(DRY RUN -- nothing will be written)"

# Preconditions (warnings, not stops -- except a missing DVSwitch tree)
if [[ ! -d "$ROOT/opt/MMDVM_Bridge" ]]; then
  echo "WARNING: /opt/MMDVM_Bridge does not exist -- install DVSwitch first (RESTORE.md step 3)."
fi
if [[ ! -d "$ROOT/usr/local/bin/SkywarnPlus" ]]; then
  echo "NOTE: SkywarnPlus code not installed yet -- its config will be listed as pending."
fi

if [[ $DRY -eq 0 && $YES -eq 0 ]]; then
  read -r -p "Restore this set onto this node? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "Aborted -- nothing written."; exit 0; }
fi

# --- Bridge / gateway inis ---
INI_DST_MMDVM="$ROOT/opt/MMDVM_Bridge/MMDVM_Bridge.ini"
INI_DST_DVS="$ROOT/opt/MMDVM_Bridge/DVSwitch.ini"
INI_DST_DMRG="$ROOT/opt/DMRGateway/DMRGateway.ini"
INI_DST_YSFG="$ROOT/opt/YSFGateway/YSFGateway.ini"
INI_DST_P25G="$ROOT/opt/P25Gateway/P25Gateway.ini"
INI_DST_NXDNG="$ROOT/opt/NXDNGateway/NXDNGateway.ini"
restore_file "$BACKUP_DIR/MMDVM_Bridge.ini.$TS" "$INI_DST_MMDVM"
restore_file "$BACKUP_DIR/DVSwitch.ini.$TS" "$INI_DST_DVS"
restore_file "$BACKUP_DIR/DMRGateway.ini.$TS" "$INI_DST_DMRG"
restore_file "$BACKUP_DIR/YSFGateway.ini.$TS" "$INI_DST_YSFG"
restore_file "$BACKUP_DIR/P25Gateway.ini.$TS" "$INI_DST_P25G"
restore_file "$BACKUP_DIR/NXDNGateway.ini.$TS" "$INI_DST_NXDNG"
if [[ -f "$BACKUP_DIR/Analog_Bridge.ini.$TS" ]]; then
  echo "  MANUAL  /opt/Analog_Bridge/Analog_Bridge.ini -- never auto-restored."
  echo "          Diff by hand:  diff /opt/Analog_Bridge/Analog_Bridge.ini $BACKUP_DIR/Analog_Bridge.ini.$TS"
  SKIPPED=$((SKIPPED+1))
fi

# --- Config trees ---
restore_tree "$SET/etc-asterisk" "$ROOT/etc/asterisk"
restore_tree "$SET/etc-allstar" "$ROOT/etc/allstar"
restore_file "$SET/etc-ircddbgateway" "$ROOT/etc/ircddbgateway"
restore_tree "$SET/etc-allmon3" "$ROOT/etc/allmon3"
restore_tree "$SET/www-supermon" "$ROOT/var/www/html/supermon"
restore_tree "$SET/www-allscan" "$ROOT/var/www/html/allscan"
restore_tree "$SET/www-AUTOSKY" "$ROOT/var/www/html/AUTOSKY"
restore_file "$SET/dvswitch-control.html" "$ROOT/var/www/html/dvswitch-control.html"
restore_file "$SET/dvswitch-control.sh" "$ROOT/var/www/cgi-bin/dvswitch-control.sh"
restore_file "$SET/var-lib-mmdvm/YSFHosts.txt" "$ROOT/var/lib/mmdvm/YSFHosts.txt"
restore_tree "$SET/systemd" "$ROOT/etc/systemd/system"
if [[ -d "$SET/skywarnplus" ]]; then
  if [[ -d "$ROOT/usr/local/bin/SkywarnPlus" ]]; then
    restore_tree "$SET/skywarnplus" "$ROOT/usr/local/bin/SkywarnPlus"
  else
    echo "  PENDING SkywarnPlus config (install SkywarnPlus code first, then re-run)"
    SKIPPED=$((SKIPPED+1))
  fi
fi
restore_tree "$SET/autosky-bin" "$ROOT/usr/local/bin"

# Web trees must be writable by Apache (astdb, caches)
if [[ $DRY -eq 0 && -z "$ROOT" ]]; then
  chown -R www-data:www-data /var/www/html/supermon /var/www/html/allscan /var/www/html/AUTOSKY 2>/dev/null || true
  systemctl daemon-reload 2>/dev/null || true
fi

# Crontabs (real node only; shown in dry-run)
for u in ASL3 root; do
  cf="$SET/manifests/crontab-$u.txt"
  [[ -s "$cf" ]] || continue
  if [[ $DRY -eq 1 || -n "$ROOT" ]]; then
    echo "  CRON    $u: $(grep -cvE '^\s*(#|$)' "$cf") active entries in backup (not loaded in this mode)"
  else
    crontab -u "$u" "$cf" && echo "  CRON    $u: crontab restored"
  fi
done

echo ""
echo "=== Summary: $CHANGED file(s) $( [[ $DRY -eq 1 ]] && echo 'would change' || echo 'changed' ), $SKIPPED manual/pending ==="
[[ $DRY -eq 0 && -d "$SAFETY" ]] && echo "Pre-restore copies of overwritten files: $SAFETY"

# --- Secrets still to fill ---
echo ""
echo "=== Secrets to re-enter (backups are redacted by design) ==="
grep -rl "__REDACTED__" "$BACKUP_DIR"/*".$TS" "$SET" 2>/dev/null | while read -r f; do
  echo "  ${f#$BACKUP_DIR/}:"
  grep -n "__REDACTED__" "$f" 2>/dev/null | head -4 | sed 's/^/      /'
done
echo "Known big ones: BrandMeister + TGIF passwords (DMRGateway.ini), the"
echo "AllStar node password / IAX secret (rpt.conf, iax.conf), Asterisk"
echo "manager password (manager.conf -- Supermon + Allmon3 use it too),"
echo "Allmon3 web login (reset via its users file), any SkywarnPlus API key."

echo ""
echo "=== Next steps (in order) ==="
echo "  1. Fill the secrets above."
echo "  2. cd $REPO && sudo bash allstar-dmr/scripts/build-dmrgateway.sh   (if /usr/local/bin/DMRGateway is missing)"
echo "  3. sudo bash allstar-dmr/dashboard/install.sh"
echo "  4. sudo bash allstar-dmr/node-configs/fix-ysf-parrot-host.sh"
echo "  5. Restart services and run the acceptance checklist in RESTORE.md"
echo "     (dashboard, DMR parrot, YSF parrot, NXDN, D-STAR, Supermon, Allmon3,"
echo "      SkywarnPlus test, Tailscale re-join if used)."

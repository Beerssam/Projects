#!/usr/bin/env bash
# backup-node-configs.sh -- Backup node configs to the Beerssam/Projects repo
#
# v2 (Oct 23 2026): wider capture for disaster recovery -- adds the D-STAR
# gateway config, Allmon3, Supermon, AllScan, AutoSky, SkywarnPlus configs,
# and system manifests (packages, enabled services, crontabs, Tailscale
# status). Restore with restore-node.sh; full procedure in RESTORE.md.
#
# Redaction: secret VALUES are replaced with __REDACTED__ (the key stays
# visible so a restore knows what to fill in). Nothing with a live password,
# API key, token, or password hash is ever written to the repo.
#
# Usage: sudo bash backup-node-configs.sh
# Test hooks (used by Muse to fixture-test off-node):
#   NODE_ROOT=/tmp/fake  prefix every node path with /tmp/fake
#   REPO_DIR=/tmp/repo   use a different repo checkout

set -e
ROOT="${NODE_ROOT:-}"
REPO="${REPO_DIR:-/home/ASL3/Projects}"
BACKUP_DIR="$REPO/allstar-dmr/node-configs/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

# redact_copy SRC DST -- copy a text file, replacing secret values.
redact_copy() {
  local src="$1" dst="$2"
  [[ -f "$src" ]] || return 0
  mkdir -p "$(dirname "$dst")"
  case "$src" in
    */users|*/.htpasswd)  # credential stores: name:hash or name|hash --
      # keep names, drop hashes (Allmon3 users uses '|', htpasswd uses ':')
      sed -E 's/^([^:|]+)[:|].*/\1:__REDACTED__/' "$src" > "$dst" ;;
    *.php|*.inc)  # php config: blank quoted values on sensitive lines
      sed -E '/(password|passwd|passphrase|secret|api[-_]?key|user[-_]?key|token|dbpass)/I s/(["'"'"'])[^"'"'"']*(["'"'"'])/\1__REDACTED__\2/g' "$src" > "$dst" ;;
    *)  # ini/conf/yaml: value after = or : on sensitive lines.
        # Keyword match, plus a boundary rule for bare "pass" (dbpass,
        # scan-pass) that deliberately does NOT touch keys like PassAllPC,
        # plus start-of-line bare keys (pass=, UserKey:) that the boundary
        # rule misses -- all three misses leaked in the Oct 23 v2 snapshot.
      sed -E \
        -e 's/^([[:space:]]*(pass|passwd|password|passphrase|secret|key|userkey|apikey)[[:space:]]*=).*/\1__REDACTED__/I' \
        -e 's/^([[:space:]]*(pass|passwd|password|passphrase|secret|key|userkey|apikey)[[:space:]]*:[[:space:]]+).*/\1__REDACTED__/I' \
        -e 's/^([[:space:]]*[^=]*(password|passwd|passphrase|secret|api[-_]?key|user[-_]?key|auth[-_]?key|token|dbpass)[^=]*=[[:space:]]*).*/\1__REDACTED__/I' \
        -e 's/^([[:space:]]*[^=]*([^a-zA-Z]pass|dbpass)[^=]*=[[:space:]]*).*/\1__REDACTED__/I' \
        -e 's/^([[:space:]]*[^:]*(password|passwd|passphrase|secret|api[-_]?key|user[-_]?key|auth[-_]?key|token|dbpass)[^:]*:[[:space:]]+).*/\1__REDACTED__/I' \
        -e 's/^([[:space:]]*[^:]*([^a-zA-Z]pass|dbpass)[^:]*:[[:space:]]+).*/\1__REDACTED__/I' \
        "$src" > "$dst" ;;
  esac
}

# redact_tree SRCDIR DSTDIR [exclude-glob...] -- copy a whole tree,
# redacting text config files and copying everything else verbatim
# (running sed over images would corrupt them).
redact_tree() {
  local src="$1" dst="$2"; shift 2
  [[ -d "$src" ]] || return 0
  mkdir -p "$dst"
  ( cd "$src" && find . -type f ) | while read -r rel; do
    local skip=0 pat
    for pat in "$@"; do case "$rel" in $pat) skip=1 ;; esac; done
    [[ $skip -eq 1 ]] && continue
    case "$rel" in
      *.ini|*.conf|*.cfg|*.inc|*.php|*.yaml|*.yml|*/users|*/.htpasswd)
        redact_copy "$src/$rel" "$dst/$rel" ;;
      *)
        mkdir -p "$dst/$(dirname "$rel")"
        cp "$src/$rel" "$dst/$rel" ;;
    esac
  done
}

echo "Backing up configs (secrets redacted)..."

# --- DVSwitch / bridge / gateway inis (flat, timestamped, as in v1) ---
declare -A INIS=(
  [MMDVM_Bridge]="$ROOT/opt/MMDVM_Bridge/MMDVM_Bridge.ini"
  [DVSwitch]="$ROOT/opt/MMDVM_Bridge/DVSwitch.ini"
  [Analog_Bridge]="$ROOT/opt/Analog_Bridge/Analog_Bridge.ini"
  [DMRGateway]="$ROOT/opt/DMRGateway/DMRGateway.ini"
  [YSFGateway]="$ROOT/opt/YSFGateway/YSFGateway.ini"
  [P25Gateway]="$ROOT/opt/P25Gateway/P25Gateway.ini"
  [NXDNGateway]="$ROOT/opt/NXDNGateway/NXDNGateway.ini"
)
for base in "${!INIS[@]}"; do
  if [[ -f "${INIS[$base]}" ]]; then
    redact_copy "${INIS[$base]}" "$BACKUP_DIR/$base.ini.$TIMESTAMP"
    note=""
    [[ "$base" == "Analog_Bridge" ]] && note=" (REFERENCE ONLY - never auto-restore)"
    echo "  $base.ini$note"
  fi
done
for base in "${!INIS[@]}"; do
  ls -t "$BACKUP_DIR/$base.ini."* 2>/dev/null | tail -n +11 | xargs -r rm -f
done

# --- Full node tree backup (v1 AllStar set + v2 additions) ---
echo ""
echo "Backing up node config tree..."
AST_BACKUP_DIR="$BACKUP_DIR/allstar.$TIMESTAMP"
mkdir -p "$AST_BACKUP_DIR"

# /etc/asterisk (AllStarLink configs: rpt.conf, extensions.conf, etc.)
if [[ -d "$ROOT/etc/asterisk" ]]; then
  mkdir -p "$AST_BACKUP_DIR/etc-asterisk"
  for f in "$ROOT"/etc/asterisk/*.conf; do
    [[ -f "$f" ]] || continue
    redact_copy "$f" "$AST_BACKUP_DIR/etc-asterisk/$(basename "$f")"
  done
  echo "  /etc/asterisk/*.conf (secrets redacted)"
fi

# /etc/allstar (if separate)
if [[ -d "$ROOT/etc/allstar" ]]; then
  redact_tree "$ROOT/etc/allstar" "$AST_BACKUP_DIR/etc-allstar"
  echo "  /etc/allstar/"
fi

# D-STAR gateway config (single file)
if [[ -f "$ROOT/etc/ircddbgateway" ]]; then
  redact_copy "$ROOT/etc/ircddbgateway" "$AST_BACKUP_DIR/etc-ircddbgateway"
  echo "  /etc/ircddbgateway (D-STAR gateway)"
fi

# Allmon3 config
if [[ -d "$ROOT/etc/allmon3" ]]; then
  redact_tree "$ROOT/etc/allmon3" "$AST_BACKUP_DIR/etc-allmon3" "*.dpkg-dist" "*~"
  echo "  /etc/allmon3/ (Allmon3)"
fi

# Web apps (config-bearing trees under the web root)
for app in supermon allscan AUTOSKY; do
  if [[ -d "$ROOT/var/www/html/$app" ]]; then
    redact_tree "$ROOT/var/www/html/$app" "$AST_BACKUP_DIR/www-$app" \
      "./astdb.txt" "*.bak" "*.sample" "*.wav" "*.mp3"
    echo "  /var/www/html/$app/"
  fi
done

# SkywarnPlus config (the severe-weather alerter; code itself reinstalls)
if [[ -d "$ROOT/usr/local/bin/SkywarnPlus" ]]; then
  mkdir -p "$AST_BACKUP_DIR/skywarnplus"
  for f in "$ROOT"/usr/local/bin/SkywarnPlus/*.yaml "$ROOT"/usr/local/bin/SkywarnPlus/*.yml \
           "$ROOT"/usr/local/bin/SkywarnPlus/*.ini "$ROOT"/usr/local/bin/SkywarnPlus/*.conf; do
    [[ -f "$f" ]] || continue
    redact_copy "$f" "$AST_BACKUP_DIR/skywarnplus/$(basename "$f")"
  done
  echo "  SkywarnPlus config"
fi
# AutoSky helper scripts in /usr/local/bin, if present
for f in "$ROOT"/usr/local/bin/[Aa]uto[Ss]ky*; do
  [[ -f "$f" ]] || continue
  mkdir -p "$AST_BACKUP_DIR/autosky-bin"
  redact_copy "$f" "$AST_BACKUP_DIR/autosky-bin/$(basename "$f")"
  echo "  $(basename "$f") (AutoSky helper)"
done

# DVSwitch dashboard (our custom control panel)
if [[ -f "$ROOT/var/www/html/dvswitch-control.html" ]]; then
  cp "$ROOT/var/www/html/dvswitch-control.html" "$AST_BACKUP_DIR/" 2>/dev/null || true
  echo "  dvswitch-control.html (dashboard)"
fi
if [[ -f "$ROOT/var/www/cgi-bin/dvswitch-control.sh" ]]; then
  cp "$ROOT/var/www/cgi-bin/dvswitch-control.sh" "$AST_BACKUP_DIR/" 2>/dev/null || true
  echo "  dvswitch-control.sh (CGI)"
fi

# YSF hosts file (carries the local-parrot fix state)
if [[ -f "$ROOT/var/lib/mmdvm/YSFHosts.txt" ]]; then
  mkdir -p "$AST_BACKUP_DIR/var-lib-mmdvm"
  cp "$ROOT/var/lib/mmdvm/YSFHosts.txt" "$AST_BACKUP_DIR/var-lib-mmdvm/YSFHosts.txt"
  echo "  /var/lib/mmdvm/YSFHosts.txt"
fi

# Systemd overrides (ALL of them, not just the bridge)
if [[ -d "$ROOT/etc/systemd/system" ]]; then
  mkdir -p "$AST_BACKUP_DIR/systemd"
  cp -r "$ROOT"/etc/systemd/system/*.d "$AST_BACKUP_DIR/systemd/" 2>/dev/null || true
  echo "  systemd overrides"
fi

# --- System manifests (the rebuild shopping list) ---
echo ""
echo "Writing system manifests..."
MAN="$AST_BACKUP_DIR/manifests"
mkdir -p "$MAN/cron.d"
if [[ -z "$ROOT" ]]; then
  dpkg-query -W -f='${Package} ${Version}\n' 2>/dev/null | sort > "$MAN/packages.txt" || true
  systemctl list-unit-files --state=enabled --no-legend 2>/dev/null > "$MAN/services-enabled.txt" || true
  for u in ASL3 root; do
    crontab -l -u "$u" > "$MAN/crontab-$u.txt" 2>/dev/null || true
  done
  { tailscale status 2>/dev/null; tailscale ip 2>/dev/null; } > "$MAN/tailscale.txt" || true
fi
[[ -f "$ROOT/etc/crontab" ]] && cp "$ROOT/etc/crontab" "$MAN/etc-crontab"
if [[ -d "$ROOT/etc/cron.d" ]]; then
  for f in "$ROOT"/etc/cron.d/*; do
    [[ -f "$f" ]] && redact_copy "$f" "$MAN/cron.d/$(basename "$f")"
  done
fi
[[ -f "$ROOT/etc/os-release" ]] && cp "$ROOT/etc/os-release" "$MAN/os-release.txt"
uname -a > "$MAN/uname.txt" 2>/dev/null || true
echo "  packages, enabled services, crontabs, OS (in manifests/)"

# Keep only last 5 full tree backups (they're larger)
ls -dt "$BACKUP_DIR"/allstar.* 2>/dev/null | tail -n +6 | xargs -r rm -rf

# --- Commit (and keep the repo usable by the ASL3 user afterwards) ---
cd "$REPO"
if git rev-parse --git-dir >/dev/null 2>&1; then
  git add allstar-dmr/node-configs/backups/ 2>/dev/null || true
  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "Node config backups $(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
    echo "  Committed backups to local git repo"
  fi
  # The script runs as root; hand the repo back to its owner so the ASL3
  # user's own git commands keep working (Oct 23 2026 ownership lesson).
  owner="$(stat -c %U "$REPO")"
  if [[ "$(id -u)" == "0" && -n "$owner" && "$owner" != "root" ]]; then
    chown -R "$owner": "$REPO/.git" "$BACKUP_DIR" 2>/dev/null || true
  fi
fi

echo ""
echo "Backup complete: $BACKUP_DIR/*.$TIMESTAMP + allstar.$TIMESTAMP/"
echo ""
echo "To push to GitHub:  cd $REPO && git push   (as the repo owner)"
echo ""
echo "To restore from backup (CAUTION):"
echo "  Follow RESTORE.md and use restore-node.sh -- it diffs before it writes"
echo "  and NEVER auto-restores Analog_Bridge.ini (node-specific tuning)."

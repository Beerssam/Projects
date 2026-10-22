#!/usr/bin/env bash
# install.sh -- install the KF0RIZ digital control panel on the AllStar node.
#
# Run with sudo on the node, from the repo directory:
#   sudo bash allstar-dmr/dashboard/install.sh
#
# What it does:
#   1. Backs up any existing control page / CGI / helpers.
#   2. Copies dvswitch-control.html to the Apache web root.
#   3. Copies dvswitch-control.sh, mode-switch.sh and gain-set.sh to the
#      CGI bin and makes them executable.
#   4. Ensures Apache CGI is enabled and reloads Apache.
#   5. Adds a sudoers rule so the CGI can run dvswitch.sh (tune/mode) and
#      the mode-switch / gain-set helpers without a password.
#
# The panel is then at: http://<node-ip>/dvswitch-control.html
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTML_SRC="$SCRIPT_DIR/dvswitch-control.html"
CGI_SRC="$SCRIPT_DIR/dvswitch-control.sh"
HELPER_SRC="$SCRIPT_DIR/mode-switch.sh"
GAIN_SRC="$SCRIPT_DIR/gain-set.sh"

[[ -f "$HTML_SRC" ]] || { echo "Missing: $HTML_SRC" >&2; exit 1; }
[[ -f "$CGI_SRC" ]] || { echo "Missing: $CGI_SRC" >&2; exit 1; }
[[ -f "$HELPER_SRC" ]] || { echo "Missing: $HELPER_SRC" >&2; exit 1; }
[[ -f "$GAIN_SRC" ]] || { echo "Missing: $GAIN_SRC" >&2; exit 1; }

# Find Apache web root. The CGI dir is ALWAYS /var/www/cgi-bin because that is
# what the Apache conf below (ScriptAlias /cgi-bin/ /var/www/cgi-bin/) serves.
# (An earlier version preferred /usr/lib/cgi-bin when it existed, which caused
# a 404 on the status/tune endpoints. Always match the conf.)
WEB_ROOT=""
CGI_DIR="/var/www/cgi-bin"
for d in /var/www/html /var/www /usr/share/apache2/default-site; do
  if [[ -d "$d" ]]; then WEB_ROOT="$d"; break; fi
done
mkdir -p "$CGI_DIR"
if [[ -z "$WEB_ROOT" ]]; then
  echo "Could not find Apache web root." >&2; exit 1;
fi

echo "== Web root: $WEB_ROOT"
echo "== CGI dir:  $CGI_DIR"

# Backup existing
TS=$(date +%Y%m%d-%H%M%S)
if [[ -f "$WEB_ROOT/dvswitch-control.html" ]]; then
  cp "$WEB_ROOT/dvswitch-control.html" "$WEB_ROOT/dvswitch-control.html.bak.$TS"
  echo "== Backed up existing HTML"
fi
if [[ -f "$CGI_DIR/dvswitch-control.sh" ]]; then
  cp "$CGI_DIR/dvswitch-control.sh" "$CGI_DIR/dvswitch-control.sh.bak.$TS"
  echo "== Backed up existing CGI"
fi
if [[ -f "$CGI_DIR/mode-switch.sh" ]]; then
  cp "$CGI_DIR/mode-switch.sh" "$CGI_DIR/mode-switch.sh.bak.$TS"
  echo "== Backed up existing mode-switch helper"
fi
if [[ -f "$CGI_DIR/gain-set.sh" ]]; then
  cp "$CGI_DIR/gain-set.sh" "$CGI_DIR/gain-set.sh.bak.$TS"
  echo "== Backed up existing gain-set helper"
fi

# Install
cp "$HTML_SRC" "$WEB_ROOT/dvswitch-control.html"
cp "$CGI_SRC" "$CGI_DIR/dvswitch-control.sh"
cp "$HELPER_SRC" "$CGI_DIR/mode-switch.sh"
cp "$GAIN_SRC" "$CGI_DIR/gain-set.sh"
chmod 755 "$CGI_DIR/dvswitch-control.sh" "$CGI_DIR/mode-switch.sh" "$CGI_DIR/gain-set.sh"
# Remove stale copies from the old (wrong) location if they exist there, so a
# future reader doesn't mistake them for the live ones.
for stale in dvswitch-control.sh mode-switch.sh gain-set.sh; do
  if [[ -f /usr/lib/cgi-bin/$stale && "$CGI_DIR" != "/usr/lib/cgi-bin" ]]; then
    rm -f "/usr/lib/cgi-bin/$stale"
    echo "== Removed stale $stale from /usr/lib/cgi-bin"
  fi
done
echo "== Installed HTML, CGI, mode-switch and gain-set helpers"

# Apache CGI config (if not already present)
if ! grep -q "dvswitch-control" /etc/apache2/conf-enabled/*.conf 2>/dev/null; then
  cat > /etc/apache2/conf-available/dvswitch-control.conf <<'EOF'
ScriptAlias /cgi-bin/ /var/www/cgi-bin/
<Directory "/var/www/cgi-bin">
  AllowOverride None
  Options +ExecCGI -MultiViews +SymLinksIfOwnerMatch
  Require all granted
</Directory>
EOF
  a2enconf dvswitch-control >/dev/null 2>&1 || true
  echo "== Added Apache CGI config"
fi

# Sudoers: let www-data run dvswitch.sh tune/mode and the mode-switch helper
# without password. Rewritten on every install so reinstalls pick up the
# helper even if the rule predates it.
SUDOERS_FILE="/etc/sudoers.d/dvswitch-control"
DVS=$(find /opt /usr/local -name "dvswitch.sh" 2>/dev/null | head -1)
if [[ -n "$DVS" ]]; then
  printf 'www-data ALL=(ALL) NOPASSWD: %s tune *, %s mode *, %s/mode-switch.sh *, %s/gain-set.sh *\n' \
    "$DVS" "$DVS" "$CGI_DIR" "$CGI_DIR" > "$SUDOERS_FILE"
  chmod 440 "$SUDOERS_FILE"
  echo "== Wrote sudoers rule for www-data -> dvswitch.sh + mode-switch.sh + gain-set.sh"
else
  echo "!! dvswitch.sh not found; sudoers rule skipped (tune/mode will fail)" >&2
fi

# Reload Apache
if systemctl is-active --quiet apache2; then
  systemctl reload apache2
  echo "== Apache reloaded"
else
  echo "!! Apache not running; start it with: sudo systemctl start apache2" >&2
fi

IP=$(hostname -I | awk '{print $1}')
echo
echo "Done. Open: http://$IP/dvswitch-control.html"

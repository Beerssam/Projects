#!/usr/bin/env bash
# install.sh -- install the KF0RIZ digital control panel on the AllStar node.
#
# Run with sudo on the node, from the repo directory:
#   sudo bash allstar-dmr/dashboard/install.sh
#
# What it does:
#   1. Backs up any existing control page / CGI.
#   2. Copies dvswitch-control.html to the Apache web root.
#   3. Copies dvswitch-control.sh to the CGI bin and makes it executable.
#   4. Ensures Apache CGI is enabled and reloads Apache.
#   5. Adds a sudoers rule so the CGI can run dvswitch.sh without a password.
#
# The panel is then at: http://<node-ip>/dvswitch-control.html
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HTML_SRC="$SCRIPT_DIR/dvswitch-control.html"
CGI_SRC="$SCRIPT_DIR/dvswitch-control.sh"

[[ -f "$HTML_SRC" ]] || { echo "Missing: $HTML_SRC" >&2; exit 1; }
[[ -f "$CGI_SRC" ]] || { echo "Missing: $CGI_SRC" >&2; exit 1; }

# Find Apache web root and CGI dir
WEB_ROOT=""
CGI_DIR=""
for d in /var/www/html /var/www /usr/share/apache2/default-site; do
  if [[ -d "$d" ]]; then WEB_ROOT="$d"; break; fi
done
for d in /var/www/cgi-bin /usr/lib/cgi-bin; do
  if [[ -d "$d" ]]; then CGI_DIR="$d"; break; fi
done
# Fall back to creating /var/www/cgi-bin
if [[ -z "$CGI_DIR" ]]; then
  CGI_DIR="/var/www/cgi-bin"
  mkdir -p "$CGI_DIR"
fi
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

# Install
cp "$HTML_SRC" "$WEB_ROOT/dvswitch-control.html"
cp "$CGI_SRC" "$CGI_DIR/dvswitch-control.sh"
chmod 755 "$CGI_DIR/dvswitch-control.sh"
echo "== Installed HTML and CGI"

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

# Sudoers: let www-data run dvswitch.sh tune/mode without password
SUDOERS_FILE="/etc/sudoers.d/dvswitch-control"
if [[ ! -f "$SUDOERS_FILE" ]]; then
  DVS=$(find /opt /usr/local -name "dvswitch.sh" 2>/dev/null | head -1)
  if [[ -n "$DVS" ]]; then
    printf 'www-data ALL=(ALL) NOPASSWD: %s tune *, %s mode *\n' "$DVS" "$DVS" > "$SUDOERS_FILE"
    chmod 440 "$SUDOERS_FILE"
    echo "== Added sudoers rule for www-data -> $DVS"
  else
    echo "!! dvswitch.sh not found; sudoers rule skipped (tune/mode will fail)" >&2
  fi
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

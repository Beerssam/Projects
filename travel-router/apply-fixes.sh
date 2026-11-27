#!/bin/sh
# apply-fixes.sh -- GL.iNet GL-MT3000 (Beryl AX) travel router
#
# Re-applies the router-side state that a firmware update or factory
# reset can wipe, for the beerswifi.duckdns.org setup:
#   1. oui-httpd allowed_host entry  (panel access by name)
#   2. AdGuard Home UCI toggles      (enabled / dns / vpn tunnels)
#   3. Pi5 SSH public key in dropbear authorized_keys (cert delivery)
#
# Idempotent: checks before changing, backs up before touching,
# verifies by read-back at the end. Run as root ON the router:
#   sh apply-fixes.sh
#
# NOT covered here:
#   - The TLS cert/key themselves. The Pi5 delivers those; if they were
#     wiped, re-run the deploy from the Pi5 (see README.md).
#   - The router's ZeroTier identity. If that is lost the router gets a
#     new ZeroTier address and the DNS record must be re-pointed --
#     a bigger rebuild than this script.

DATE=$(date +%Y%m%d-%H%M%S)

if [ "$(id -u)" != "0" ]; then
  echo "ERROR: run this as root on the router."
  exit 1
fi

# --- backups -------------------------------------------------------------
for f in /etc/config/oui-httpd /etc/config/adguardhome /etc/dropbear/authorized_keys; do
  if [ -f "$f" ]; then
    cp "$f" "$f.bak-$DATE" && echo "backup: $f.bak-$DATE"
  fi
done

# --- 1. panel-by-name host gate ------------------------------------------
# GL's nginx Lua gate (oui-access.lua) 403s any Host not on this list,
# which leaves the panel app spinning at #/login when reached by name.
if uci get oui-httpd.main.allowed_host 2>/dev/null | tr ' ' '\n' | grep -qx 'beerswifi.duckdns.org'; then
  echo "allowed_host: beerswifi.duckdns.org already present -- ok"
else
  uci add_list oui-httpd.main.allowed_host=beerswifi.duckdns.org
  uci commit oui-httpd
  echo "allowed_host: ADDED beerswifi.duckdns.org"
fi

# --- 2. AdGuard Home toggles ----------------------------------------------
AGH_CHANGED=0
for kv in enabled=1 dns_enabled=1 override_vpn=1; do
  k=${kv%%=*}; v=${kv#*=}
  cur=$(uci get adguardhome.config.$k 2>/dev/null)
  if [ "$cur" != "$v" ]; then
    uci set adguardhome.config.$k=$v
    AGH_CHANGED=1
    echo "adguardhome.$k: was '$cur', set to $v"
  else
    echo "adguardhome.$k: already $v -- ok"
  fi
done
uci commit adguardhome
if [ "$AGH_CHANGED" = "1" ]; then
  echo "Restarting AdGuard Home (note: its init script also reloads the firewall)..."
  /etc/init.d/adguardhome restart
fi

# --- 3. Pi5 SSH key (rides the acme.sh cert deploy hook) -------------------
PI5_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOaM1ThJP2hmMrkPkuS1QgZtPJ6iGVv4IrYhHRdZ6bdp sbeers@PI5-TAKserver"
AK=/etc/dropbear/authorized_keys
mkdir -p /etc/dropbear
touch "$AK"
chmod 600 "$AK"
if grep -qF "$PI5_PUBKEY" "$AK"; then
  echo "authorized_keys: Pi5 key already present -- ok"
else
  echo "$PI5_PUBKEY" >> "$AK"
  echo "authorized_keys: ADDED Pi5 key"
fi

# --- verification ----------------------------------------------------------
echo "--- verify ---"
echo "allowed_host : $(uci get oui-httpd.main.allowed_host 2>/dev/null)"
echo "adguardhome  : $(uci show adguardhome 2>/dev/null | grep -E 'enabled|override' | tr '\n' ' ')"
echo "pi5 key      : $(grep -cF "$PI5_PUBKEY" "$AK") match(es) in $AK"
if ps w | grep '[A]dGuardHome' >/dev/null; then
  echo "adguard proc : running"
else
  echo "adguard proc : NOT RUNNING -- check the panel"
fi
echo "Done. If the cert files were also wiped, re-run the deploy from the Pi5:"
echo "  ~/.acme.sh/acme.sh --deploy -d beerswifi.duckdns.org --deploy-hook glrouter"

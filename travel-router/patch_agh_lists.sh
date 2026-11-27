#!/bin/sh
# patch_agh_lists.sh -- GL-MT3000 AdGuard Home blocklist upgrade
# Part of the travel-router recovery kit (Beerssam/Projects).
#
# Changes to /etc/AdGuardHome/config.yaml:
#   1. Enables the AdAway Default Blocklist (id 2 -- ships disabled)
#   2. Adds OISD Big         (id 3) https://big.oisd.nl/
#   3. Adds HaGeZi Multi PRO (id 4)
#      https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt
#
# Idempotent: safe to re-run; exits early if everything is applied.
# Backs up the config before editing and restores it automatically
# if the post-edit sanity check fails.
# Run as root ON the router:  sh patch_agh_lists.sh
#
# NOTE: AdGuard stops during the edit -- DNS through the router
# pauses for under a minute. Clients with a secondary DNS (Sam's
# phone: Control D) fall back automatically.

CFG=/etc/AdGuardHome/config.yaml
DATE=$(date +%Y%m%d-%H%M%S)
BAK=$CFG.bak-$DATE
TMP=/tmp/agh_config_new.yaml

if [ "$(id -u)" != "0" ]; then
  echo "ERROR: run as root on the router."
  exit 1
fi
if [ ! -f "$CFG" ]; then
  echo "ERROR: $CFG not found."
  exit 1
fi

# --- what is missing? (idempotency) --------------------------------------
ADD_OISD=1;   grep -q 'big.oisd.nl' "$CFG" && ADD_OISD=0
ADD_HAGEZI=1; grep -q 'hagezi' "$CFG" && ADD_HAGEZI=0
ADAWAY_LINE=$(awk '/adaway\.org/{print prev} {prev=$0}' "$CFG")
ADAWAY_OFF=0; case "$ADAWAY_LINE" in *'enabled: false'*) ADAWAY_OFF=1 ;; esac

if [ "$ADD_OISD" = "0" ] && [ "$ADD_HAGEZI" = "0" ] && [ "$ADAWAY_OFF" = "0" ]; then
  echo "All list upgrades already applied -- nothing to do."
  exit 0
fi
[ "$ADD_OISD" = "0" ]   && echo "OISD Big: already present"
[ "$ADD_HAGEZI" = "0" ] && echo "HaGeZi PRO: already present"
[ "$ADAWAY_OFF" = "0" ] && echo "AdAway: already enabled"

# --- backup + stop ---------------------------------------------------------
cp "$CFG" "$BAK" && echo "backup: $BAK"
echo "Stopping AdGuard Home..."
/etc/init.d/adguardhome stop
sleep 2

# --- edit ------------------------------------------------------------------
awk -v add_oisd=$ADD_OISD -v add_hagezi=$ADD_HAGEZI '
  NR==1 { prev=$0; next }
  {
    if ($0 ~ /adaway\.org/ && prev ~ /enabled: false/) {
      sub(/false/, "true", prev)
      print "AdAway: enabling (was disabled)" > "/dev/stderr"
    }
    if ($0 ~ /^whitelist_filters:/) {
      print prev
      if (add_oisd) {
        print "  - enabled: true"
        print "    url: https://big.oisd.nl/"
        print "    name: OISD Big"
        print "    id: 3"
      }
      if (add_hagezi) {
        print "  - enabled: true"
        print "    url: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt"
        print "    name: HaGeZi Multi PRO"
        print "    id: 4"
      }
      prev=$0; next
    }
    print prev; prev=$0
  }
  END { print prev }
' "$CFG" > "$TMP"

# --- sanity check ------------------------------------------------------------
OK=1
for u in AdGuardSDNSFilter adaway.org; do
  grep -q "$u" "$TMP" || { echo "SANITY FAIL: $u missing"; OK=0; }
done
[ "$ADD_OISD" = "1" ]   && { grep -q 'big.oisd.nl' "$TMP" || { echo "SANITY FAIL: OISD missing"; OK=0; }; }
[ "$ADD_HAGEZI" = "1" ] && { grep -q 'hagezi' "$TMP"      || { echo "SANITY FAIL: HaGeZi missing"; OK=0; }; }
grep -q '^filters:' "$TMP"          || { echo "SANITY FAIL: filters section gone"; OK=0; }
grep -q '^whitelist_filters:' "$TMP" || { echo "SANITY FAIL: whitelist_filters gone"; OK=0; }

if [ "$OK" != "1" ]; then
  echo "Aborting -- restoring backup and restarting AdGuard."
  cp "$BAK" "$CFG"
  /etc/init.d/adguardhome start
  exit 1
fi

# --- apply + start -----------------------------------------------------------
cp "$TMP" "$CFG"
echo "Config updated. Starting AdGuard Home (firewall reload flood is normal)..."
/etc/init.d/adguardhome start
sleep 30

echo "--- filters on disk ---"
ls -la /etc/AdGuardHome/data/filters/
echo "--- filter log lines ---"
logread | grep -i 'filter' | tail -8
echo "--- AdGuard process ---"
ps w | grep '[A]dGuardHome' || echo "NOT RUNNING -- roll back: cp $BAK $CFG && /etc/init.d/adguardhome restart"
echo "--- memory ---"
free | head -2
echo "Done. Rollback if anything misbehaves:"
echo "  cp $BAK $CFG && /etc/init.d/adguardhome restart"

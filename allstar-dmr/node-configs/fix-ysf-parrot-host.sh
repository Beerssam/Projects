#!/usr/bin/env bash
# fix-ysf-parrot-host.sh -- point YSF talkgroup 99999 at the node's LOCAL
# YSFParrot instead of the public DE-Parrot server.
#
# Root cause (Oct 23 2026): /var/lib/mmdvm/YSFHosts.txt shipped with
#   99999;DE-Parrot;Parrot;207.180.235.10;42020;000;
# a community parrot server that no longer answers (Sam's gateway linked
# to it, forwarded his audio out, and no playback ever returned -- the
# logs show the connect and his TX, then silence). The node's own
# YSFParrot (ysfparrot.service, enabled, listening on 127.0.0.1:42012)
# sat idle the whole time. This script rewrites ONLY the address/port
# fields of the 99999 line to 127.0.0.1 / 42012.
#
# Safe to re-run: if a host-file update ever restores the public entry,
# run this again. It backs up first, changes nothing if the entry is
# already local, and stops with a clear message if the file doesn't look
# as expected.
#
# Usage: sudo bash fix-ysf-parrot-host.sh
# Env override (testing): YSF_HOSTS_FILE

set -u
HOSTS="${YSF_HOSTS_FILE:-/var/lib/mmdvm/YSFHosts.txt}"

if [[ ! -f "$HOSTS" ]]; then
  echo "ERROR: $HOSTS not found -- nothing changed." >&2
  exit 1
fi

line=$(grep '^99999;' "$HOSTS" | head -1)
if [[ -z "$line" ]]; then
  echo "ERROR: no 99999 entry in $HOSTS -- nothing changed." >&2
  exit 1
fi
echo "Current 99999 entry: $line"

if [[ "$line" == *"127.0.0.1;42012"* ]]; then
  echo "Already pointing at the local parrot -- nothing to do."
  exit 0
fi

bak="$HOSTS.bak.parrot-$(date +%Y%m%d-%H%M%S)"
cp "$HOSTS" "$bak" || { echo "ERROR: backup to $bak failed -- nothing changed." >&2; exit 1; }
echo "Backup taken: $bak"

# Rewrite fields 4 (address) and 5 (port) on the 99999 line only; every
# other line passes through byte-identical.
tmp=$(mktemp) || exit 1
awk -F';' 'BEGIN { OFS=";" }
  $1 == "99999" { $4 = "127.0.0.1"; $5 = "42012" }
  { print }' "$HOSTS" > "$tmp" && cat "$tmp" > "$HOSTS"
rm -f "$tmp"

newline=$(grep '^99999;' "$HOSTS" | head -1)
echo "New 99999 entry:     $newline"
if [[ "$newline" != *"127.0.0.1;42012"* ]]; then
  echo "ERROR: edit did not take -- restoring backup." >&2
  cp "$bak" "$HOSTS"
  exit 1
fi

# Reload the gateway so it picks up the corrected entry now (it also
# reloads its hosts hourly, but there's no reason to wait).
if systemctl restart ysfgateway 2>/dev/null; then
  sleep 2
  echo "ysfgateway: $(systemctl is-active ysfgateway 2>/dev/null || echo unknown)"
else
  echo "NOTE: could not restart ysfgateway; the change takes effect at its next hourly hosts reload, or run: sudo systemctl restart ysfgateway"
fi

echo "Done. Retest: dashboard YSF mode -> tune 99999 -> key up ~5s -> unkey; your voice should play back."
echo "Rollback: sudo cp $bak $HOSTS && sudo systemctl restart ysfgateway"

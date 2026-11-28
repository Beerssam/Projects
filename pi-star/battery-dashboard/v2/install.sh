#!/bin/bash
# install.sh -- wire battery dashboard v2 into the system.
# Everything that matters lives in ~/UPS_HAT_E/ (survives WPSD updates);
# this script (re)creates the thin system wiring that an update can wipe:
#   /etc/cron.d/pi-star-battery   (v2 generator every 5 min + 04:15 backup)
# and retires the two v1 cron.d schedulers (backed up first, never deleted).
# Idempotent. Run as pi-star:  bash ~/UPS_HAT_E/install.sh
# Daily self-check mode:       bash ~/UPS_HAT_E/install.sh --check
#   --check only restores wiring that is missing; it changes nothing else.
set -u
HOME_DIR="/home/pi-star/UPS_HAT_E"
CRON_FILE="/etc/cron.d/pi-star-battery"
BACKUP_DIR="$HOME_DIR/wiring-backup"

write_cron() {
    sudo tee "$CRON_FILE" > /dev/null <<'CRON'
*/5 * * * * pi-star nice -n 19 /home/pi-star/UPS_HAT_E/generate_webpage_v2.sh > /tmp/battery_v2.log 2>&1
15 4 * * * pi-star /home/pi-star/run_backup.sh >> /home/pi-star/UPS_HAT_E/backup.log
CRON
    sudo chmod 644 "$CRON_FILE"
}

if [ "${1:-}" = "--check" ]; then
    [ -f "$CRON_FILE" ] || { write_cron; echo "$(date -Iseconds) restored missing $CRON_FILE" >> "$HOME_DIR/install.log"; }
    exit 0
fi

mkdir -p "$BACKUP_DIR"
STAMP=$(date +%Y%m%d-%H%M%S)
for f in /etc/cron.d/webpage-scheduler /etc/cron.d/pi-star-backup.save; do
    if [ -f "$f" ]; then
        sudo cp "$f" "$BACKUP_DIR/$(basename "$f").bak-$STAMP"
        sudo rm "$f"
        echo "retired $f (backup in $BACKUP_DIR)"
    fi
done
write_cron
echo "wrote $CRON_FILE"

# daily self-check in the user crontab (restores wiring after a WPSD update)
( crontab -l 2>/dev/null | grep -v 'install.sh --check' ; \
  echo "17 5 * * * $HOME_DIR/install.sh --check" ) | crontab -
echo "self-check crontab entry set"

# nginx site already serves /var/www/battery_data on :7777 -- unchanged.
"$HOME_DIR/generate_webpage_v2.sh"
echo "first v2 run done: /var/www/battery_data/index.html + battery.json"

#!/bin/bash
export PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin:/home/pi-star
LOG_FILE="/home/pi-star/UPS_HAT_E/logs/backup.log"

# Perform the critical pre-backup copies to ensure system configs are included
cp /home/pi-star/.config/rclone/rclone.conf /home/pi-star/UPS_HAT_E/system_config/ 2>/dev/null
cp /var/lib/zerotier-one/identity.public /home/pi-star/UPS_HAT_E/system_config/ 2>/dev/null

# Log the start
echo "Backup started at $(date)" >> $LOG_FILE

# Run rclone using the dynamic date-based folder path
/home/pi-star/rclone --config /home/pi-star/.config/rclone/rclone.conf \
copy /home/pi-star/UPS_HAT_E/ my-google-drive:Pi_Scripts_Backup/$(date +%Y-%m-%d)/ >> $LOG_FILE 2>&1

# Log the exit status
echo "Backup finished with exit code $? at $(date)" >> $LOG_FILE

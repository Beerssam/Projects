#!/bin/sh
# Refresh Cockpit's copy of the 625731 cert after a Let's Encrypt renewal.
case "$RENEWED_DOMAINS" in
  *625731.nodes.allstarlink.org*) ;;
  *) exit 0 ;;
esac
cat /etc/letsencrypt/live/625731.nodes.allstarlink.org/fullchain.pem /etc/letsencrypt/live/625731.nodes.allstarlink.org/privkey.pem > /etc/cockpit/ws-certs.d/625731.nodes.allstarlink.org.cert
chmod 600 /etc/cockpit/ws-certs.d/625731.nodes.allstarlink.org.cert
systemctl restart cockpit.socket cockpit 2>/dev/null || systemctl restart cockpit 2>/dev/null || true

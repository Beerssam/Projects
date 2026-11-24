# AllStar hub (node 625731) — configs saved 2026-11-24

Live host: Allstar-Hub, 192.168.1.200, user `asl`. Debian 13 (trixie), ASL3.

## Files

| File here | Live path on the hub |
|---|---|
| `000-asl3-appliance-ssl.conf` | `/etc/apache2/sites-enabled/000-asl3-appliance-ssl.conf` |
| `apache-tls.conf` | `/etc/asl-web-ui/apache-tls.conf` |
| `cockpit-cert.sh` | `/etc/letsencrypt/renewal-hooks/deploy/cockpit-cert.sh` |

- `000-asl3-appliance-ssl.conf` — Apache's HTTPS site. Includes the AI dashboard proxy (`/ai-dashboard/` plus the dashboard's absolute API paths `/api/*`, `/stream`, `/action/` to the Flask app on 127.0.0.1:62573). The API lines were added 2026-11-24 to fix the laptop no-data issue; the WebUI's `/api/v1/` is deliberately NOT proxied here.
- `apache-tls.conf` — written by the WebUI when it got its Let's Encrypt cert; just the two `SSLCertificate*` lines for `625731.nodes.allstarlink.org`.
- `cockpit-cert.sh` — deploy hook run by certbot after a renewal of the 625731 cert; rebuilds Cockpit's combined cert and restarts Cockpit.

## Certificates

- One cert on the hub: `625731.nodes.allstarlink.org`, Let's Encrypt, valid to 2027-02-22.
- Renewal dry-run (`certbot renew --dry-run`) passed 2026-11-24 — simulated renewal succeeded, no live cert changed.
- Renewal needs no port flip: the Pi5 nginx passes only the ACME challenge path through to the hub.

## WebUI Cockpit-link fix (documented, not copied)

2026-11-24 the WebUI's hardcoded Cockpit link (`:9090`) was changed to use **9091 on `*.nodes.allstarlink.org`, 9090 otherwise**, in three package files:

- `/usr/share/asl-web-ui/www/app.js` (1.4 MB minified bundle — not copied here)
- `/usr/share/asl3-appliance/web/js/index.js`
- `/usr/share/asl3-appliance/web/fallback-ap.html`

These are package files, so a future `asl-web-ui` / `asl3-appliance` update will overwrite them and the fix must be re-applied. Backups of the patched files are in `/home/asl/backups/20261124/` on the hub.

## NOT included (secrets)

- `ai_dashboard.py` and `ai_orchestrator.py` (`/home/asl/`) — both contain plaintext secrets (dashboard password, Gemini API keys). They are backed up as patches under `allstar-ai-hub/patches/`, not as live files. Never commit them as-is.
- `/etc/cockpit/ws-certs.d/625731.nodes.allstarlink.org.cert` — combined cert + private key. Rebuild it from the Let's Encrypt files with `cockpit-cert.sh` instead.
- `/home/asl/.aviationstack_key` — API key file. Never commit.

## Restore

Copy the files back to the live paths above, run `apachectl configtest`, then `systemctl reload apache2`. For the cert hook, copy to the deploy-hooks dir and `chmod +x`.

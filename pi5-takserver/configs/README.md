# Pi5 "PI5-TAKserver" — configs saved 2026-11-24

Live host: 192.168.1.199, user `sbeers`. Runs OpenTAK, nginx, Docker (Nextcloud + Guacamole).

## Files

| File here | Live path on the Pi5 |
|---|---|
| `nginx/allstar-hub` | `/etc/nginx/sites-available/allstar-hub` |
| `nginx/allstar-node` | `/etc/nginx/sites-enabled/allstar-node` |
| `nginx/huc-location.conf` | `/etc/nginx/huc-location.conf` |
| `letsencrypt-hooks/opentakserver.sh` | `/etc/letsencrypt/renewal-hooks/deploy/opentakserver.sh` |
| `letsencrypt-hooks/reload-services.sh` | `/etc/letsencrypt/renewal-hooks/deploy/reload-services.sh` |

- `nginx/allstar-hub` — the 625731 site. Port 80 serves the ACME challenge (Pi5 webroot first, else proxy to the hub) and redirects the rest to HTTPS. Port 443 (Pi5's 625731 cert) proxies `/asl-web-ui/`, `/allscan/`, `/allmon3/` to the hub's HTTPS, `/ai-dashboard/` plus the dashboard's absolute API paths (`/api/*`, `/stream`, `/action/`) to the Flask app on 192.168.1.200:62573, and catch-all `/` to the hub's HTTPS. The API locations were added 2026-11-24 to fix the laptop no-data issue.
- `nginx/allstar-node` — the 625730 site. Note it lives in `sites-enabled/` (a regular file, not a symlink), not `sites-available/`. It includes `/etc/nginx/huc-location.conf`, which is saved here as `nginx/huc-location.conf` — it proxies `/huc/` to the 625730 host's 8443 (websocket UI) and rewrites redirects back under `/huc/`.
- The two hook scripts are certbot deploy hooks: one restarts OpenTAK after a renewal, the other reloads nginx and restarts the EUD handler.

## Certificates

Five certs on the Pi5, all Let's Encrypt. Renewal dry-run (`certbot renew --dry-run`) passed 2026-11-24 — all 5 simulated renewals succeeded, no live cert changed:

- `625730.nodes.allstarlink.org`
- `625731.nodes.allstarlink.org` (expires 2027-02-22)
- `beershome.ddns.net-0001` (beershome.ddns.net + beershome.duckdns.org)
- `beershome.duckdns.org` (beershome.duckdns.org + beersradio.duckdns.org)
- `beersphotos.duckdns.org` (expires 2027-02-18)

## NOT included (secrets)

- `~/duckdns/duck.sh` — contains the DuckDNS token.
- `/home/sbeers/nextcloud/docker-compose.yml` and `/home/sbeers/immich/docker-compose.yml` — may contain passwords. Back those up separately with secrets redacted.
- Nothing under `/etc/letsencrypt/live/` — private keys are never committed. Only the public cert paths appear in the configs above.

## Restore

Copy the nginx files back to the live paths, run `nginx -t`, then `systemctl reload nginx`. Copy the hook scripts to the deploy-hooks dir and `chmod +x`.

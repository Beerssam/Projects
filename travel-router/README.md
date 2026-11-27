# travel-router — GL.iNet GL-MT3000 (Beryl AX)

Sam's travel router, stationary on the home LAN as an extension of the
main AT&T router. Reached for admin over ZeroTier at **10.167.65.134**
(home-LAN/WAN side: 192.168.1.136). Its public name is
**beerswifi.duckdns.org**, pinned to the ZeroTier address so the admin
panel is reachable by name from Sam's phone over ZeroTier.

This folder is the recovery kit for the state a firmware update or
factory reset can wipe. Built Nov 26, 2026, after a firmware update
broke three separate things in one day (below).

## The arrangement

- **DNS record:** beerswifi.duckdns.org -> 10.167.65.134 (set by hand
  on DuckDNS; must never be auto-updated to the public IP).
- **Certificate:** Let's Encrypt cert for beerswifi.duckdns.org,
  issued by acme.sh on the Pi5 (PI5-TAKserver) via DNS-01. Renewal was
  always automatic; *delivery* to the router is done by a custom
  deploy hook (`glrouter.sh`, reference copy in this folder) that
  pipes the cert/key over SSH and HUPs the router's nginx master.
- **Panel by name:** GL's nginx Lua gate only serves Hosts on a UCI
  allowlist, so beerswifi.duckdns.org must be in
  `oui-httpd.main.allowed_host` or the panel spins at #/login.
- **Ad blocking:** the router's built-in AdGuard Home is the phone's
  primary DNS in its ZeroTier Custom DNS (secondary: Control D
  76.76.2.2). Filtering verified by dig: ad domains -> 0.0.0.0,
  rs-ny.rustdesk.com -> its real address.

## What broke on Nov 26, 2026 (and the fixes)

1. **DNS record kept reverting to the public IP.** The Pi5's
   `~/duckdns/duck.sh` (cron, every 5 min) was updating beerswifi
   along with the other DuckDNS names. Fix: `beerswifi` removed from
   the domains list in duck.sh (backup `duck.sh.bak-20261126` on the
   Pi5); the record re-set by hand to 10.167.65.134.
   **Never put beerswifi back in duck.sh.** (duck.sh itself holds the
   DuckDNS token — it is never committed anywhere.)
2. **Certificate expired on the router (Nov 20) while renewal was
   healthy on the Pi5.** The missing link was delivery. Fix: Pi5 SSH
   key into the router's dropbear authorized_keys + custom acme.sh
   deploy hook `glrouter.sh` (stock ssh hook uses scp, which this
   router cannot do — no sftp-server; the hook pipes over ssh
   instead). Registered as `Le_DeployHook='glrouter,'` and
   force-tested successfully Nov 26, 2026. Next renewals deliver
   automatically.
3. **Panel loaded by IP but spun forever by name.** GL's
   `/usr/share/gl-ngx/oui-access.lua` returns 403 for any Host not on
   its allowlist; the app shell loads, its first /rpc call gets 403,
   and the login view never renders. Fix:
   `uci add_list oui-httpd.main.allowed_host=beerswifi.duckdns.org`
   + `uci commit oui-httpd` (no restart needed; the gate re-reads
   UCI per request). Rollback: `uci del_list ...` + commit.
   The gate almost certainly arrived with the recent firmware
   update — if the name spins again after a future update, re-check
   this entry first.

## Files

- `apply-fixes.sh` — run as root **on the router** after an update or
  reset. Restores items 3's UCI entry, the AdGuard Home toggles, and
  the Pi5's SSH key in authorized_keys. Backs up before touching,
  idempotent, verifies by read-back.
- `glrouter.sh` — reference copy of the Pi5-side acme.sh deploy hook
  (lives at `~/.acme.sh/deploy/glrouter.sh` on the Pi5). No secrets.
- `patch_agh_lists.sh` — the AdGuard blocklist upgrade (Nov 26, 2026):
  enables the stock AdAway list and adds OISD Big + HaGeZi Multi PRO
  (471k extra rules total). Idempotent; backs up the AGH config
  first. Re-run after any reset that wipes /etc/AdGuardHome.

## Recovery sequence after a firmware update / reset

1. Confirm the router still answers at 10.167.65.134 over ZeroTier.
   (If its ZeroTier identity was wiped it will have a *different*
   address — rejoin/re-authorize it and re-point the DuckDNS record
   first; this kit assumes the address is unchanged.)
2. On the router, as root: `sh apply-fixes.sh`
3. From the Pi5, re-deliver the certificate:
   `~/.acme.sh/acme.sh --deploy -d beerswifi.duckdns.org --deploy-hook glrouter`
4. On the Pi5, remove `beerswifi` from `~/duckdns/duck.sh` again if a
   Pi5 restore ever brought back the old domains list.
5. On the router: `sh patch_agh_lists.sh` to restore the upgraded
   AdGuard blocklists (a reset wipes /etc/AdGuardHome).
6. Verify (below).

## Verification

- Panel by name: https://beerswifi.duckdns.org loads and logs in.
- Cert on the wire (probe a few seconds *after* any reload — a probe
  raced with the HUP can still hit a draining old worker):
  `echo | openssl s_client -connect 10.167.65.134:443 -servername beerswifi.duckdns.org 2>/dev/null | grep -E 'notAfter|subject'`
- AdGuard filtering, from the Pi5:
  `dig @10.167.65.134 pagead2.googlesyndication.com +short` -> `0.0.0.0`
  `dig @10.167.65.134 rs-ny.rustdesk.com +short` -> `209.250.254.15`

## Known quirks (not bugs to chase)

- **AdGuard Home keeps no books on this GL build.** The panel stats
  read zero and no query log is ever written (verified Nov 26, 2026:
  even a forced flush on service restart produced no querylog.json).
  Filtering works; the scoreboard doesn't. Cosmetic.
- **AdGuard's own dashboard is suppressed** in this --glinet build:
  port 3000 and the panel's "Settings Page" link both redirect to
  the GL panel.
- **scp to the router fails** (no sftp-server). Pipe over ssh:
  `ssh root@10.167.65.134 'cat > /path' < localfile`
- **`/etc/init.d/nginx reload` is a no-op.** Reload = SIGHUP the
  nginx master:
  `kill -HUP $(ps w | grep "[m]aster process" | awk '{print $1}')`
- **Restarting the adguardhome service reloads the whole firewall**
  (pages of fw3 warnings — normal).
- Router nginx has `access_log off;` — only error.log exists, and
  the host gate's 403s don't appear in it.

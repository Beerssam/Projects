# Node Disaster Recovery — KF0RIZ ASL3/DVSwitch node (625730)

The bare-card-to-on-air runbook. The GitHub backup set is a **redacted
config layer**, not a disk image: this procedure rebuilds the node from a
fresh ASL3 install plus the configs in this repo, with the secrets
re-entered by hand at the end. Budget 1–2 hours, most of it waiting on
installs. Written Oct 23 2026 against backup set format v2
(`backup-node-configs.sh` v2 / `restore-node.sh`).

## What you need before you start

- A fresh microSD with the current ASL3 image, booted, on the network.
- This repo cloned on the node (step 4) — it carries the backup sets under
  `allstar-dmr/node-configs/backups/`.
- Sam's own password records (NOT in GitHub, by design):
  BrandMeister hotspot password, TGIF password, AllStar node password /
  IAX secret, Asterisk manager password. The restore script prints the
  exact list of redacted fields when it finishes.

## Procedure

1. **Flash and boot ASL3.** First-boot setup: hostname, user `ASL3`,
   network. Note the node's LAN IP (dashboard and pages hang off it).
2. **Recreate the nodes.** In `asl-menu` (or by hand later via the restored
   `rpt.conf`): main node **625730**, hub **625731**, DVSwitch pseudo-node
   **1999** (USRP, duplex 0). The restored Asterisk configs assume these
   numbers — if the fresh install created a different node number, the
   restored `rpt.conf` wins, but make sure no duplicate node stanzas fight.
3. **Install DVSwitch** (Sam's node uses the DVSwitch bookworm repo):
   ```
   wget http://dvswitch.org/bookworm && chmod +x bookworm && ./bookworm
   apt update && apt install dvswitch-server
   ```
   This lays down Analog_Bridge, MMDVM_Bridge, the gateways and parrots —
   the versions in `manifests/packages.txt` of the backup set are what the
   old node ran; the repo's current versions are fine.
4. **Clone this repo** as ASL3:
   ```
   cd /home/ASL3 && git clone https://github.com/Beerssam/Projects.git
   ```
5. **Install the pieces the packages don't carry:**
   - SkywarnPlus (severe-weather alerter): install per the SkywarnPlus
     project instructions into `/usr/local/bin/SkywarnPlus/` — code only;
     its config comes back in step 6.
   - AllScan and Supermon live in the web root and come back with the
     restore itself (their config-bearing trees are in the backup set).
     Allmon3 is an ASL3 package (already present); only its
     `/etc/allmon3` config is restored.
6. **Run the restore** (pick the newest timestamp in the backup folder):
   ```
   cd /home/ASL3/Projects
   sudo bash allstar-dmr/node-configs/restore-node.sh latest --dry-run
   sudo bash allstar-dmr/node-configs/restore-node.sh latest
   ```
   The dry run shows what would change. The real run safety-copies every
   file it overwrites (path printed), restores the bridge/gateway inis,
   `/etc/asterisk`, `/etc/ircddbgateway`, `/etc/allmon3`, the Supermon /
   AllScan / AutoSky web trees, SkywarnPlus config, the YSF hosts file,
   systemd overrides, and both crontabs. **Analog_Bridge.ini is never
   auto-restored** — diff it by hand against the backup and merge
   (its gain/port tuning is node-specific).
7. **Re-enter the secrets** the restore report listed (fields marked
   `__REDACTED__`), then check the DMR side still has its
   `__SET_...__`-style values replaced real values in
   `/opt/DMRGateway/DMRGateway.ini` — BrandMeister + TGIF passwords.
8. **Rebuild DMRGateway** (not packaged):
   ```
   sudo bash allstar-dmr/scripts/build-dmrgateway.sh
   ```
9. **Install the dashboard and the YSF parrot fix:**
   ```
   sudo bash allstar-dmr/dashboard/install.sh
   sudo bash allstar-dmr/node-configs/fix-ysf-parrot-host.sh
   ```
10. **Re-join Tailscale** if used (`tailscale up`) — node identity keys
    are never backed up (they're secrets); `manifests/tailscale.txt`
    shows what the old node looked like on the tailnet.
11. **Start everything and verify** (next section).

## Acceptance checklist

- [ ] `systemctl status` clean for: analog_bridge, mmdvm_bridge,
      dmrgateway, ysfgateway, nxdngateway, p25gateway, ircddbgatewayd,
      ysfparrot, apache2, allmon3
- [ ] Dashboard loads at `http://<node-ip>/dvswitch-control.html`;
      SERVICES shows BM / TGIF / KS-DMR Connected
- [ ] Link 1999 to 625730; DMR: BM parrot 9990 echoes your voice
- [ ] YSF: tune 99999, key 5 s — local parrot plays you back
- [ ] NXDN: tune 65000, key up with 1999 linked
- [ ] D-STAR: tune REF001C, key up — gateway links the reflector
- [ ] Supermon page loads and shows the node; Allmon3 page loads
- [ ] AllScan page loads with its configuration intact
- [ ] SkywarnPlus: run a manual poll/test; confirm the hourly saytime
      announcement and both nightly reboot entries are back in crontab
      (`crontab -l` as root — 02:00 and 04:00 `shutdown -r` entries)
- [ ] Analog side: connect 625730 ↔ 625731 hub as usual

## What is NOT in the backup (and why)

| Missing | Why / where it lives instead |
|---|---|
| Passwords, API keys, tokens, password hashes | Redacted by design — Sam's own records; the restore report lists every field to fill |
| Tailscale / SSH identity keys | Secrets; re-join / regenerated on the new install |
| The OS and packages themselves | Reinstalled in steps 1–3; exact old versions in `manifests/packages.txt` |
| Analog_Bridge.ini auto-restore | Blocked on purpose — hand-merge (step 6) |
| Log files, astdb, subscriber databases | Regenerate on their own (Supermon astdb cron, DVSwitch dbupdate) |
| DMRGateway binary | Rebuilt from source in step 8 (repo carries the build script + patches) |

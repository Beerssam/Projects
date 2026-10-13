# DVSwitch control panel — design brief (draft, Oct 13 2026)

Sam asked for a custom DVSwitch control panel to replace the stock one
("I hate how the dvswitch mode switches works its so not user friendly").
Audio troubleshooting comes first; this is groundwork for that conversation.

## Requirements (Sam's words)

- Handle all digital modes: DMR, YSF, M17, P25, etc.
- Only one DMR mode active at a time, with easy switching between the DMR
  modes (BrandMeister / TGIF / KS-DMR).
- Replace the old DVSwitch mode-switch UI.

## Control surfaces available on the node (verified)

- `dvswitch.sh mode {DMR|NXDN|P25|YSF|DSTAR}` — sets Analog_Bridge's digital
  mode. (Source: DVSwitch Mobile DVSM doc, lists.hamvoip.org attachment.)
- `dvswitch.sh tune <tg>` — tunes to a TG/reflector. For DMR/P25/NXDN it's
  just the TG number, so Sam's 7-digit dial strings (4000777, 7003120) pass
  through unchanged. (Same source; also the ASL wiki dialplan doc.)
- Status: `systemctl status` on analog_bridge/mmdvm_bridge/dmrgateway,
  DMRGateway log via `journalctl -u dmrgateway`, tune state via
  `/opt/MMDVM_Bridge/dvswitch.sh` helpers.
- DMRGateway keeps all three DMR networks connected simultaneously; "DMR
  mode" = whichever network the tuned dial string routes to. RX from any
  network flows when its slot is free, so the panel doesn't need to
  connect/disconnect networks — just tune.

## Prior art (reference, not to copy)

- `ki9ng/dvswitch-control-panel`: web panel on ASL3, mode buttons + quick
  tune + favorites, installed via script, served as
  `http://NODE_IP/dvswitch-control.html` through Apache with a CGI backend
  (`/var/www/cgi-bin/dvswitch-control.sh`). Proves the pattern works.
- `firealarmss/dvswitch_mode_switcher` (port 3000): the one Sam dislikes.
  Its TG dropdown is fed by `tg_alias.yml` (already populated for KF0RIZ in
  this repo, commit c17f92e — still useful as the preset list source).

## Proposed shape

Single lightweight page served on the node (same Apache+CGI pattern as the
proven prior art, no new dependencies):
- Mode row: DMR / YSF / P25 / NXDN / D-STAR (+ M17 if present on the node)
- DMR sub-row (visible in DMR mode): BrandMeister | TGIF | KS-DMR quick
  presets — BM: 91, 3100, 3120 · TGIF: 4000777 (777) · KS-DMR: 7003120.
  Tapping one runs `dvswitch.sh mode DMR` (if needed) + `tune <dial string>`.
- Status strip: service states + last DMRGateway log lines + current tune.
- Favorites: reuse the `tg_alias.yml` preset list already in this repo.

## Open questions for Sam (decide before building)

1. Which non-DMR modes are actually installed on the node? (M17 is not an
   Analog_Bridge mode — check what the node really runs before promising it.)
2. Replace the :3000 switcher outright, or run side-by-side?
3. Any auth needed, or LAN-only like the existing UIs?
4. Favorite TGs beyond the dial-plan presets?

## Install change list (when approved — Sam confirms before running)

- Files: one HTML page + one CGI script on the node, presets copied from
  this repo's `tg_alias.yml`.
- Backup: existing web root / CGI dir listing first.
- Services: apache2 reload only; no bridge restarts.

# KF0RIZ AllStar multi-mode DMR — install notes

Callsign **KF0RIZ**, DMR ID **3209686**. Three DMR networks: BrandMeister (via 3103
San Jose, closest US master to Arizona), TGIF, and KS-DMR (native Kansas network).

## Dialing

| You dial (from AllStar) | Goes to |
|---|---|
| Plain TG, e.g. `91`, `3104`, `3120` | BrandMeister (TS1/TS2 as dialed) |
| `4` + TG, e.g. `4000777` | TGIF TG 777 |
| `7003120` | KS-DMR Kansas Statewide (TS2, native Kansas network) |

## What these files are

- `DMRGateway.ini` — the multi-mode heart. **DMRGateway is not part of DVSwitch**
  and not configured by the `dvs` menu; you build it from source (step 1).
  Its local side is `[General]` RptAddress/RptPort (NOT an unnumbered
  `[DMR Network]` section — current DMRGateway would misparse that as an
  upstream network).
- `MMDVM_Bridge.ini` — DMR leg repointed from the BM master to the local
  DMRGateway (127.0.0.1:62031). Only `[DMR Network]` changes vs. stock.
- `Analog_Bridge.ini` — audio bridge reference. `deploy-on-node.sh` **never
  overwrites** the node's live `/opt/Analog_Bridge/Analog_Bridge.ini` (your
  multi-mode config stays); the repo copy is installed only on nodes that
  don't have one yet, and is staged for validation.
- `DVSwitch.ini` — reference only. The stock file at
  `/opt/MMDVM_Bridge/DVSwitch.ini` already has the correct `[DMR]` partner
  ports; do not overwrite it.
- `dmrgateway.service` — systemd unit for the source-built DMRGateway.
- `deploy-on-node.sh` — one-shot installer: backs up, fills passwords,
  validates, installs, restarts. **Read it before running it.**
- `verify-on-node.sh` — post-deploy health check (daemons, ports, logins).
- `tg_alias.yml` — talkgroup list for the DVSwitch Mode Switcher web UI
  (port 3000). The switcher's "Switch Talkgroup" dropdown is filled from this
  file; copy it to the switcher's `configs/` dir on the node and the UI picks
  it up in seconds, no restart.

The two network **passwords are left as `__SET_...__` markers** — filled in on
the node by `deploy-on-node.sh`, never committed.

## Install

1. **Build DMRGateway** (once): `sudo bash ../../scripts/build-dmrgateway.sh`
2. From a fresh `git pull` of this repo on the node:
   `cd allstar-dmr/nodes/kf0riz && sudo bash deploy-on-node.sh`
   It first looks for passwords the node already has (an existing
   DMRGateway.ini, or the stock MMDVM_Bridge.ini for BrandMeister) and only
   asks for the ones it can't find. It validates everything, then installs
   and restarts DMRGateway → MMDVM_Bridge → Analog_Bridge in order.
3. Wait ~30s, then: `sudo bash verify-on-node.sh`

## If something's off

- "Connected but no audio" → almost always the BM hotspot password.
- Parrot (`9990`) won't answer back → PCRewrite maps RF→network only, with no
  auto-inverse like TGRewrite, so the echo never comes home. Use TG `91` for
  the audio test instead.
- One network logs in then gets kicked → duplicate DMR ID; the three ESSIDs
  (`...01`, `...02`, `...03`) must each be unique per connection.
- No audio on TGIF → check the `4`-prefix rewrite rules and that the stanza is enabled.
- TGIF **777 scan** silent but the dashboard shows traffic → the scan returns
  real TG numbers (e.g. 8003120, 5029332, 5000777); DMRGateway drops network
  traffic matching no rewrite rule, so the `[DMR Network 2]` TGRewrite range
  must cover them (fixed Oct 13 2026: range widened to 9999999).
- Audio too hot/quiet → `usrpGain`/`tlvGain` in `Analog_Bridge.ini [USRP]`.
- DMRGateway won't start → `sudo journalctl -u dmrgateway -e` (it logs to stdout).

# KF0RIZ AllStar multi-mode DMR — install notes

Callsign **KF0RIZ**, DMR ID **3209686**. Three DMR networks: BrandMeister (via 3103
San Jose, closest US master to Arizona), TGIF, and KS-DMR (native Kansas network).

## Dialing

| You dial (from AllStar) | Goes to |
|---|---|
| Plain TG, e.g. `91`, `3104`, `3120` | BrandMeister (TS1/TS2 as dialed) |
| `4` + TG, e.g. `4000777` | TGIF TG 777 |
| `73120` | KS-DMR Kansas Statewide (TS2, native Kansas network) |

## What these files are

- `DMRGateway.ini` — the multi-mode heart. **DMRGateway is not part of DVSwitch**
  and not configured by the `dvs` menu; you build it from source (step 1).
  Its local side is `[General]` RptAddress/RptPort (NOT an unnumbered
  `[DMR Network]` section — current DMRGateway would misparse that as an
  upstream network).
- `MMDVM_Bridge.ini` — DMR leg repointed from the BM master to the local
  DMRGateway (127.0.0.1:62031). Only `[DMR Network]` changes vs. stock.
- `Analog_Bridge.ini` — audio bridge. If your node already bridges DMR audio
  fine, keep your existing `[USRP]` values; the `[AMBE_AUDIO]` ports here are
  the DVSwitch stock pairing.
- `DVSwitch.ini` — reference only. The stock file at
  `/opt/MMDVM_Bridge/DVSwitch.ini` already has the correct `[DMR]` partner
  ports; do not overwrite it.
- `dmrgateway.service` — systemd unit for the source-built DMRGateway.
- `deploy-on-node.sh` — one-shot installer: backs up, fills passwords,
  validates, installs, restarts. **Read it before running it.**
- `verify-on-node.sh` — post-deploy health check (daemons, ports, logins).

The two network **passwords are left as `__SET_...__` markers** — filled in on
the node by `deploy-on-node.sh`, never committed.

## Install

1. **Build DMRGateway** (once): `sudo bash ../../scripts/build-dmrgateway.sh`
2. From a fresh `git pull` of this repo on the node:
   `cd allstar-dmr/nodes/kf0riz && sudo bash deploy-on-node.sh`
   It asks for your BrandMeister hotspot-security password (SelfCare → Security)
   and TGIF password, validates everything, then installs and restarts
   DMRGateway → MMDVM_Bridge → Analog_Bridge in order.
3. Wait ~30s, then: `sudo bash verify-on-node.sh`

## If something's off

- "Connected but no audio" → almost always the BM hotspot password.
- One network logs in then gets kicked → duplicate DMR ID; the three ESSIDs
  (`...01`, `...02`, `...03`) must each be unique per connection.
- No audio on TGIF → check the `4`-prefix rewrite rules and that the stanza is enabled.
- Audio too hot/quiet → `usrpGain`/`tlvGain` in `Analog_Bridge.ini [USRP]`.
- DMRGateway won't start → `sudo journalctl -u dmrgateway -e` (it logs to stdout).

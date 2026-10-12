# AllStar DVSwitch Multi-Mode DMR

Bridge one AllStarLink ASL3 node to **multiple DMR networks** (e.g. BrandMeister + TGIF)
through DVSwitch Server. One AllStar node, several DMR networks, talkgroup routing by prefix.

## How it works

```
app_rpt (ASL3 / Asterisk)
  -> Analog_Bridge   (PCM <-> AMBE voice frames, via chan_usrp UDP)
  -> MMDVM_Bridge    (AMBE <-> DMR frames, its DMR side points at local DMRGateway)
  -> DMRGateway      (routes by talkgroup rewrite rules to N upstream DMR networks)
  -> BrandMeister, TGIF, KS-DMR, ...
```

DMRGateway supports up to **5 upstream networks** (+ XLX). Each network stanza needs its
own rewrite rules — a stanza with no TGRewrite rules passes nothing.

> **DMRGateway is not part of DVSwitch.** It isn't in the DVSwitch apt repo and the
> `dvs` menu doesn't configure it. Build it from source with
> `scripts/build-dmrgateway.sh` (github.com/g4klx/DMRGateway).

**Dialing convention (example):** dial TGs normally for BrandMeister (network 1);
prefix with `4` (e.g. `4000777`) to reach TGIF TG 777 (network 2). Prefixes are yours to choose.

## Bring-up order (important)

1. Install DVSwitch Server on the ASL3 box: `sudo bash scripts/install-dvswitch-bookworm.sh`
2. Run the DVSwitch menu (`cd /usr/local/dvs && sudo ./dvs`) and get **single-network DMR
   working first**. The menu's generated `.ini` files are ground truth — if anything in
   `templates/` disagrees with them on port numbers or key names, trust the menu output.
3. Copy `vars.example.sh` to `vars.sh` and fill in your DMR ID, callsign, and network
   passwords. `vars.sh` is gitignored — never commit real credentials.
4. Render the configs: `bash scripts/generate-configs.sh` → files land in `output/`
5. Install them over the files in `/opt/...` (paths below), then restart services **in order**:
   DMRGateway → MMDVM_Bridge → Analog_Bridge (Asterisk stays running).
6. Key a talkgroup: `sudo /opt/MMDVM_Bridge/dvswitch.sh tune <TG>`

## Files

- `templates/DMRGateway.ini` — the multi-mode heart: `[General]` RptAddress/RptPort
  for the localhost leg + 2+ `[DMR Network N]` upstream stanzas with rewrite rules.
  **No unnumbered `[DMR Network]` section** — current DMRGateway would parse it as
  an upstream network, not the localhost leg.
- `templates/MMDVM_Bridge.ini` — DMR side pointed at the local DMRGateway
  (`Address=127.0.0.1, Port=62031, Local=62032`; verified against DMRGateway source)
- `templates/Analog_Bridge.ini` — links ASL (USRP) to MMDVM_Bridge (AMBE audio);
  key names verified against the DVSwitch-distributed ini
- `scripts/build-dmrgateway.sh` — builds DMRGateway from source (not in DVSwitch repo)
- `scripts/install-dvswitch-bookworm.sh` — DVSwitch apt install for Debian 12 / ASL3
- `scripts/generate-configs.sh` — fills templates from `vars.sh` into `output/`
- `scripts/validate-dmr-configs.sh` — sanity-checks a config set before it goes
  on a node (port pairing, ESSIDs, rewrite rules, password markers, AMBE pairing)
- `vars.example.sh` — copy to `vars.sh` and fill in (gitignored)
- `nodes/kf0riz/` — finished configs for Sam's node (KF0RIZ / 3209686):
  BrandMeister + TGIF + KS-DMR via DMRGateway, passwords left as `__SET_...__`
  markers; includes `deploy-on-node.sh`, `verify-on-node.sh`, `dmrgateway.service`

## Typical install paths (DVSwitch Server on Debian 12)

- `/opt/Analog_Bridge/Analog_Bridge.ini`
- `/opt/MMDVM_Bridge/MMDVM_Bridge.ini`
- `/opt/MMDVM_Bridge/DMRGateway.ini` (on some builds `/opt/DMRGateway/DMRGateway.ini`)
- `/etc/asterisk/rpt.conf`, `/etc/asterisk/usrp.conf` (ASL side, chan_usrp)

## UDP ports

| Ports | Scope | Purpose |
|---|---|---|
| 62031 | outbound to masters | DMR master links (BM hotspots; repeaters use 62030) |
| 62031 / 62032 | localhost | MMDVM_Bridge ↔ DMRGateway: DMRGateway binds 62031 (`[General]` LocalPort) and only accepts frames from 62032 (`[General]` RptPort); MMDVM_Bridge uses `Port=62031, Local=62032` |
| 31100 / 31103 | localhost | Analog_Bridge ↔ MMDVM_Bridge (AMBE/TLV audio, crossed: AB txPort 31103 → MM rxPort 31103, MM txPort 31100 → AB rxPort 31100) |
| 32001 / 34001 | localhost | ASL chan_usrp ↔ Analog_Bridge (common convention; keep your working values) |

Open outbound 62031; don't firewall the localhost inter-process ports.

## Gotchas

- Every upstream network connection needs a **unique DMR ID**: use ESSID suffixes
  (e.g. `123456701` for BM, `123456702` for TGIF). Reusing the base ID on two networks
  gets one login kicked.
- BrandMeister **requires the hotspot security password** (brandmeister.network →
  SelfCare → Security → Hotspot Security). The old default `passw0rd` is rejected —
  this is the #1 "connected but no audio" cause.
- A `[DMR Network N]` stanza with **no TGRewrite rules passes nothing**.
- Audio levels: start `txGain`/`rxGain` at 0.50, adjust on reports.
- BM static vs dynamic TGs: bridge PTT keys dynamic TGs; set static TGs in BM SelfCare.
- ASL3 = Debian 12 bookworm. Do **not** use the `dvswitch.org/trixie` installer on it.

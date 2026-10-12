# KF0RIZ AllStar multi-mode DMR — install notes

Callsign **KF0RIZ**, DMR ID **3209686**. Two DMR networks: BrandMeister (via 3103
San Jose, closest US master to Arizona) and TGIF.

## Dialing

| You dial (from AllStar) | Goes to |
|---|---|
| Plain TG, e.g. `91`, `3104`, `3120` | BrandMeister (TS1/TS2 as dialed) |
| `4` + TG, e.g. `4000777` | TGIF TG 777 |
| `73120` | KS-DMR Kansas Statewide (TS2, native Kansas network) |

Three DMR networks are configured: BrandMeister, TGIF, and KS-DMR (the standalone
Kansas HBlink network — you're a Kansas ham, so its public hotspot entry
`vesta.k0usy.org:62071` is fair use for you). Note the public KS-DMR entry only
carries TS2/TG 3120, which is why it's a single dialing mapping rather than a full
prefix range. BrandMeister's own TG 3120 remains available too.

## Install

These files were built from `templates/` with your callsign/ID filled in. The two
network **passwords are left as `__SET_...__` markers** — fill them in on the node,
never commit real passwords.

1. Get single-network DMR working first via the DVSwitch menu:
   `cd /usr/local/dvs && sudo ./dvs` (ground truth for ports/key names).
2. Back up the working configs on the node:
   `sudo cp /opt/MMDVM_Bridge/DMRGateway.ini{,.bak}`
   (same for `MMDVM_Bridge.ini` and `/opt/Analog_Bridge/Analog_Bridge.ini`).
3. Copy these three files over the ones in `/opt/...`.
4. Fill in the passwords:
   - `__SET_BM_HOTSPOT_PASSWORD__` → your BrandMeister hotspot security password
     (brandmeister.network → SelfCare → Security → Hotspot Security).
   - `__SET_TGIF_PASSWORD__` → your TGIF hotspot password (tgif.network dashboard).
5. Double-check the **port pairing** between `MMDVM_Bridge.ini [DMR Network] Port=`
   and `DMRGateway.ini [DMR Network] Local=`, and the `[USRP]` directionality,
   against the `dvs`-generated files from step 1. You can also run the repo's
   consistency checker against these files (or your node's copies):
   `bash ../scripts/validate-dmr-configs.sh [config-dir]`
   It verifies the crossed port pairing, ESSID uniqueness, rewrite rules,
   and that no password markers or caller-ID rewrites slipped in.
6. Restart in order: DMRGateway → MMDVM_Bridge → Analog_Bridge
   (Asterisk stays running).
7. Key a talkgroup: `sudo /opt/MMDVM_Bridge/dvswitch.sh tune 91`

## If something's off

- "Connected but no audio" → almost always the BM hotspot password.
- One network logs in then gets kicked → duplicate DMR ID; the three ESSIDs here
  (`...01`, `...02`, `...03`) must each be unique per connection.
- No audio on TGIF → check the `4`-prefix rewrite rules and that the stanza is enabled.
- Audio too hot/quiet → adjust `txGain`/`rxGain` in `Analog_Bridge.ini`.

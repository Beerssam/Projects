# Cross-Mode Bridge (xmode) — Design (v2)

Sam's requirement (Nov 13 2026): bridge **any digital mode to any
digital mode, on the fly**, mainly between his own private
talkgroups/reflectors on different modes, temporarily, controlled
from the dashboard. Plus automatic gain leveling on **every** audio
path — including the one path Analog_Bridge's built-in AGC does not
cover (analog -> digital) — with a dashboard on/off switch and the
manual sliders always retained.

Sam's architectural correction (Nov 13 2026, evening): the bridge is
digital-to-digital and **never comes out analog**, so it must not
borrow AllStar node numbers (1998/1999 exist to plug digital chains
into his analog node 625730). The path stays inside DVSwitch. This
design (v2) follows that: no Asterisk involvement, no rpt.conf
changes at all.

Node hardware constraint: the AllStar node is a **Pi 3B+**. Sized
for it: leg stacks run only while a bridge is up, software vocoders
only, no D-STAR leg (its codec needs a hardware vocoder).

## Architecture: DVSwitch legs + an AB<->AB USRP crossover

Each mode is a **leg**: a full independent DVSwitch chain.

- **DMR leg**: Analog_Bridge (DMR) + MMDVM_Bridge + its OWN
  DMRGateway instance (own BM/TGIF/KS-DMR logins, new ESSIDs
  320968608 / ...609 / ...610) so the leg can sit on any DMR network
  without touching the main node's DMRGateway.
- **YSF leg**: Analog_Bridge (YSFN) + MMDVM_Bridge + own YSFGateway.
- **P25 leg**: Analog_Bridge (P25) + MMDVM_Bridge + own P25Gateway.
  (Fallback if AB's software IMBE disappoints: USRP2P25 from
  MMDVM_CM in place of AB+MB on this leg.)
- **NXDN leg**: Analog_Bridge (NXDN) + MMDVM_Bridge + own
  NXDNGateway.
- **M17 leg**: a second USRP2M17 instance (own ini/unit/log dir),
  reflector switching by the same pattern as the 1998 bridge helper.

Every leg's PCM side (AB's [USRP], or USRP2M17's [USRP Network]) has
a **fixed listen port** ("home port"). A bridge between legs A and B
is the transcoding crossover documented in Analog_Bridge's own
config (two ABs with crossed USRP ports), with the usrp-agc shim in
the middle for leveling:

- The helper points A's transmit port at the bridge shim's A input
  and B's transmit port at its B input (ini edit, the values persist
  across restarts), generates the shim config (A input -> B's home
  port, B input -> A's home port), and starts both leg stacks plus
  the shim. Audio: network A -> leg A chain -> decode to PCM -> shim
  (AGC both directions) -> leg B encode -> network B, and back.
- Stop: stop the shim and both leg stacks, park the transmit ports.
- **One bridge at a time** — that matches the intended use (a
  temporary bridge between two of Sam's own endpoints). Legs cost
  zero CPU while no bridge is up.
- Each leg's destination (network + TG / reflector) is set by ini
  edit + restart (ini-as-source-of-truth, the m17-switch pattern),
  driven from the dashboard's existing searchable lists (DMR
  talkgroups, YSF/P25/NXDN reflectors, M17 registry).
- The main chains (625730 <-> 1999 DVSwitch, 625730 <-> 1998 M17)
  are untouched and not involved in any way.

## Audio leveling (the "auto gain" requirement)

Three layers, all dashboard-controlled, manual controls never
removed:

1. **AB built-in AGC** (per leg + main chain): `usrpAudio =
   AUDIO_USE_AGC` levels audio coming *from* each digital network
   toward the PCM side. Dashboard toggle flips AGC <-> GAIN.
2. **`usrp-agc` shim** (new, in this repo): a small Python USRP
   pass-through adding AGC + a hard limiter to the directions AB
   does not cover. USRP is a simple public protocol (32-byte header
   — "USRP" + 7 big-endian u32: seq, memory, keyup, talkgroup,
   type, mpxid, reserved — then 160 int16 LE PCM samples per voice
   frame). It processes ONLY type-0 voice payloads, passes every
   other packet byte-identical, preserves headers exactly, and has
   a **bypass mode** (pure pass-through) switchable from the
   dashboard — one tap back to the raw path, manual sliders intact.
   Instances:
   - **Bridge**: generated per bridge; AGC on BOTH directions
     (digital-to-digital leveling is the point).
   - **Main chain**: between Asterisk and the main Analog_Bridge,
     AGC on the Asterisk -> AB direction (the analog -> digital
     path — Sam's original distortion complaint), AB's own gain/AGC
     governs the other direction as today.
3. **Manual gains stay**: the existing dashboard sliders (main
   chain) and per-leg gain sliders (writing one takes that
   direction out of AGC into manual gain — the intended override)
   remain fully functional.

AGC design (per instance, ini-configured): per-frame RMS,
-20 dBFS target, +24/-6 dB range, 5 ms attack / 200 ms release
smoothing (gain moves between frames, no pumping clicks),
-3 dBFS peak limiter last, silence gate (gain freezes below
-50 dBFS RMS instead of pumping noise). Negligible CPU at 8 kHz.

## Port plan (all 127.0.0.1 UDP; installer preflight verifies each
planned bind is free with `ss -ulnp` and stops on any conflict)

Existing (untouched): ASL<->main AB 34001/32001; ASL<->USRP2M17
34002/32002; main TLV 31100/31103, 32100/32103, 33100/33103,
35100/35103; main MB nets 3200/4200, 32010/32011; DMRGateway
62031/62032; M17 net 32012.

Leg home ports (the PCM side listens here; transmit is parked at
34299 while unbridged and pointed at the bridge shim while bridged):
- DMR leg AB rx 34201 · YSF leg AB rx 34211 · P25 leg AB rx 34221
- NXDN leg AB rx 34231 · M17 leg USRP2M17 LocalPort 34240
Bridge shim: listens 34401 (from leg A) / 34402 (from leg B),
sends to the legs' home ports. M17 leg network LocalPort 32013
(32012 is the 1998 bridge's).

Leg TLV (AB <-> MB): DMR 31200/31203, YSF 35200/35203,
P25 32250/32253, NXDN 33200/33203.
Leg MB network locals: YSF 3300/4300 (leg YSFGateway RptPort 4300),
P25 33010/33011 (leg P25Gateway RptPort 33010), NXDN 33022/33021
(leg NXDNGateway RptPort 33021). Gateway instances are cloned from
the node's working gateway inis at install time (see
legs/GATEWAY-PATCHES.md). Leg DMRGateway: MMDVM leg 62131/62132.

Main-chain shim: Asterisk keeps its side (sends to 34001, listens
on 32001 — the rpt.conf USRP convention is send:listen). The shim
takes over 34001/32001 toward Asterisk and faces the AB on a fresh
pair: shim -> AB rx 32021, AB tx 34021 -> shim -> Asterisk 32001.
(The AB [USRP] change rx 34001->32021 / tx 32001->34021 is the
ONLY edit to an existing config in this whole project, done by the
installer with backup; bypass mode makes it safe. 32021/34021,
NOT 32011: 32011 is the main MMDVM_Bridge [P25 Network] LocalPort
— caught in the port audit. The rx/tx direction of this rewire was
itself caught and fixed in fixture testing before first install.)

## Node changes (installer, all backed up, preflight-verified)

- New: /opt/xmode/ (leg configs, usrp-agc, helper, tools) and
  /etc/USRP2M17-xmode.ini.
- New systemd units (installed, NOT enabled — leg stacks start on
  demand when a bridge is started): analog-bridge-xmode-{dmr,ysf,
  p25,nxdn}, mmdvm-bridge-xmode-{...}, dmrgateway-xmode,
  ysfgateway-xmode, p25gateway-xmode, nxdngateway-xmode,
  usrp2m17-xmode, plus usrp-agc@ (instances: main = enabled and
  started; bridge = started per bridge).
- Analog_Bridge.ini (main): only the [USRP] rx/tx change for the
  main shim (above), with backup and a generated ROLLBACK.sh.
- Dashboard: Bridge card + AGC controls (dashboard install.sh).
- NO rpt.conf changes. NO Asterisk changes. Nothing about 1998,
  1999, or 625730 changes.

## Acceptance tests (on the node, with Sam)

1. Bridge DMR(TGIF private TG) <-> YSF(private room): talk on a
   radio on one side (via his WPSD hotspot / second ear), heard on
   the other, and back. Repeat with the bridge shim bypassed to
   compare levels.
2. Bridge with the M17 leg (M17 <-> YSF): second ear via DroidStar
   or a WPSD hotspot in M17 mode.
3. CPU: `top` during a bridged QSO — the two active leg stacks plus
   shim must leave the 3B+ comfortable (expect well under 150% of
   400%).
4. AGC on the main chain: BM 9990 parrot with the main shim on vs
   bypassed; hot and quiet stations even out when on.
5. Reboot: no leg stacks running, main 1999/1998 behavior unchanged,
   bridge starts cleanly from the dashboard afterwards.

## Risks / open items

- AB's P25 software IMBE quality is unproven on this node (the P25
  on-air test is still pending generally). USRP2P25 fallback noted.
- Whether YSFGateway honors [Network] Startup for the YSF leg tune
  is unproven; if it doesn't, that leg's tune gets a remote-command
  v2 (the gateway clone keeps its Remote Commands port for this).
- Multiple DMRGateway logins under one DMR ID with distinct ESSIDs
  is the same pattern the node already uses (602/603/604); leg
  ESSIDs 608/609/610 are new but equivalent.
- A three-or-more-way bridge would need a fanout hub; out of scope
  by design (v1 was a hub design — Sam's direction is pairwise,
  DVSwitch-native).

# Cross-mode bridges for the KF0RIZ ASL3 node — design (DRAFT)

Status: **DRAFT Nov 13, 2026 — researched and written on Muse's side only.
NOT built, NOT pushed, NOT installed. REFINED Nov 13 (Sam, in a later
message): he wants ANY-to-ANY on the fly, mainly between his OWN private
TGs/reflectors on different modes, as temporary bridges — so the
preferred design is now the hub-and-legs design in §7, with the
single-pair converter in §2–§4 kept as the fallback / first-proof route.
Awaiting Sam's pick of the phase-1 leg scope before any build work.**
Follows the same pattern as the M17 bridge (`m17/DESIGN.md`): separate
services running alongside DVSwitch, never touching node 1999.

## 0. The anchor Sam already has: TGIF 913

TGIF's own talkgroup list (the snapshot installed on the node Nov 13,
`dashboard/talkgroups-tgif.json`) lists:

- **913 — "KF0RIZ Digital Cross Mode"**

That is Sam's own talkgroup, named for exactly this job. So the DMR side
of the first bridge is settled: **TGIF TG 913**. No new TG to create, no
busy public talkgroup to tie up on the DMR side.

## 1. Goal

Let Sam talk on TGIF 913 and be heard on another digital mode — P25 or
YSF, his example — and hear replies back, from his analog node (625730)
or from any radio on 913, using the same operating pattern he already
uses: start the bridge when he wants it, stop it when done. Dashboard
control, no hand-editing config files to change destinations.

Non-goals (v1):

- No changes to DVSwitch / DMRGateway / node 1999. The bridge is a
  separate service with its own network logins, exactly like USRP2M17.
- No always-on bridge. A bridge is single-channel and ties up both ends
  while it runs; it is start/stop on demand.
- No D-STAR. There are no working D-STAR converters in this family
  (the fork's own README: DSTAR2xxx utilities are still a work in
  progress and not currently functional).
- No "automatic TX audio leveling" box. See §6 — that idea stays second,
  and the honest answer is per-leg gain set once at build time.

## 2. The tools: nostar/MMDVM_CM

Verified Nov 13, 2026 against the upstream repo
(`github.com/nostar/MMDVM_CM`, same family as the USRP2M17 already
running on the node). It contains, among others:

- `DMR2YSF`, `DMR2NXDN`, `DMR2P25`, `P252DMR`, `YSF2P25`, `YSF2DMR`,
  `NXDN2DMR`, `USRP2YSF`, `USRP2P25`, `USRP2DMR`, `DMR2M17`, `M172DMR`

Two kinds of conversion, and the difference matters for which pair to
build first:

- **DMR ↔ YSF / NXDN: same codec (AMBE+2).** Protocol conversion /
  frame repacking, no vocoder round-trip, no quality loss. This is the
  clean first pair.
- **Anything ↔ P25: real transcode (AMBE+2 ↔ IMBE).** The fork's
  transcoding utilities use md380 firmware to encode/decode AMBE+2 and
  run on ARM (Pi 2/3/4 confirmed) — the ASL3 node is a Pi 3B+, so it
  fits, but it is heavier and costs a little audio quality.
  Works, just not the cleanest first proof.

The phase-2 hub (Analog_Reflector at the core, one transcoder chain per
codec family — AMBE+2, IMBE, Codec2 — fanning out to many modes) is
now the PREFERRED design, per Sam's Nov 13 refinement — see §7. The
single-pair converter below is the fallback / first-proof route if the
hub proves too heavy for the node (see sizing, §7).

## 3. Fallback first pair (if the hub in §7 is too heavy for the Pi 3B+)

**TGIF 913 ↔ YSF, via DMR2YSF** — the no-transcode pair, and Sam's YSF
leg is already proven (traffic carried to reflector 94122, US-XLX503,
Oct 18–20).

Default YSF destination if Sam does not pick another: **94122
(US-XLX503)**, the reflector he has already used successfully. A quieter
dedicated reflector would be better for a standing bridge; 94122 is the
known-working fallback, not a permanent claim on a busy room.

**Alternative first pair, if Sam prefers P25:** TGIF 913 ↔ P25 10200
(North America, already in the dashboard P25 list), via DMR2P25.
Transcode, and 10200 is a busy public talkgroup — on-demand use only,
never left running.

Either way the DMR side stays TGIF 913, so the same bridge identity
works for both; the pairs are separate services, one at a time in v1.

## 4. Architecture (v1, one pair)

```
 DMR radio / analog HT
      |                         TGIF 913
      v                    (own ESSID login, see §5)
 625730 (app_rpt) -- link, operator-controlled --> bridge pseudo-node
                                                        |
                                              DMR2YSF (or DMR2P25)
                                                        |
                                              own gateway instance
                                              (YSFGateway / P25Gateway)
                                                        |
                                              YSF reflector 94122
                                              (or P25 TG 10200)
```

Same shape as the M17 bridge: the converter is to the second mode what
USRP2M17 is to M17 — a standalone network client with its own login,
running beside DVSwitch. It never fights DMRGateway because it never
shares a login or a port with it.

Dashboard control (the "Cross-Mode Bridge card", modeled on the M17
panel): pick side A (network + talkgroup, reusing the dropdowns built
Nov 13), pick side B (mode + reflector/TG), Start/Stop, with a status
line showing whether the bridge service is up and what it is joined to.
v1: one bridge, one pair, start/stop. Changing destination = stop,
reconfigure, start — no live retune in v1.

Operating rules:

- Start/stop on demand only; never always-on, and never left bridged
  into a busy public talkgroup/reflector.
- The bridge never touches 1999, 1998, or the DVSwitch chain. Sam's
  analog node links to the bridge pseudo-node the same way it links to
  1998/1999 — one link at a time for the conversation in progress.
- A bridge is single-channel: while it is up, both ends hear each
  other and nothing else on those channels.

## 5. Identity, ports, and collisions (to verify on the node at build)

- **DMR login:** the bridge needs its own TGIF ESSID so it never
  fights DMRGateway's TGIF login (320968602). Proposed: **320968605**.
  TO VERIFY on the node before any login: 320968601 is Sam's other
  hotspot (not the node), 602 = TGIF main, 603 = KS-DMR. Memory says
  604 = BrandMeister; the repo copy of DMRGateway.ini reads
  `Id=320968633` for the BM network, which does not match — resolve
  that discrepancy from the live ini before assigning 605, and do not
  assume any ESSID is free until the node confirms it.
- **TGIF password:** the bridge reuses the TGIF password the node
  already has (deploy scripts recover it from the existing node ini,
  never log or commit it — same rule as every other node script).
- **Ports in use on the node — do not reuse:** DMRGateway 62031/62032;
  YSF 3200/4200; P25 32010/32011; NXDN 14021/14022; D-Star 20010/20011;
  M17 USRP 34002/32002 + reflector leg 32012. The converter and its
  gateway instance get a fresh, documented pair, checked with `ss`
  at install time the way install-m17.sh does.
- **Build:** clone `nostar/MMDVM_CM`, build only the converter(s) for
  the chosen pair, same idempotent-patch pattern as
  `scripts/build-dmrgateway.sh` and `m17/build-usrp2m17.sh`. Fixture-test
  on Muse's side first (ini parsing, start/stop, bad-input rejection);
  the node install is a script with preflight, backup, and rollback,
  and only runs on Sam's approval with an enumerated change list —
  the standing ritual.

## 6. Audio levels (the second idea — refined scope)

There is no set-and-forget "crisp audio" manager for this stack, and
this design does not invent one — but per Sam's Nov 13 refinement the
hub design puts leveling in one place per leg, which is the closest
this stack gets:

- Every hub leg passes through its own Analog_Bridge, so per-leg gain
  and AGC live in one place per leg. The dashboard gets an **AGC on/off
  toggle per leg, WITH the manual gain sliders always retained as
  fallback** — toggle is not a replacement for the sliders.
- Each single-pair converter likewise has its own per-leg gain
  settings in its ini (`GainAdjustdB` style), set once per bridge leg
  when the bridge is built.
- Analog_Bridge's AGC covers only the digital→analog leg (what Sam
  hears). The analog→digital leg (tlv) stays fixed-gain — the answer
  there is still the tabled parrot A/B test (tlvGain 0.10 vs ~0.30 vs
  ~0.50, same distortion at all gains = upstream clipping), not
  another box.
- Flipping on receive-side AGC in Analog_Bridge is a separate,
  one-line, reversible experiment whenever Sam wants it — not part
  of the bridge build.

## 7. REFINED design (Sam, Nov 13): hub-and-legs, any-to-any on the fly

Sam's refinement: he wants **any-to-any on the fly, mainly between his
OWN private TGs/reflectors on different modes, as temporary bridges**
— not one fixed pair. The design that fits that is hub-and-legs:

- **Hub: Analog_Reflector, already on the node.** Verified from Sam's
  Oct 23 package inventory: `analog-reflector 1.1.30` installed, and
  `/opt/Analog_Reflector` present in the Oct 23 /opt inventory, along
  with `md380-emu` (the software AMBE vocoder) and all the gateways.
  Nothing new to install for the hub itself.
- **One leg per mode:** an Analog_Bridge + MMDVM_Bridge pair per mode
  (DMR, YSF, P25, NXDN), plus a second USRP2M17 instance for the M17
  leg — each leg with its own network login and gateway instance, so
  no leg ever fights the main 1999 DVSwitch chain.
- **Dashboard:** enables/disables legs and sets each leg's destination
  from the existing list machinery (the BM/TGIF talkgroup dropdowns and
  the reflector lists built Nov 13). Any combination of live legs is
  one conversation: e.g. TGIF 913 + P25 10200 + a YSF reflector, all
  joined, then torn down when done.
- **D-STAR leg excluded:** hardware vocoder required; no working
  software route in this family.
- **Sizing constraint — the node is a Pi 3B+** (Sam, Nov 13; the Pi5
  is a different box — do not conflate them when sizing work). The hub
  itself is trivial CPU; the vocoder work is per leg — one conversation
  costs one decode + one encode per other live leg. A CPU/load check
  during acceptance is a built-in step, and if the hub is too heavy
  on the 3B+, the fallback is the single-pair converter in §2–§4.

## 8. Open decisions for Sam (one reply settles the build)

1. **Phase-1 leg scope:** all five modes (DMR, YSF, P25, NXDN, M17)
   as hub legs, or DMR/YSF/P25 first?
2. **First destinations:** TGIF 913 on the DMR leg (settled, §0);
   P25 10200 and YSF 94122 as the defaults for those legs, or
   different / quieter private destinations he names?
3. **Fallback if the hub is too heavy on the Pi 3B+:** single-pair
   DMR2YSF (TGIF 913 ↔ YSF 94122) as the first proof instead?

# M17 for the KF0RIZ ASL3 node — design

Status: **APPROVED Oct 23, 2026 — package built and fixture-tested on Muse's
VM the same day; awaiting push + node install.** (rev 2: dashboard reflector
switching moved into v1 scope at Sam's request.)

Fixture-test summary (Oct 23): build script cloned, patched, and built
USRP2M17 end-to-end (binary reports version 20210406). The switch helper
passed status/connect/disconnect/switch/link/unlink against stubbed
systemd/Asterisk and the real DVRef registry data — including module
validation (M17-002 offers only module A; asking for B is refused before
anything is touched), DNS-host and static-IP reflectors, unknown-reflector
and bad-input rejection. install-m17.sh ran against Sam's real rpt.conf
(from the Oct 23 backup): dry-run changed nothing; the real fixture run
added the [nodes] line inside the section and a [1998] stanza byte-identical
to [1999] except the port pair, verified the ACKN step, and a re-run proved
idempotent. The dashboard CGI returned valid JSON for status/link/switch
with honest ok:false on failure. One real bug was caught and fixed by the
fixture run (missing parent-dir creation before the unit install).

## 1. Goal

Let Sam talk from his analog node (625730) into an M17 reflector, and hear
replies, using the same operating pattern he already uses for DVSwitch:
link a private pseudo-node when he wants the mode, unlink when done.
Reflector switching happens from the dashboard — pick a reflector and a
module, tap, done. Nobody edits config files by hand to change rooms.

Non-goals:

- No changes to DVSwitch. DVSwitch has **no M17 in any version** — verified
  Oct 23 against the DVSwitch source repos (Analog_Bridge's mode list is
  DMR, DMR_IPSC, DSTAR, NXDN, P25, YSFN, YSFW; there is no M17 section or
  M17 gateway anywhere in the suite). Sam's install is already current;
  there is nothing to upgrade into M17.
- No M17 RF. This is a network client only — no modem, no radio, no hotspot
  in the path.
- No changes to how the other modes work. The dashboard's M17 button —
  today a factory remnant that does a meaningless DVSwitch mode switch —
  gets rewired to open the real M17 panel described in §3.

## 2. The bridge: USRP2M17

The tool is **USRP2M17** from the `nostar/MMDVM_CM` project (Tom, N7TAE —
the cross-mode converter family). Its README states its purpose plainly:
converting between USRP PCM audio and M17, "connecting M17 reflectors to
AllStar or svxlink nodes."

Key properties, all verified from source on Oct 23:

- It is itself an M17 client. It connects directly to an mrefd reflector
  (CONN / ACKN handshake, PING/PONG keepalive every ~8 s, automatic
  re-CONN if the reflector stops responding). No hotspot in the middle.
- Codec2 is bundled in the source tree and compiled in. No AMBE dongle,
  no vocoder hardware — M17's codec is open source, so this whole bridge
  is software.
- Links only against libm and pthread. The build is one `make`.
- M17 has no accounts, registration, or passwords. Identity is the
  callsign, carried in the protocol itself. Nothing secret exists in this
  design, so nothing needs redacting in the repo.
- Reflector address is resolved with a normal DNS lookup
  (`CUDPSocket::lookup`), so a hostname works in the config, not just an IP.

Verification build (Muse's VM, GCC 13.3, Oct 23): cloned
`github.com/nostar/MMDVM_CM`, built the `USRP2M17` directory. Two files
needed a one-line fix for the modern compiler — `#include <cstdint>` in
`Conf.h` and `ModeConv.h`. The resulting binary runs and reads its ini
(default `/etc/USRP2M17.ini`, or a path given on the command line). The
node runs Debian bookworm (GCC 12), which may not even need the patches;
the build script will apply them idempotently either way, the same pattern
`build-dmrgateway.sh` already uses for DMRGateway.

Alternatives considered and rejected:

- **MMDVMHost + M17Gateway (g4klx stack):** the gateway expects an MMDVM
  modem / RF path. Wrong tool for a network-only bridge into Asterisk,
  and upstream MMDVM dropped M17 in 2025, leaving those repos archived.
- **WPSD hotspot:** already works on Sam's Pis today, but it doesn't tie
  M17 into the AllStar node, which is the point of this project.
- **Waiting for DVSwitch to add M17:** nothing in their source or repos
  suggests it's coming.

## 3. Architecture

```
 analog HT
    |  RF
    v
 625730 (app_rpt)  <-- internal link, operator-controlled -->  1998 (app_rpt, private)
                                                                    |
                                                       chan_usrp, USRP/127.0.0.1:34002:32002
                                                                    |
                                                              USRP2M17
                                                                    |
                                                       UDP, reflector port 17000
                                                                    |
                                                        mrefd reflector (e.g. M17-M17, module A)
```

Audio path, M17 → analog: reflector sends Codec2 3200 frames; USRP2M17
decodes to PCM and hands it to Asterisk as USRP audio on loopback; node
1998 is linked to 625730, so it comes out the analog side. The reverse
path encodes Sam's analog audio to Codec2 and streams it to the reflector
while his PTT is up. In other words, node 1998 is to M17 exactly what node
1999 is to DVSwitch, and USRP2M17 plays the role Analog_Bridge plays —
except it talks to a reflector directly instead of to MMDVM_Bridge.

Operating rules:

- Link **either** 1998 **or** 1999 to 625730, not both at once — linking
  both would feed two digital networks into the same analog conversation
  (and send Sam's analog audio out both at once). Same discipline as any
  two links; v1 has no interlock (see Risks).

### Dashboard control (the "M17 panel")

The dashboard's M17 button opens an M17 panel instead of switching
DVSwitch modes. The panel shows and controls the whole M17 side:

- **Status:** service up/down, current reflector + module, whether 1998
  is linked to 625730.
- **Reflector picker:** the full M17 reflector list (~126 reflectors)
  from the same DVRef registry the dashboard already fetches for its
  other lists, plus a module selector (A–Z).
- **Switch / Connect:** applies the chosen reflector + module.
- **Disconnect:** drops the reflector connection (stops the bridge).
- **Link / Unlink 1998:** connects or disconnects the pseudo-node to
  625730 from the same panel (Asterisk CLI under the hood; exact command
  form verified against ASL3 during the build).

How a switch works, honestly: USRP2M17 has **no runtime control
channel** — it reads its ini once at startup. So a switch is a small
privileged helper (`m17-switch.sh`, same pattern as the existing
`mode-switch.sh` / `gain-set.sh`) that rewrites the reflector name +
address in `/etc/USRP2M17.ini`, restarts the service, and waits for the
log to show **"Received ACKN from reflector"** before reporting success
— no fake "ok" states; the panel shows the truth or an error. A switch
takes a few seconds. Two things make that painless:

- The 1998 ↔ 625730 link is Asterisk-side and **stays up through a
  switch** — only the M17 leg cycles, so Sam never re-links to change
  rooms.
- The ini remains the single source of truth: the dashboard edits the
  same file a manual change would, so after a reboot the bridge comes
  back on whatever reflector was last selected.

Safety shape, mirroring the existing helpers: the browser never supplies
an address. It sends a reflector name + module letter; the helper
validates the name format, resolves the host itself from the node's
DVRef/M17Hosts registry data, and only then edits the ini (with a
timestamped backup) and restarts the service. www-data's sudoers grant
covers exactly this one helper.

## 4. Configuration (defaults chosen; all are one-line changes)

From the author's sample ini, with Sam's values filled in:

```ini
[M17 Network]
Callsign=KF0RIZ A
Address=<M17-M17 reflector host>   ; hostname OK, DNS-resolved
Name=M17-M17 A
LocalPort=32012
DstPort=17000
GainAdjustdB=3
Daemon=0
Debug=0

[USRP Network]
Address=127.0.0.1
DstPort=32002
LocalPort=34002
GainAdjustdB=-6
Debug=0

[Log]
DisplayLevel=1
FileLevel=1
FilePath=/var/log/usrp2m17
FileRoot=USRP2M17
```

Decisions baked into those numbers:

- **Reflector: M17-M17, module A** — the flagship M17 reflector/room.
  The exact host address gets pinned at build time from the DVRef M17
  host data (the same registry the dashboard already pulls its reflector
  lists from; ~126 reflectors).
- **Ports 34002 / 32002** for the USRP pair — mirrors 1999's 34001/32001
  and collides with nothing in the current repo configs.
- **LocalPort 32012, not the sample's 32010.** The author's sample uses
  32010, which on Sam's node is already the P25 gateway leg (32010/32011
  are the P25 pair in MMDVM_Bridge.ini). 32012 is unused in the repo
  configs. All three ports get re-verified against the live node
  (`ss -ulnp`) before install.
- **Gains at the author's defaults** (+3 dB M17 side, −6 dB USRP side —
  his stated trial-and-error balance). Tunable in the ini if levels are
  off on the first test.
- **Daemon=0 with a systemd `Type=simple` unit**, rather than letting it
  self-daemonize — systemd keeps supervision and logging.
- Log directory `/var/log/usrp2m17`. Logs are small; rotation is a
  non-issue for v1.

Callsign suffix — resolved from source during the build: the CONN
packet's module byte is read from the **Name** field (the module you
join), while the `Callsign` string is the bridge's own source identity,
encoded whole. The template therefore uses `KF0RIZ D` (the author's
sample uses the same "D" suffix convention) and `Name=M17-M17 A` carries
the module that matters. A related detail: voice streams originating
from the USRP side get their source suffix forced to "D" by the code,
so "D" is this program's bridge identity — consistent, and cosmetic.

## 5. What gets built (after this doc is approved)

All in `allstar-dmr/m17/` in Beerssam/Projects:

| File | Purpose |
| --- | --- |
| `DESIGN.md` | This document |
| `USRP2M17.ini` | Config template with the values in §4 |
| `build-usrp2m17.sh` | Clones MMDVM_CM, applies the `<cstdint>` patches idempotently, builds, installs the binary to `/usr/local/bin`. Mirrors `build-dmrgateway.sh` norms |
| `usrp2m17.service` | systemd unit (Type=simple, Restart=on-failure, enabled at boot) |
| `install-m17.sh` | Node-side install: backups first, verifies the node matches expectations and stops on mismatch, installs ini + unit, adds node 1998 to rpt.conf (refuses if 1998 already exists), restarts Asterisk, ends with a liveness check (service active + `ACKN` from the reflector in the log) |
| `../dashboard/m17-switch.sh` | Privileged dashboard helper (§3), kept with the other helpers: validates reflector + module (against the registry's module list), resolves the host server-side, backs up and edits the ini, restarts usrp2m17, verifies `ACKN` (fails fast on `NACK`), reports real success/failure |
| Dashboard changes | `dvswitch-control.sh`: new `?action=m17` endpoint + an `m17` block and `usrp2m17` service in status. `dvswitch-control.html`: M17 button opens the M17 panel (status, reflector picker, module, switch/disconnect, link/unlink, start bridge); SERVICES card gains M17 Reflector + USRP2M17 rows. `install.sh`: installs `m17-switch.sh` and its sudoers line alongside the existing helpers |

## 6. Node changes at install time (preview)

The install will come with its own enumerated change list and go-ahead,
per house rules. For review purposes, the full footprint is:

1. `/etc/asterisk/rpt.conf`: one new `[1998]` stanza (inherits
   `(node-main)`, `duplex = 0`, `rxchannel = USRP/127.0.0.1:34002:32002`)
   and one `[nodes]` line (`1998 = radio@127.0.0.1/1998,NONE`).
   Backup taken first.
2. New files only: `/usr/local/bin/USRP2M17`, `/etc/USRP2M17.ini`,
   `/etc/systemd/system/usrp2m17.service`, `/var/log/usrp2m17/`.
3. Restarts: Asterisk once (momentary link drop — 1999 and the hub link
   re-establish per Sam's existing auto-connect behavior), the new
   usrp2m17 service starts, and Apache reloads for the dashboard update.
4. One new sudoers line (www-data → `m17-switch.sh` only), added by the
   dashboard's install.sh next to the existing helper grants.
5. Nothing else is modified. No DVSwitch config is touched; the only
   dashboard behavior that changes is the M17 button/panel.

Rollback: stop/disable usrp2m17, restore the rpt.conf backup, restart
Asterisk. Or the zero-residual version: just don't link 1998 — an
unlinked, stopped bridge is inert.

## 7. Test plan (acceptance)

1. Service starts on the node; log shows CONN sent and **"Received ACKN
   from reflector"**.
2. Link 1998 → 625730. Key up on analog; confirm the transmission lands
   on the reflector (second ear: DroidStar on Sam's phone, or a WPSD
   hotspot in M17 mode watching the same reflector/module).
3. Reverse path: transmit into the reflector from the second ear; confirm
   clean audio out of the analog side.
4. Audio levels both directions judged by ear; adjust `GainAdjustdB`
   values if needed.
5. Soak: connection survives keepalive indefinitely; kill/restart the
   service and confirm auto-reconnect.
6. Nightly-reboot behavior: the unit is enabled, so after the node's
   designed nightly reboots USRP2M17 returns and reconnects on its own —
   to the last reflector the dashboard selected, since that lives in the
   ini. The 1998 *link* does not auto-reconnect — same as 1999 today.
   Acceptable for v1.
7. Dashboard switching: with 1998 linked, switch from M17-M17 A to a
   second reflector + module from the panel. Panel must show the new
   reflector, the log must show its `ACKN`, audio must still flow, and
   the 1998 link must never have dropped. Switch back. Exercise
   Disconnect and Connect from the panel as well.

## 8. Risks and honest unknowns

- **Upstream maintenance:** USRP2M17 is a small community tool, not a
  packaged product. The source is self-contained (bundled Codec2), so the
  worst case is we maintain our clone — the same position we're already
  in with the patched DMRGateway.
- **Reflector host data changes:** reflector hosts move occasionally.
  The ini holds one hostname; if M17-M17 moves, it's a one-line fix.
  (DVRef data is the reference when that happens.)
- **No link interlock:** linking 1998 and 1999 simultaneously would mix
  M17 and DVSwitch audio into one conversation. Operator discipline for
  v1; a dashboard or DTMF-layer interlock is a possible v2.
- **Audio quality expectations:** Codec2 at 3200 bps sounds like what it
  is — intelligible, openly-implemented digital voice, not FM and not
  AMBE. The gain defaults are the author's; final judgment is Sam's ear
  on the acceptance test.
- **Switching is restart-based:** because USRP2M17 has no runtime
  control channel, each reflector switch restarts the service — a few
  seconds where the M17 leg is down (the AllStar link itself stays up).
  There is no way around this without patching USRP2M17 itself, which
  v1 deliberately avoids.
- **Dashboard trust boundary:** the panel's helper is one more
  www-data-reachable privileged script. It is kept to the established
  helper pattern: fixed-purpose, strict input validation, reflector
  addresses resolved on the node from registry data (never taken from
  the request), ini backup before every edit.

## 9. Effort

- Build package (scripts, ini, unit, dashboard panel + helper): one
  working session on Muse's side, fixture-tested against Sam's current
  configs from the repo backups before anything is pushed.
- Node install: ~10 minutes plus the Asterisk restart.
- On-air acceptance test: needs Sam at the radio with a second M17 ear
  (phone app or WPSD hotspot).

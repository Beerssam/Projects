# BrandMeister DMR Login Failure — Research Report

**Date:** 2026-10-18 (overnight research)
**Node:** AllStar ASL3, DMRGateway custom build (RPTL + scan-rewrite + private-call patches)
**Symptom:** `BM_3103, Login to the master has failed, retrying network...` every ~10s.
Identical failure on 3102. TGIF and KS-DMR work through the same binary.
**BM self-care device log:** 320968604 shows "authentication failed (incorrect password)".

---

## 1. How BrandMeister Hotspot Auth Works (verified against DMRGateway source)

Source: `g4klx/DMRGateway` master branch, `DMRNetwork.cpp` / `Conf.cpp`
(now maintained by Adrian Musceac YO8RZZ; auth core unchanged from G4KLX).

The upstream link uses the **Homebrew repeater protocol** (same as MMDVMHost):

| Step | Direction | Packet | Meaning |
|------|-----------|--------|---------|
| 1 | GW → Master | `RPTL` + 4-byte ID (big-endian) | Login request |
| 2 | Master → GW | `RPTACK` + 4-byte salt | Login accepted, here is the salt |
| 3 | GW → Master | `RPTK` + 4-byte ID + `SHA256(salt \|\| password)` (32 bytes) | Authorisation |
| 4 | Master → GW | `RPTACK` | Password accepted |
| 5 | GW → Master | `RPTC` + config block | Send config |
| 6 | Master → GW | `RPTACK` | `Logged into the master successfully` → RUNNING |

A `MSTNAK` from the master at each stage means something different
(this is explicit in the current source comments, `DMRNetwork.cpp:62-92`):

- NAK while `WAITING_LOGIN` → **"login"**: ID not recognised / not permitted
- NAK while `WAITING_AUTHORISATION` → **"auth"**: **wrong password** —
  "by far the most common real-world support issue"
- NAK while `WAITING_CONFIG` → **"config"**: master rejected declared config
  (e.g. this ID is already connected elsewhere)
- No response at all → **"timeout"**: host/port unreachable, not credentials

**Password handling (verified in `Conf.cpp:326-354`):**
DMRGateway's ini parser **strips surrounding double quotes** from every value:
```cpp
// Remove quotes from the value
if (len > 1U && *value == '"' && value[len - 1U] == '"') { ... strip ... }
```
So `Password="<redacted>"` is sent as `<redacted>`. **Quotes are definitively
not the issue** (Sam was right about this, and the source confirms it).

The password is hashed as `SHA256(4-byte salt || password bytes)` — no
trailing whitespace is added by DMRGateway (the parser also trims trailing
spaces/tabs on unquoted values).

---

## 2. What the Evidence Actually Shows

1. **This is an AUTH-stage failure, not a login-stage failure.** BM's device
   log says "authentication failed (incorrect password)" for 320968604. That
   means: RPTL accepted → RPTACK+salt received → RPTK sent → **hash mismatch**.
   The ID is recognised; the password hash does not match what BM has stored.

2. **"TGIF works" is NOT evidence the password/auth path is correct.**
   Verified via n6jet.com (crawled 2026-10-17): *"Unlike BrandMeister, TGIF
   does not require it. The shared password still connects."* TGIF is lenient
   about hotspot passwords. A broken RPTK computation or a wrong password
   would still connect to TGIF while BM strictly rejects it.

3. **The 3 custom patches are unlikely culprits but cannot be fully exonerated
   by "TGIF works".** The patches touch the local MMDVM side and the data
   path, not `CDMRNetwork::writeAuthorisation()`. But since TGIF doesn't
   validate, only a test against a strict master (BM) or a vanilla build can
   truly rule them out.

4. **Network path is fine.** Ping to masters works (44ms), and BM's device log
   shows the auth *attempt* — packets reach BM and BM responds. Not a
   firewall/DNS/port issue.

5. **ESSID format is fine.** 320968604 = base ID 3209686 + ESSID 04, standard
   9-digit format. BM's device log references this exact ID, so BM parsed it.

---

## 3. Ranked Likely Causes (most → least likely)

### #1 — The hotspot password stored in BrandMeister self-care ≠ "<redacted>"
**Most likely by a wide margin.** The DMRGateway source comments call wrong
password "by far the most common real-world support issue," and every
hotspot error-message reference (n6jet.com, openSPOT3 manual, forums) says
the same for exactly this symptom.

How this happens even when Sam "confirmed" the password:
- The **"Hotspot Security" checkbox** in BM self-care must be **checked**,
  the password entered, **and Save clicked**. Viewing the page is not enough.
  If the box was never checked/saved, BM has no (or an old) password stored.
- Sam may have confirmed his **account** password rather than the separate
  **hotspot** password field.
- A copy/paste into self-care may have included a trailing space (invisible
  in the browser); DMRGateway sends it without.
- A previous password change may not have propagated (rare, but reported).

### #2 — The running DMRGateway is reading a different DMRGateway.ini
There is direct precedent on this node (Oct 13): the `dmrgateway` systemd
unit's `ExecStart` pointed at `/etc/dmrgateway/DMRGateway.ini` while configs
were installed to `/opt/DMRGateway/DMRGateway.ini`. If Sam verified the
password with `cat -A` on one file but the service reads another, the
running gateway could be sending a stale/different password. TGIF working
doesn't rule this out if both files happen to have the right TGIF password
(or TGIF doesn't care).

### #3 — A custom-build patch broke upstream RPTK computation
Unlikely (patches are local-side/data-path), but "TGIF works" cannot exonerate
them because TGIF doesn't validate. A vanilla-build test settles it
definitively (see Tests).

### #4 — Stale session or ESSID conflict on BM's side
If another device/session is holding 320968604, or a hung session exists,
BM can behave oddly. Usually this manifests as config-stage rejection, but
it's worth checking the self-care device list for duplicates.

### #5 — BM account-level issue
Account not validated, callsign issue, etc. Unlikely given the specific
"incorrect password" message rather than an account error.

### Ruled out
- **Quotes in the ini** — stripped by the parser (source-verified).
- **Special characters/whitespace in the sent password** — `cat -A` clean.
- **ESSID pre-registration** — BM auto-recognises ESSIDs (Sam correct).
- **One vs many passwords** — account-wide hotspot password (Sam correct).
- **Master-specific outage** — 3102 and 3103 fail identically.
- **Network/firewall** — BM logs the attempt; ping fine.
- **DMRGateway version vs BM protocol change** — no 2025/2026 BM auth
  changes found; Homebrew RPTL/RPTK/SHA256 is stable and widely used.

---

## 4. Specific Tests (in order)

1. **Confirm which ini file the live service reads:**
   ```
   sudo systemctl cat dmrgateway | grep -E "ExecStart="
   sudo grep -A2 '^\[DMR Network 1\]' <that-file> | grep -i password | cat -A
   ```
   If the password differs from what Sam checked, that's the bug.

2. **Confirm the failure stage with Debug:**
   Add `Debug=1` under `[DMR Network 1]`, `sudo systemctl restart dmrgateway`,
   then watch `journalctl -u dmrgateway`. Expect to see:
   `Sending authorisation` (RPTACK received = login OK) followed by
   `Login to the master has failed` (MSTNAK to RPTK = auth failed).
   If instead there is no `Sending authorisation`, it's a login-stage (ID)
   problem, not password.

3. **Re-save the hotspot password in BM self-care:**
   brandmeister.network → SelfCare → check **Hotspot Security** is enabled →
   re-type the password → **Save** → wait 2 minutes →
   `sudo systemctl restart dmrgateway`. (Eliminates "viewed but not saved".)

4. **Set a brand-new hotspot password** (e.g. `bm1996KF0`), save in self-care,
   put the identical string in `[DMR Network 1]` Password, restart. Eliminates
   all doubt about what's stored vs what's sent.

5. **Vanilla-build test (definitive patch exoneration):**
   Build stock g4klx/DMRGateway without the 3 patches, point a test
   `[DMR Network 1]` at BM. If vanilla also fails → password/account issue,
   patches innocent. If vanilla works → a patch broke `writeAuthorisation`.

6. **Check self-care device list** for duplicate or stale 320968604 entries;
   remove any stale ones.

---

## 5. Config Changes to Try

**None on the node.** The `[DMR Network 1]` config is correct per source
analysis (address, port 62031, ID 320968604, password format). Do not change
the node config until the self-care side is re-verified — the evidence points
at BM's stored password, not the node.

If all self-care steps fail, the fallback is test #5 (vanilla build), and if
that also fails, contact BM support with the device-log timestamps showing
"authentication failed (incorrect password)" for 320968604.

---

## Sources
- `g4klx/DMRGateway` master: `DMRNetwork.cpp` (login handshake, MSTNAK
  handling, `writeAuthorisation` SHA256(salt||password)), `Conf.cpp`
  (quote-stripping ini parser) — fetched 2026-10-18
- https://www.n6jet.com/hotspot-error-messages.html — "Login to the master
  has failed… Almost always a wrong hotspot password"
- https://www.n6jet.com/hotspot-security.html — "Unlike BrandMeister, TGIF
  does not require it. The shared password still connects."
- http://manuals.sharkrf.com/openspot3/en/homebrew-mmdvm-connector.html —
  auth-failed → turn off Hotspot Security or use the hotspot password
- BrandMeister hotspot-security rollout docs (Sept 2021, hamdigitaal.nl /
  minnesotadmr.com) — personalized hotspot password required since then

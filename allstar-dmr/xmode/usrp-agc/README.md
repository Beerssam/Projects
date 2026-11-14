# usrp-agc

A tiny USRP pass-through that adds automatic gain control + a peak
limiter to the USRP (PCM) hops where Analog_Bridge has no AGC —
above all the **analog -> digital** direction on the main chain
(Asterisk -> Analog_Bridge), which is the path behind the node's
analog-side TX distortion reports.

* `usrp_agc.py` — the daemon (Python 3 stdlib only, negligible CPU).
  Processes **only** USRP type-0 voice payloads; every other packet,
  and every header, is forwarded byte-identical. AGC: per-frame RMS,
  -20 dBFS target, +24/-6 dB range, 5 ms attack / 200 ms release
  smoothing, -50 dBFS silence gate (gain freezes on noise), -3 dBFS
  peak limiter last.
* Bypass: if the instance's state file (`/run/usrp-agc/<name>.state`)
  contains `bypass`, everything passes byte-identical. The dashboard
  Bridge/Audio controls write that file — one tap back to the raw
  path, and all manual AB gain sliders keep working exactly as before.
* `usrp-agc-main.ini` — the main-chain instance config.
* The **bridge** instance (`usrp-agc@bridge`) has no static config:
  xmode-switch.sh generates `/opt/xmode/usrp-agc/bridge.ini` when a
  bridge starts (the two legs' home ports differ per pairing), with
  AGC on both directions and its state file at
  `/run/usrp-agc/bridge.state`.
* `usrp-agc@.service` — systemd template unit (`usrp-agc@main`,
  `usrp-agc@bridge`).

Verified locally with synthetic USRP packets: quiet sine leveled to
the target RMS exactly, loud sine reduced with peaks under the
limiter ceiling, silence leaves the gain frozen, below-gate signals
are not pumped, DTMF/text/short/non-USRP packets are byte-identical,
bypass is byte-identical, and headers survive untouched.

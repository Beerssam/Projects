#!/usr/bin/env python3
"""usrp_agc.py -- USRP pass-through with AGC + limiter.

Sits between two USRP endpoints (e.g. Asterisk <-> Analog_Bridge, or an
AllStar leg node <-> a leg Analog_Bridge) and levels the voice audio in
the configured direction(s). Built for the KF0RIZ node because
Analog_Bridge's built-in AGC (AUDIO_USE_AGC) exists only on its USRP
side; the analog -> digital direction has no AGC anywhere in the
DVSwitch stack. This shim covers that direction.

USRP packet (public protocol, see DVSwitch chan_usrp.h):
  32-byte header: "USRP" + 7 big-endian u32 (seq, memory, keyup,
  talkgroup, type, mpxid, reserved); type 0 = voice, 1 = DTMF, 2 = text.
  Voice payload: int16 little-endian PCM, 8 kHz, normally 160 samples.

Rules the shim lives by:
  * ONLY type-0 voice payloads are ever modified. Every other packet —
    and every header, always — is forwarded byte-identical.
  * AGC is per-frame RMS based with smoothed gain (attack/release), a
    silence gate (gain freezes on quiet frames instead of pumping
    noise up), and a hard peak limiter as the final stage.
  * Bypass: when the state file says "bypass", ALL packets pass
    byte-identical. The dashboard toggles the state file; the shim
    notices within a second. Manual gains elsewhere are untouched.

Usage: usrp_agc.py <config.ini>
Config:
  [shim]
  listen_a / send_a   UDP port pair for side A (listen on, send back to)
  listen_b / send_b   same for side B
  agc_a_to_b = on|off process voice A -> B
  agc_b_to_a = on|off process voice B -> A
  state_file = /run/usrp-agc-main/state   (contains "on" or "bypass")
  [agc]
  target_dbfs_rms, max_gain_db, min_gain_db, ceiling_dbfs_peak,
  gate_dbfs_rms, attack_ms, release_ms
"""

import array
import configparser
import math
import os
import select
import socket
import sys
import time

HEADER_LEN = 32
TYPE_VOICE = 0
FULL_SCALE = 32768.0


def db_to_lin(db):
    return 10.0 ** (db / 20.0)


class Agc:
    """One direction's AGC state: a smoothed linear gain + limiter."""

    def __init__(self, cfg):
        self.target_rms = db_to_lin(cfg.getfloat("target_dbfs_rms", -20.0)) * FULL_SCALE
        self.max_gain = db_to_lin(cfg.getfloat("max_gain_db", 24.0))
        self.min_gain = db_to_lin(cfg.getfloat("min_gain_db", -6.0))
        self.ceiling = db_to_lin(cfg.getfloat("ceiling_dbfs_peak", -3.0)) * FULL_SCALE
        self.gate_rms = db_to_lin(cfg.getfloat("gate_dbfs_rms", -50.0)) * FULL_SCALE
        attack_ms = cfg.getfloat("attack_ms", 5.0)
        release_ms = cfg.getfloat("release_ms", 200.0)
        # Per 20 ms frame smoothing factors from the time constants.
        self.alpha_attack = 1.0 - math.exp(-20.0 / max(attack_ms, 1.0))
        self.alpha_release = 1.0 - math.exp(-20.0 / max(release_ms, 1.0))
        self.gain = 1.0

    def process(self, samples):
        """samples: array('h') modified in place."""
        if not samples:
            return
        sq = 0.0
        peak = 0
        for s in samples:
            sq += s * s
            a = -s if s < 0 else s
            if a > peak:
                peak = a
        rms = math.sqrt(sq / len(samples))
        if rms >= self.gate_rms:
            desired = self.target_rms / rms if rms > 0 else self.gain
            desired = min(max(desired, self.min_gain), self.max_gain)
            alpha = self.alpha_attack if desired < self.gain else self.alpha_release
            self.gain += (desired - self.gain) * alpha
        g = self.gain
        # Apply gain, tracking the new peak for the limiter.
        new_peak = 0.0
        out = array.array("h", samples)
        for i, s in enumerate(samples):
            v = s * g
            av = -v if v < 0 else v
            if av > new_peak:
                new_peak = av
            out[i] = int(max(-32768.0, min(32767.0, v)))
        if new_peak > self.ceiling and new_peak > 0:
            scale = self.ceiling / new_peak
            for i, s in enumerate(out):
                out[i] = int(s * scale)
        samples[:] = out


def process_packet(data, agc):
    """Return the packet to forward. Only voice payloads are processed;
    the 32-byte header is always preserved byte-for-byte."""
    if len(data) <= HEADER_LEN or not data.startswith(b"USRP"):
        return data
    ptype = int.from_bytes(data[20:24], "big")
    if ptype != TYPE_VOICE:
        return data
    payload = data[HEADER_LEN:]
    if len(payload) % 2:
        return data
    samples = array.array("h")
    samples.frombytes(payload)
    if sys.byteorder == "big":
        samples.byteswap()
    agc.process(samples)
    if sys.byteorder == "big":
        samples.byteswap()
    return data[:HEADER_LEN] + samples.tobytes()


class Direction:
    def __init__(self, name, enabled, agc_cfg):
        self.name = name
        self.enabled = enabled
        self.agc = Agc(agc_cfg)
        self.packets = 0
        self.processed = 0

    def forward(self, data, bypass):
        self.packets += 1
        if bypass or not self.enabled:
            return data
        out = process_packet(data, self.agc)
        if out != data:
            self.processed += 1
        return out


def load_config(path):
    cfg = configparser.ConfigParser()
    with open(path) as f:
        cfg.read_file(f)
    return cfg


def main(argv):
    if len(argv) != 2:
        print("usage: usrp_agc.py <config.ini>", file=sys.stderr)
        return 2
    cfg = load_config(argv[1])
    for section in ("shim", "agc"):
        if not cfg.has_section(section):
            cfg.add_section(section)
    shim = cfg["shim"]
    agc_cfg = cfg["agc"]

    def port(key):
        return int(shim.get(key))

    state_file = shim.get("state_file", "").strip()
    a_to_b = Direction("a->b", shim.get("agc_a_to_b", "on").lower() == "on", agc_cfg)
    b_to_a = Direction("b->a", shim.get("agc_b_to_a", "off").lower() == "on", agc_cfg)

    sock_a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_a.bind(("127.0.0.1", port("listen_a")))
    sock_b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_b.bind(("127.0.0.1", port("listen_b")))
    dest_a = ("127.0.0.1", port("send_a"))
    dest_b = ("127.0.0.1", port("send_b"))

    print(f"usrp-agc: A listen {port('listen_a')} -> B {dest_b[1]}; "
          f"B listen {port('listen_b')} -> A {dest_a[1]}; "
          f"agc a->b {'on' if a_to_b.enabled else 'off'}, "
          f"b->a {'on' if b_to_a.enabled else 'off'}", flush=True)

    bypass = False
    state_mtime = None
    last_state_check = 0.0

    def current_bypass(now):
        nonlocal bypass, state_mtime, last_state_check
        if not state_file or now - last_state_check < 1.0:
            return bypass
        last_state_check = now
        try:
            m = os.stat(state_file).st_mtime
        except OSError:
            return bypass
        if m == state_mtime:
            return bypass
        state_mtime = m
        try:
            with open(state_file) as f:
                value = f.read().strip().lower()
        except OSError:
            return bypass
        new = value == "bypass"
        if new != bypass:
            print(f"usrp-agc: bypass {'ON' if new else 'OFF'} (state file)", flush=True)
        bypass = new
        return bypass

    while True:
        readable, _, _ = select.select([sock_a, sock_b], [], [], 0.5)
        now = time.monotonic()
        bp = current_bypass(now)
        for sock in readable:
            data, _ = sock.recvfrom(65535)
            if sock is sock_a:
                sock_b.sendto(a_to_b.forward(data, bp), dest_b)
            else:
                sock_a.sendto(b_to_a.forward(data, bp), dest_a)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

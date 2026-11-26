#!/usr/bin/env python3
"""patch_hub_whisper_small.py - AI hub: step the Whisper gate
model large-v3-turbo -> small.en for speed (Nov 25 2026)

Turbo's accuracy is real (near-perfect gate transcripts all
evening) but its cost is the whole user experience: measured
live Nov 25, the gate takes ~36-45 s per clip (36.0 s standalone
load test; the 19:49 Price Chopper question ran ~52 s from
unkey to answer-start, of which everything after the gate --
search 0.8 s, deepening 0.7 s, Gemini 3.0 s, Piper 1.8 s --
sums to ~6 s). Sam's call: swap to the middle version.

The ladder by English word-error rate: tiny ~7.6% -> base ~5.0%
-> small ~3.4% -> turbo ~2.5%. small.en gives up a little
accuracy vs turbo but should transcribe in a fraction of the
time, and it is still clearly better than the base.en whose
garbles ('Retaw', 'Raydown') poisoned searches this morning.
English-only variant: all hub traffic is English and .en
models transcribe English more accurately than the multilingual
build at the same size.

Same shape as the previous two Whisper swaps: download
ggml-small.en.bin (~466 MB) into /opt/whisper.cpp/models/,
verify BEFORE any code change (size floor 300 MB + ggml magic,
stored little-endian as 'lmgg'), then swap the one model
filename in /home/asl/stt_script.py (currently
ggml-large-v3-turbo.bin). After the swap, test-transcribe the
newest monitor clip (timed, so the new gate cost is visible)
and require a non-empty transcript; on ANY failure restore the
backup, leaving turbo live, and abort. Turbo and base.en stay
on disk either way; rollback is copying the backup back.

Restart ai_orchestrator afterwards (stt_script is imported
per-call inside whisper_gate but the module is cached after
first import).

Run with:  sudo python3 patch_hub_whisper_small.py
Then:      sudo systemctl restart ai_orchestrator
Rollback: copy the backup back over stt_script.py and restart.
"""
import glob
import os
import shutil
import subprocess
import sys
import time

SCRIPT = "/home/asl/stt_script.py"
MODELS = "/opt/whisper.cpp/models"
NEW_MODEL = "ggml-small.en.bin"
OLD_MODEL = "ggml-large-v3-turbo.bin"
URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/" + NEW_MODEL
CLI = "/opt/whisper.cpp/build/bin/whisper-cli"
MONITOR = "/var/spool/asterisk/monitor/625731"

dest = os.path.join(MODELS, NEW_MODEL)

# --- 1. Download (skip if a verified copy is already there) ---
def verified(path):
    try:
        if os.path.getsize(path) < 300_000_000:
            return False
        with open(path, "rb") as f:
            return f.read(4) in (b"lmgg", b"ggml")
    except OSError:
        return False

if not verified(dest):
    if os.path.exists(dest):
        os.remove(dest)
    print(f"Downloading {NEW_MODEL} (about 466 MB)...")
    r = subprocess.run(["curl", "-L", "-o", dest, URL], timeout=1800)
    if r.returncode != 0 or not verified(dest):
        print("ABORT: download did not verify (size/magic). No changes made.")
        if os.path.exists(dest):
            os.remove(dest)
        sys.exit(1)
print(f"Model verified ({os.path.getsize(dest)} bytes).")

# --- 2. Swap the filename in stt_script.py ---
with open(SCRIPT) as f:
    src = f.read()
n = src.count(OLD_MODEL)
if n != 1:
    print(f"ABORT: '{OLD_MODEL}' found {n} times in stt_script.py (need exactly 1). No changes made.")
    sys.exit(1)
backup = f"{SCRIPT}.bak-{time.strftime('%Y%m%d-%H%M%S')}-whispersmall"
shutil.copy2(SCRIPT, backup)
with open(SCRIPT, "w") as f:
    f.write(src.replace(OLD_MODEL, NEW_MODEL))
print(f"Swapped {OLD_MODEL} -> {NEW_MODEL}. Backup: {backup}")

# --- 3. Prove the new model loads: transcribe the newest
# monitor clip and require non-empty output. ---
clips = sorted(glob.glob(os.path.join(MONITOR, "*.wav")), key=os.path.getmtime)
if clips:
    clip = clips[-1]
    t0 = time.time()
    try:
        r = subprocess.run([CLI, "-m", dest, "-f", clip, "-nt"],
                           capture_output=True, text=True, timeout=300)
        dt = time.time() - t0
        out = (r.stdout or "").strip()
        if r.returncode != 0 or not out:
            raise RuntimeError(f"rc={r.returncode} out={out[:80]!r} err={(r.stderr or '')[:200]!r}")
        print(f"Load test OK in {dt:.1f}s on {os.path.basename(clip)}: {out[:90]!r}")
    except Exception as e:
        print(f"ABORT: small.en load test failed ({e}). Restoring {OLD_MODEL}.")
        shutil.copy2(backup, SCRIPT)
        sys.exit(1)
else:
    print("WARNING: no monitor clips found for a load test; swap kept unverified.")

print("PATCH OK. Now restart: sudo systemctl restart ai_orchestrator")

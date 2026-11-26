#!/usr/bin/env python3
"""patch_hub_whisper_turbo.py - AI hub: upgrade the Whisper gate
model base.en -> large-v3-turbo (Nov 25 2026)

Sam's call, Nov 25 (voice): he originally kept the hub's models
small out of caution about compute; the hub Pi 5 is in fact
coasting, and he asked for whichever Whisper is best and still
free, best-and-quick preferred. All Whisper models are free
(open weights). The ladder by English word-error rate:
tiny ~7.6% -> base ~5.0% -> small ~3.4% -> medium ~2.9% ->
large-v3 ~2.4% -> large-v3-turbo ~2.5% at roughly 8x large's
speed (809M params, 4 decoder layers). Turbo is the
best-and-quick point: near-large accuracy without large's lag.
The gate transcript drives echo drops, the search gates, and
the SearXNG query wording, so gate accuracy pays off in search
quality (the Walmart query lost its street names in base.en's
read).

Same shape as the tiny -> base.en upgrade
(patch_hub_whisper_base.py): download ggml-large-v3-turbo.bin
(1.5 GiB) into /opt/whisper.cpp/models/, verify BEFORE any code
change (size floor 1 GB + ggml magic, stored little-endian as
'lmgg'), then swap the one model filename in
/home/asl/stt_script.py (currently ggml-base.en.bin).

Extra safety vs the base upgrade: turbo support needs a
whisper.cpp build new enough to load it. After the swap, the
patch test-transcribes the newest monitor clip with the new
model (timing it, so the gate cost is visible) and requires a
non-empty transcript; on ANY failure it restores the backup,
leaving base.en live, and aborts. base.en and tiny stay on disk
either way.

Restart ai_orchestrator afterwards (stt_script is imported
per-call inside whisper_gate but the module is cached after
first import).

Run with:  sudo python3 patch_hub_whisper_turbo.py
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
NEW_MODEL = "ggml-large-v3-turbo.bin"
OLD_MODEL = "ggml-base.en.bin"
URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/" + NEW_MODEL
CLI = "/opt/whisper.cpp/build/bin/whisper-cli"
MONITOR = "/var/spool/asterisk/monitor/625731"

dest = os.path.join(MODELS, NEW_MODEL)

# --- 1. Download (skip if a verified copy is already there) ---
def verified(path):
    try:
        if os.path.getsize(path) < 1_000_000_000:
            return False
        with open(path, "rb") as f:
            return f.read(4) in (b"lmgg", b"ggml")
    except OSError:
        return False

if not verified(dest):
    if os.path.exists(dest):
        os.remove(dest)
    print(f"Downloading {NEW_MODEL} (about 1.5 GiB)...")
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
backup = f"{SCRIPT}.bak-{time.strftime('%Y%m%d-%H%M%S')}-whisperturbo"
shutil.copy2(SCRIPT, backup)
with open(SCRIPT, "w") as f:
    f.write(src.replace(OLD_MODEL, NEW_MODEL))
print(f"Swapped {OLD_MODEL} -> {NEW_MODEL}. Backup: {backup}")

# --- 3. Prove this whisper.cpp build can load turbo: transcribe
# the newest monitor clip and require non-empty output. ---
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
        print(f"ABORT: turbo load test failed ({e}). Restoring {OLD_MODEL}.")
        shutil.copy2(backup, SCRIPT)
        sys.exit(1)
else:
    print("WARNING: no monitor clips found for a load test; swap kept unverified.")

print("PATCH OK. Now restart: sudo systemctl restart ai_orchestrator")

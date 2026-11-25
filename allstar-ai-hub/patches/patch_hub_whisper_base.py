#!/usr/bin/env python3
"""patch_hub_whisper_base.py - AI hub: Whisper gate model tiny -> base
(Nov 25 2026)

The local Whisper gate (stt_script.py, whisper-cli) runs the TINY
model - the smallest and least accurate Whisper model. Its
transcript drives three things: the search-gate trigger words, the
SearXNG search query, and the own-voice echo match. A day of
testing (Nov 25) traced repeated failures to its garbling:
"Raytown" heard as Retaw/Raydown/retail, spelled callsigns mangled,
and echo clips slipping through because one word drifted.

The BASE model (English-only variant - all hub traffic is English,
and the .en models transcribe English more accurately) is the
sweet spot for the Pi 5: much better accuracy, still only a few
seconds per clip. The tiny model file is left in place; rollback
is just pointing the path back.

Order of operations in this script:
  1. Download ggml-base.en.bin (~148 MB, HuggingFace whisper.cpp
     repo) into /opt/whisper.cpp/models/ if it is not already
     there, and verify it (size > 100 MB, ggml magic bytes).
     If the download or verification fails, the script aborts
     with NO code changes - the hub never points at a bad model.
  2. Back up stt_script.py and swap the model filename in the
     whisper-cli invocation (exactly one occurrence required).
  3. Result must py_compile.

Run with:  sudo python3 patch_hub_whisper_base.py
Then:      sudo systemctl restart ai_orchestrator
Rollback: copy the backup back over stt_script.py and restart.
"""
import os
import py_compile
import shutil
import subprocess
import sys
import time

PATH = "/home/asl/stt_script.py"
MODEL_DIR = "/opt/whisper.cpp/models"
NEW_MODEL = "ggml-base.en.bin"
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
MODEL_PATH = os.path.join(MODEL_DIR, NEW_MODEL)

# --- 1. Get the model in place and verified, BEFORE any code change ---
def model_ok(path):
    try:
        if os.path.getsize(path) < 100_000_000:
            return False
        with open(path, "rb") as f:
            return f.read(4) == b"ggml"
    except Exception:
        return False

if model_ok(MODEL_PATH):
    print(f"Model already present and verified: {MODEL_PATH}")
else:
    if os.path.exists(MODEL_PATH):
        os.remove(MODEL_PATH)  # partial/corrupt - fetch a fresh copy
    print(f"Downloading {NEW_MODEL} (~148 MB) ...")
    r = subprocess.run(
        ["curl", "-fL", "--retry", "2", "-o", MODEL_PATH, MODEL_URL],
    )
    if r.returncode != 0 or not model_ok(MODEL_PATH):
        print("ABORT: download failed or model did not verify. No changes made.")
        if os.path.exists(MODEL_PATH):
            os.remove(MODEL_PATH)
        sys.exit(1)
    print(f"Model downloaded and verified ({os.path.getsize(MODEL_PATH)} bytes).")

# --- 2. Swap the model filename in stt_script.py ---
with open(PATH) as f:
    src = f.read()

old = "ggml-tiny.bin"
n = src.count(old)
if n != 1:
    print(f"ABORT: '{old}' found {n} times (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-whisperbase"
shutil.copy2(PATH, backup)
src = src.replace(old, NEW_MODEL)

# Compile in memory BEFORE writing.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")

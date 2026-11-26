#!/usr/bin/env python3
"""patch_hub_whisper_vocab.py - AI hub: give the Whisper gate a
vocabulary hint (initial prompt) - Nov 25 2026

WHY: the gate transcript drives the search query, and small.en
garbles Sam's local vocabulary ('Price Chopper' -> 'press
chopper', Nov 25 20:24). Gemini hears the raw audio itself and
gets it right, but the SEARCH is built from Whisper's words.

whisper-cli supports an initial prompt (--prompt): text the
decoder leans on when the audio is ambiguous. This patch adds
a VOCAB string of Sam's world - local businesses, places,
streets, and radio terms - to the whisper-cli call in
/home/asl/stt_script.py.

WHAT IT IS AND ISN'T: a nudge, not training and not a speed
change (same model, same runtime). It biases close calls
toward words that actually exist in Sam's life. The list is
meant to GROW: when a new garble shows up in the logs, add the
correct term to VOCAB and rerun a future version of this patch
(this one aborts if --prompt is already present).

SAFETY: both anchors must match exactly once or the patch
aborts with no changes; timestamped backup; result must
py_compile. NOTE: if this whisper-cli build rejected the flag,
the gate would return '[STT Error: Whisper]' - the run block
therefore tests stt_script.py directly on a real clip BEFORE
restarting the service, and the rollback is one copy back.

Run with:  sudo python3 patch_hub_whisper_vocab.py
Verify:    sudo python3 /home/asl/stt_script.py "$(ls -t /var/spool/asterisk/monitor/625731/*.wav | head -1)"
           (expect a transcript line, NOT '[STT Error: Whisper]')
Then:      sudo systemctl restart ai_orchestrator
Rollback: copy the backup back over stt_script.py and restart.
"""
import py_compile
import shutil
import sys
import time

PATH = "/home/asl/stt_script.py"

with open(PATH) as f:
    src = f.read()

if "--prompt" in src or "VOCAB" in src:
    print("ABORT: vocabulary prompt already present (patch already applied?). No changes made.")
    sys.exit(1)

old1 = '''import sys, os, subprocess, time'''
new1 = '''import sys, os, subprocess, time
VOCAB = "KF0RIZ amateur radio hub, Shawnee, Kansas. Price Chopper, Walmart Supercenter, Johnson County Library, Shawnee Mission Parkway, 66th Street, 65th Street, Lenexa, Overland Park, Kansas City, Raytown, De Soto, Mission. AllStar Link, talkgroup, repeater, BrandMeister, TGIF, DMR, DVSwitch, YSF, P25, NXDN, M17, D-STAR."'''

old2 = '''    try: return subprocess.check_output(["/opt/whisper.cpp/build/bin/whisper-cli","-m","/opt/whisper.cpp/models/ggml-small.en.bin","-f",t,"-nt"],stderr=subprocess.DEVNULL).decode().strip()'''
new2 = '''    try: return subprocess.check_output(["/opt/whisper.cpp/build/bin/whisper-cli","-m","/opt/whisper.cpp/models/ggml-small.en.bin","-f",t,"-nt","--prompt",VOCAB],stderr=subprocess.DEVNULL).decode().strip()'''

for label, old in (("imports", old1), ("whisper-call", old2)):
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor {label} found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-vocab"
shutil.copy2(PATH, backup)
src = src.replace(old1, new1).replace(old2, new2)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Verify BEFORE restarting:")
print('  sudo python3 /home/asl/stt_script.py "$(ls -t /var/spool/asterisk/monitor/625731/*.wav | head -1)"')
print("Then restart: sudo systemctl restart ai_orchestrator")

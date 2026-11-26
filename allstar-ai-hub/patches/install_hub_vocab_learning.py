#!/usr/bin/env python3
"""install_hub_vocab_learning.py - AI hub self-growing Whisper
vocabulary (Nov 25 2026)

Installs the learning loop Sam approved:
  1. stt_script.py: whisper-cli --prompt now comes from
     /home/asl/ai_vocab.txt, read fresh on EVERY clip (falls back
     to the built-in VOCAB when the file is missing/empty). Works
     whether or not the static patch_hub_whisper_vocab.py was
     applied first - that patch is superseded by this one.
  2. /home/asl/vocab_miner.py: nightly miner. Reads GEMINI's
     transcripts from the orchestrator log (never Whisper's, so
     the gate can't learn its own garbles), counts capitalized
     name-like phrases over a rolling 7 days, promotes any heard
     >= 3 times into ai_vocab.txt alongside the pinned CORE list.
     Capped (40 phrases / 1000 chars) so the prompt - and the
     system - cannot bloat no matter how much Sam talks.
  3. asl's crontab: miner runs nightly at 03:30, logging to
     /home/asl/ai_vocab.log. The miner is also run once NOW to
     seed the file from the existing log.

Safety: stt anchors must match exactly once or the install
aborts before changing anything; timestamped backup of
stt_script.py; both files compile-checked; cron addition is
idempotent; rerunning this installer aborts (guard string).

Run with:  sudo python3 install_hub_vocab_learning.py
Verify:    sudo python3 /home/asl/stt_script.py "$(ls -t /var/spool/asterisk/monitor/625731/*.wav | head -1)"
           (expect a transcript line, NOT '[STT Error: Whisper]')
Then:      sudo systemctl restart ai_orchestrator
Rollback: copy the stt backup back, remove the cron line
(crontab -u asl -e), restart ai_orchestrator.
"""
import os
import py_compile
import shutil
import subprocess
import sys
import time

STT = "/home/asl/stt_script.py"
MINER_PATH = "/home/asl/vocab_miner.py"
VOCAB_FILE = "/home/asl/ai_vocab.txt"
CRON_LINE = "30 3 * * * /usr/bin/python3 /home/asl/vocab_miner.py >> /home/asl/ai_vocab.log 2>&1"

MINER_SRC = '#!/usr/bin/env python3\n# vocab_miner.py - AI hub self-growing Whisper vocabulary (Nov 25 2026)\n#\n# Mines the orchestrator log\'s [RADIO INTERPRETATION] lines - GEMINI\'s\n# transcripts, not Whisper\'s, so the gate never learns its own garbles -\n# for capitalized name-like phrases Sam keeps saying. Phrases heard at\n# least THRESHOLD times in the last WINDOW_DAYS days are promoted into\n# /home/asl/ai_vocab.txt, which stt_script.py reads fresh on every clip\n# as the whisper-cli --prompt. The pinned CORE list always stays.\n#\n# Safety rails: promotion needs repeated identical hearings (one-off\n# Gemini errors never qualify); the auto list is capped by count and\n# total size (Whisper only reads a limited prompt); entries expire out\n# of the rolling window on their own; the file is plain text - inspect\n# or edit it any time. Run nightly from cron; --dry-run prints only.\nimport os\nimport re\nimport sys\nfrom collections import Counter\nfrom datetime import date, timedelta\n\nLOG = "/var/log/ai_orchestrator.log"\nOUT = "/home/asl/ai_vocab.txt"\nWINDOW_DAYS = 7\nTHRESHOLD = 3\nMAX_AUTO = 40\nMAX_CHARS = 1000\n\nCORE = "KF0RIZ amateur radio hub, Shawnee, Kansas. Price Chopper, Walmart Supercenter, Johnson County Library, Shawnee Mission Parkway, 66th Street, 65th Street, Lenexa, Overland Park, Kansas City, Raytown, De Soto, Mission. AllStar Link, talkgroup, repeater, BrandMeister, TGIF, DMR, DVSwitch, YSF, P25, NXDN, M17, D-STAR."\nCORE_WORDS = set(re.findall(r"[a-z0-9]+", CORE.lower()))\n\n# Capitalized often but useless as vocabulary (Whisper knows them).\nSTOP = {\n    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",\n    "sunday", "january", "february", "march", "april", "may", "june",\n    "july", "august", "september", "october", "november", "december",\n    "today", "tomorrow", "yesterday", "please", "thanks", "thank",\n    "yes", "no", "okay", "well", "google",\n}\n# Words that are only capitalized because they start a sentence.\nCOMMON = STOP | {\n    "the", "a", "an", "can", "could", "what", "when", "where", "who",\n    "how", "is", "it", "my", "i", "do", "does", "did", "you", "we",\n    "they", "he", "she", "and", "but", "if", "then", "than", "that",\n    "this", "there", "their", "them", "his", "her", "its", "on", "in",\n    "at", "for", "to", "tell", "give", "find", "look", "looking",\n    "show", "get", "let", "me", "us", "him", "are", "was", "were",\n    "will", "would", "should", "hey", "hi", "hello", "search",\n}\nCONNECTORS = {"of", "the", "and", "&"}\n\nLINE_RE = re.compile(\n    r\'^\\[(\\d{4})-(\\d{2})-(\\d{2}) [\\d:.]+\\] \\[RADIO INTERPRETATION\\] Heard: "(.*)"\\s*$\')\nWORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-\'][A-Za-z0-9]+)*")\n\n\ndef phrases_from(transcript):\n    """Capitalized name-like phrases in one transcript.\n\n    A token is name-like when it starts uppercase and is not a common\n    word that is only capitalized because it starts a sentence. A\n    single-word phrase is kept only when the word appears capitalized\n    mid-sentence - real name evidence.\n    """\n    words = list(WORD_RE.finditer(transcript))\n    tokens = []  # (surface, lower, sentence_start)\n    for i, m in enumerate(words):\n        start = (i == 0)\n        if not start and any(c in transcript[words[i - 1].end():m.start()]\n                             for c in ".!?"):\n            start = True\n        tokens.append((m.group(0), m.group(0).lower(), start))\n\n    def name_like(tok):\n        surface, lower, sstart = tok\n        if not surface[0].isupper() or lower in STOP:\n            return False\n        if sstart and lower in COMMON:\n            return False\n        return True\n\n    found = []\n    i = 0\n    while i < len(tokens):\n        if not name_like(tokens[i]):\n            i += 1\n            continue\n        run = [tokens[i]]\n        j = i + 1\n        while j < len(tokens):\n            if name_like(tokens[j]):\n                run.append(tokens[j])\n                j += 1\n            elif (tokens[j][1] in CONNECTORS and j + 1 < len(tokens)\n                    and name_like(tokens[j + 1])):\n                run.append(tokens[j])\n                j += 1\n            else:\n                break\n        if len(run) > 1 or not run[0][2]:\n            found.append(" ".join(t[0] for t in run))\n        i = j\n    return found\n\n\ndef main():\n    dry = "--dry-run" in sys.argv\n    cutoff = date.today() - timedelta(days=WINDOW_DAYS)\n    counts = Counter()\n    surfaces = {}\n    try:\n        with open(LOG, errors="ignore") as f:\n            lines = f.readlines()\n    except OSError as e:\n        print(f"vocab_miner: cannot read {LOG}: {e}")\n        lines = []\n    for line in lines:\n        m = LINE_RE.match(line)\n        if not m:\n            continue\n        try:\n            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))\n        except ValueError:\n            continue\n        if d < cutoff:\n            continue\n        for ph in phrases_from(m.group(4)):\n            key = ph.lower()\n            counts[key] += 1\n            surfaces.setdefault(key, Counter())[ph] += 1\n\n    promoted = []  # (surface, count)\n    for key, n in counts.most_common():\n        if n < THRESHOLD:\n            continue\n        if all(w in CORE_WORDS for w in key.split()):\n            continue  # already pinned in CORE\n        promoted.append((surfaces[key].most_common(1)[0][0], n))\n    promoted = promoted[:MAX_AUTO]\n\n    def compose(items):\n        if not items:\n            return CORE\n        return CORE + " " + ", ".join(s for s, _ in items) + "."\n\n    text = compose(promoted)\n    while len(text) > MAX_CHARS and promoted:\n        promoted.pop()\n        text = compose(promoted)\n\n    print(f"vocab_miner: window {WINDOW_DAYS}d, threshold {THRESHOLD}, "\n          f"promoted {len(promoted)}: {[s for s, _ in promoted]}")\n    if dry:\n        print("vocab_miner: --dry-run, not writing.")\n        return 0\n    tmp = OUT + ".tmp"\n    with open(tmp, "w") as f:\n        f.write(text + "\\n")\n    os.replace(tmp, OUT)\n    print(f"vocab_miner: wrote {OUT} ({len(text)} chars)")\n    return 0\n\n\nif __name__ == "__main__":\n    sys.exit(main())\n'

CORE = "KF0RIZ amateur radio hub, Shawnee, Kansas. Price Chopper, Walmart Supercenter, Johnson County Library, Shawnee Mission Parkway, 66th Street, 65th Street, Lenexa, Overland Park, Kansas City, Raytown, De Soto, Mission. AllStar Link, talkgroup, repeater, BrandMeister, TGIF, DMR, DVSwitch, YSF, P25, NXDN, M17, D-STAR."

with open(STT) as f:
    src = f.read()

if "ai_vocab.txt" in src:
    print("ABORT: file-based vocabulary already installed. No changes made.")
    sys.exit(1)

IMPORTS = "import sys, os, subprocess, time"
CALL_PLAIN = '    try: return subprocess.check_output(["/opt/whisper.cpp/build/bin/whisper-cli","-m","/opt/whisper.cpp/models/ggml-small.en.bin","-f",t,"-nt"],stderr=subprocess.DEVNULL).decode().strip()'
CALL_VOCAB = '    try: return subprocess.check_output(["/opt/whisper.cpp/build/bin/whisper-cli","-m","/opt/whisper.cpp/models/ggml-small.en.bin","-f",t,"-nt","--prompt",VOCAB],stderr=subprocess.DEVNULL).decode().strip()'
NEW_BLOCK = '''    vocab = VOCAB
    try:
        with open("/home/asl/ai_vocab.txt") as _vf: _v = _vf.read().strip()
        if _v: vocab = _v
    except Exception: pass
    try: return subprocess.check_output(["/opt/whisper.cpp/build/bin/whisper-cli","-m","/opt/whisper.cpp/models/ggml-small.en.bin","-f",t,"-nt","--prompt",vocab],stderr=subprocess.DEVNULL).decode().strip()'''

if src.count(CALL_PLAIN) == 1:
    if "VOCAB" in src:
        print("ABORT: unexpected state (plain call but VOCAB present). No changes made.")
        sys.exit(1)
    if src.count(IMPORTS) != 1:
        print("ABORT: import anchor not unique. No changes made.")
        sys.exit(1)
    new_src = src.replace(IMPORTS, IMPORTS + '\nVOCAB = "' + CORE + '"')
    new_src = new_src.replace(CALL_PLAIN, NEW_BLOCK)
    variant = "original stt_script (static patch not applied)"
elif src.count(CALL_VOCAB) == 1:
    new_src = src.replace(CALL_VOCAB, NEW_BLOCK)
    variant = "static vocab patch already applied (upgrading it)"
else:
    print("ABORT: whisper call line not found exactly once in either known form. No changes made.")
    sys.exit(1)

compile(new_src, STT, "exec")
backup = f"{STT}.bak-{time.strftime('%Y%m%d-%H%M%S')}-vocablearn"
shutil.copy2(STT, backup)
with open(STT, "w") as f:
    f.write(new_src)
py_compile.compile(STT, doraise=True)
print(f"1/4 stt_script.py patched ({variant}). Backup: {backup}")

compile(MINER_SRC, MINER_PATH, "exec")
with open(MINER_PATH, "w") as f:
    f.write(MINER_SRC)
os.chmod(MINER_PATH, 0o755)
py_compile.compile(MINER_PATH, doraise=True)
print(f"2/4 miner written to {MINER_PATH}")

r = subprocess.run(["python3", MINER_PATH], capture_output=True, text=True)
print("3/4 seed run:", (r.stdout or "").strip() or r.stderr.strip())
for p in (VOCAB_FILE, MINER_PATH):
    if os.path.exists(p):
        shutil.chown(p, "asl", "asl")

r = subprocess.run(["crontab", "-u", "asl", "-l"], capture_output=True, text=True)
existing = r.stdout if r.returncode == 0 else ""
if "vocab_miner" in existing:
    print("4/4 cron already present, left as is.")
else:
    new_cron = existing.rstrip("\n") + ("\n" if existing.strip() else "") + CRON_LINE + "\n"
    r = subprocess.run(["crontab", "-u", "asl", "-"], input=new_cron,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("WARNING: cron install failed:", r.stderr.strip(),
              "\nAdd this line manually (crontab -u asl -e):", CRON_LINE)
    else:
        print("4/4 nightly cron added for asl (03:30).")

print("INSTALL OK. Verify BEFORE restarting:")
print('  sudo python3 /home/asl/stt_script.py "$(ls -t /var/spool/asterisk/monitor/625731/*.wav | head -1)"')
print("Then restart: sudo systemctl restart ai_orchestrator")

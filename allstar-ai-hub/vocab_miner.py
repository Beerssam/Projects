#!/usr/bin/env python3
# vocab_miner.py - AI hub self-growing Whisper vocabulary (Nov 25 2026)
#
# Mines the orchestrator log's [RADIO INTERPRETATION] lines - GEMINI's
# transcripts, not Whisper's, so the gate never learns its own garbles -
# for capitalized name-like phrases Sam keeps saying. Phrases heard at
# least THRESHOLD times in the last WINDOW_DAYS days are promoted into
# /home/asl/ai_vocab.txt, which stt_script.py reads fresh on every clip
# as the whisper-cli --prompt. The pinned CORE list always stays.
#
# Safety rails: promotion needs repeated identical hearings (one-off
# Gemini errors never qualify); the auto list is capped by count and
# total size (Whisper only reads a limited prompt); entries expire out
# of the rolling window on their own; the file is plain text - inspect
# or edit it any time. Run nightly from cron; --dry-run prints only.
import os
import re
import sys
from collections import Counter
from datetime import date, timedelta

LOG = "/var/log/ai_orchestrator.log"
OUT = "/home/asl/ai_vocab.txt"
WINDOW_DAYS = 7
THRESHOLD = 3
MAX_AUTO = 40
MAX_CHARS = 1000

CORE = "KF0RIZ amateur radio hub, Shawnee, Kansas. Price Chopper, Walmart Supercenter, Johnson County Library, Shawnee Mission Parkway, 66th Street, 65th Street, Lenexa, Overland Park, Kansas City, Raytown, De Soto, Mission. AllStar Link, talkgroup, repeater, BrandMeister, TGIF, DMR, DVSwitch, YSF, P25, NXDN, M17, D-STAR."
CORE_WORDS = set(re.findall(r"[a-z0-9]+", CORE.lower()))

# Capitalized often but useless as vocabulary (Whisper knows them).
STOP = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "today", "tomorrow", "yesterday", "please", "thanks", "thank",
    "yes", "no", "okay", "well", "google",
}
# Words that are only capitalized because they start a sentence.
COMMON = STOP | {
    "the", "a", "an", "can", "could", "what", "when", "where", "who",
    "how", "is", "it", "my", "i", "do", "does", "did", "you", "we",
    "they", "he", "she", "and", "but", "if", "then", "than", "that",
    "this", "there", "their", "them", "his", "her", "its", "on", "in",
    "at", "for", "to", "tell", "give", "find", "look", "looking",
    "show", "get", "let", "me", "us", "him", "are", "was", "were",
    "will", "would", "should", "hey", "hi", "hello", "search",
}
CONNECTORS = {"of", "the", "and", "&"}

LINE_RE = re.compile(
    r'^\[(\d{4})-(\d{2})-(\d{2}) [\d:.]+\] \[RADIO INTERPRETATION\] Heard: "(.*)"\s*$')
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")


def phrases_from(transcript):
    """Capitalized name-like phrases in one transcript.

    A token is name-like when it starts uppercase and is not a common
    word that is only capitalized because it starts a sentence. A
    single-word phrase is kept only when the word appears capitalized
    mid-sentence - real name evidence.
    """
    words = list(WORD_RE.finditer(transcript))
    tokens = []  # (surface, lower, sentence_start)
    for i, m in enumerate(words):
        start = (i == 0)
        if not start and any(c in transcript[words[i - 1].end():m.start()]
                             for c in ".!?"):
            start = True
        tokens.append((m.group(0), m.group(0).lower(), start))

    def name_like(tok):
        surface, lower, sstart = tok
        if not surface[0].isupper() or lower in STOP:
            return False
        if sstart and lower in COMMON:
            return False
        return True

    found = []
    i = 0
    while i < len(tokens):
        if not name_like(tokens[i]):
            i += 1
            continue
        run = [tokens[i]]
        j = i + 1
        while j < len(tokens):
            if name_like(tokens[j]):
                run.append(tokens[j])
                j += 1
            elif (tokens[j][1] in CONNECTORS and j + 1 < len(tokens)
                    and name_like(tokens[j + 1])):
                run.append(tokens[j])
                j += 1
            else:
                break
        if len(run) > 1 or not run[0][2]:
            found.append(" ".join(t[0] for t in run))
        i = j
    return found


def main():
    dry = "--dry-run" in sys.argv
    cutoff = date.today() - timedelta(days=WINDOW_DAYS)
    counts = Counter()
    surfaces = {}
    try:
        with open(LOG, errors="ignore") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"vocab_miner: cannot read {LOG}: {e}")
        lines = []
    for line in lines:
        m = LINE_RE.match(line)
        if not m:
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if d < cutoff:
            continue
        for ph in phrases_from(m.group(4)):
            key = ph.lower()
            counts[key] += 1
            surfaces.setdefault(key, Counter())[ph] += 1

    promoted = []  # (surface, count)
    for key, n in counts.most_common():
        if n < THRESHOLD:
            continue
        if all(w in CORE_WORDS for w in key.split()):
            continue  # already pinned in CORE
        promoted.append((surfaces[key].most_common(1)[0][0], n))
    promoted = promoted[:MAX_AUTO]

    def compose(items):
        if not items:
            return CORE
        return CORE + " " + ", ".join(s for s, _ in items) + "."

    text = compose(promoted)
    while len(text) > MAX_CHARS and promoted:
        promoted.pop()
        text = compose(promoted)

    print(f"vocab_miner: window {WINDOW_DAYS}d, threshold {THRESHOLD}, "
          f"promoted {len(promoted)}: {[s for s, _ in promoted]}")
    if dry:
        print("vocab_miner: --dry-run, not writing.")
        return 0
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        f.write(text + "\n")
    os.replace(tmp, OUT)
    print(f"vocab_miner: wrote {OUT} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

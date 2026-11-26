#!/usr/bin/env python3
"""patch_hub_fresh_google_date.py - AI hub: two fine-tuning
additions Sam approved Nov 25 2026 ("get as much out of the
gate as we can" while the fine-tuning patches are going on)

1) FRESH-SEARCH NOTE FOR GOOGLE MODE. patch_hub_fresh_search.py
   attaches the discard-the-old-answer note to the SearXNG
   results block - but in Google mode there is no block; the
   grounded search rides inside Gemini. This patch adds a
   standalone _fresh_note, built whenever the gate transcript
   carries 'new search' / 'search again', and appends it to the
   prompt's data segment (the proven f-string that carries
   {adsb_block}{health_block}{ddg_block}), so the instruction
   reaches the model on BOTH search paths. Wording is
   path-neutral: answer from the newest search information;
   where it conflicts with earlier answers, the newest wins.

2) TODAY'S DATE IN THE PROMPT. On Nov 25 the hub, answering a
   'yesterday' news question with no search data, said
   'yesterday, June 20th' - the prompt never tells the model
   what today is. _date_note now carries the hub's local date
   (datetime.now() - the same form the live cascade code uses)
   into the same data segment on EVERY question: "Today's date
   is Wednesday, November 25, 2026. When the user says today,
   yesterday, tonight, or tomorrow, judge it against this
   date."

DEPENDENCY: run AFTER patch_hub_fresh_search.py (this patch
anchors on the _fresh line it adds; it aborts with a clear
message if that patch has not been applied).

Safety: anchors must match exactly once or abort with no
changes; already-applied guard; compiled in memory before
writing; timestamped backup; result must py_compile.

Run with:  sudo python3 patch_hub_fresh_google_date.py
Then:      sudo systemctl restart ai_orchestrator
Rollback: copy the backup back over ai_orchestrator.py and restart.
"""
import py_compile
import shutil
import sys
import time

PATH = "/home/asl/ai_orchestrator.py"

with open(PATH) as f:
    src = f.read()

if "_date_note" in src:
    print("ABORT: fresh-google/date patch already present. No changes made.")
    sys.exit(1)
if "_fresh" not in src:
    print("ABORT: patch_hub_fresh_search.py has not been applied yet - run it first. No changes made.")
    sys.exit(1)

# --- Edit 1: build the note + date strings beside _fresh ---
old_fresh = '''    _fresh = bool(_gate_low) and ("new search" in _gate_low or "search again" in _gate_low)'''
new_fresh = '''    _fresh = bool(_gate_low) and ("new search" in _gate_low or "search again" in _gate_low)
    _fresh_note = ""
    if _fresh:
        _fresh_note = ("NOTE: The user was not satisfied with the previous search and explicitly asked for a NEW search. "
                       "Use the newest search information available for this question; if it conflicts with anything said "
                       "earlier in this conversation, the newest information is correct and the earlier answer was wrong.\\n\\n")
    _today_str = datetime.now().strftime("%A, %B %d, %Y")
    _date_note = ("Today's date is " + _today_str + ". When the user says today, yesterday, tonight, or tomorrow, "
                  "judge it against this date.\\n\\n")'''

# --- Edit 2: append both notes to the prompt's data segment ---
old_seg = '''{adsb_block}{health_block}{ddg_block}'''
new_seg = '''{adsb_block}{health_block}{ddg_block}{_fresh_note}{_date_note}'''

EDITS = [
    ("fresh", old_fresh, new_fresh),
    ("segment", old_seg, new_seg),
]

for name, old, _new in EDITS:
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor '{name}' found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-freshgoogledate"
shutil.copy2(PATH, backup)

for _name, old, new in EDITS:
    src = src.replace(old, new)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")

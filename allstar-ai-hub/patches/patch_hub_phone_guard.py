#!/usr/bin/env python3
"""patch_hub_phone_guard.py - AI hub: phone numbers only from
real search results, never from model memory (Nov 25 2026)

WHY (Nov 25 22:30 YMCA session): Sam's first ask - 'could you
tell me the phone number to the YMCA in Olathe?' - fired NO
search ('phone' is in neither gate word list), and Gemini
answered 913-393-0281 from its own memory. WRONG - the real
Olathe Family YMCA number is 913-393-9622; the invention even
shared the real 913-393 prefix. Later, WITH search results in
hand, Gemini twice declined honestly when the number was not
in the pages, and finally read the correct number off a
deepened page. The honesty rule constrains claims about
search results; nothing constrained memory-sourced specifics.

TWO EDITS:
1. Add "phone" to BOTH search word lists (_search_gate_words
   for the grounded route, _search_words for the SearXNG
   fallback), so a phone-number ask always searches. (Matching
   is by substring: 'telephone'/'phones' also trigger -
   harmless extra searches.)
2. Append a phone rule to the prompt right after the honesty
   sentences: never state a phone number from your own
   knowledge; give one only when it appears in search results
   provided for this question or was already stated earlier
   in the conversation (so digit-by-digit repeats of a number
   under discussion still work); otherwise say you do not
   have it and that the caller can ask you to search for it.

Safety: all three anchors must match exactly once or the
patch aborts with no changes; already-applied guard;
compiled in memory before writing; timestamped backup;
result must py_compile.

Run with:  sudo python3 patch_hub_phone_guard.py
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

if "never state a phone number from your own knowledge" in src:
    print("ABORT: phone guard already present (patch already applied?). No changes made.")
    sys.exit(1)

old1 = '''    _search_gate_words = ("weather", "forecast", "news", "score", "scores", "price", "stock", "latest", "traffic", "rain", "snow", "storm", "game", "election", "outside", "won", "who won", "earthquake", "concert", "open now", "today", "tonight", "tomorrow", "headline", "what time", "when is", "when does", "who is", "president", "search", "look up", "lookup", "google")'''
new1 = '''    _search_gate_words = ("weather", "forecast", "news", "score", "scores", "price", "stock", "latest", "traffic", "rain", "snow", "storm", "game", "election", "outside", "won", "who won", "earthquake", "concert", "open now", "today", "tonight", "tomorrow", "headline", "what time", "when is", "when does", "who is", "president", "search", "look up", "lookup", "google", "phone")'''

old2 = '''    _search_words = ("weather", "forecast", "news", "score", "scores", "price", "stock", "latest", "traffic", "rain", "snow", "storm", "game", "election", "outside", "won", "who won", "earthquake", "concert", "open now", "today", "tonight", "tomorrow", "headline", "what time", "when is", "when does", "who is", "president", "search", "look up", "lookup", "google", "movie times", "hours")'''
new2 = '''    _search_words = ("weather", "forecast", "news", "score", "scores", "price", "stock", "latest", "traffic", "rain", "snow", "storm", "game", "election", "outside", "won", "who won", "earthquake", "concert", "open now", "today", "tonight", "tomorrow", "headline", "what time", "when is", "when does", "who is", "president", "search", "look up", "lookup", "google", "movie times", "hours", "phone")'''

old3 = '''saying or implying that you searched.'''
new3 = '''saying or implying that you searched. One exception: never state a phone number from your own knowledge. Give a phone number only when it appears in search results provided for this question or when it was already stated earlier in this conversation. If a caller asks for a phone number and none was provided, say that you do not have it and that they can ask you to search for it.'''

for label, old in (("gate-words", old1), ("fallback-words", old2), ("prompt", old3)):
    n = src.count(old)
    if n != 1:
        print(f"ABORT: anchor {label} found {n} times (need exactly 1). No changes made.")
        sys.exit(1)

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-phoneguard"
shutil.copy2(PATH, backup)
src = src.replace(old1, new1).replace(old2, new2).replace(old3, new3)

# Compile in memory BEFORE writing: a bad edit must never reach the disk.
compile(src, PATH, "exec")

with open(PATH, "w") as f:
    f.write(src)

py_compile.compile(PATH, doraise=True)
print(f"PATCH OK. Backup: {backup}")
print("Now restart: sudo systemctl restart ai_orchestrator")

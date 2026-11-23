#!/usr/bin/env python3
"""Add conversation memory (last 5 exchanges) + allow long answers when needed.

AllStar AI hub, /home/asl/ai_orchestrator.py. Sam approved both on Nov 23.

CORRECTED VERSION (v2): the first version (patch_memory_brevity.py) failed its
syntax check. The history-recording lines were inserted at 12 spaces, but
the `return ai_reply` they sit before is at 16 spaces (inside a nested
try: the JSON-parsing try is at 12 spaces, its body at 16). The 12-space
lines closed the try suite early, so Python expected an except/finally
and rejected the file. Nothing was changed on the hub. This version inserts
those lines at 16 spaces. All other edits are identical to v1.

1. CONVERSATION MEMORY (Sam: "we could do five")
   Problem: every question starts fresh. The hub only sends the current
   audio to Gemini, so it cannot refer back to a previous Q&A — e.g. ask
   "what's two plus two", get "four", then ask "the answer from the first
   question plus four equals what" and it has no idea what it said.
   Fix: keep a rolling list of the last 5 exchanges (caller question +
   hub answer) in global_state["history"], and send it with each new
   question so Gemini can look back. Capped at 5 so it cannot grow
   unbounded. Cost is small: a few hundred extra words per call, still
   one API call per transmission, so it does not burn the daily request
   count any faster. The memory is shared across everyone who uses the
   hub (not per-caller).

2. BREVITY RULE (Sam: brief by default, but long when needed)
   Problem: on Nov 23 the hub refused "what are the 50 capitals" because
   the prompt says "Keep all spoken responses brief" and a 50-item list
   does not fit that rule.
   Fix: keep brief as the default, but add that if the caller asks for a
   list or something that needs detail, give the full answer instead of
   refusing for length.

CHANGES (5 edits):
  (1) global_state: add "history": [] key.
  (2) process_audio(): build _hist_text from the last 5 exchanges before
      the system_instruction is assembled.
  (3) system_instruction: insert the history block after the ADS-B snapshot.
  (4) system_instruction: soften the brevity rule (brief by default, full
      answer when the question needs detail).
  (5) process_audio(): after a real reply is produced (past the noise /
      identity safeguards), append (transcript, reply) to history, cap 5.
      Inserted at 16 spaces (inside the inner try, before return ai_reply).

SAFETY:
- Refuses to run unless the verified backup exists at
  /home/asl/backups/20261122/ai_orchestrator.py
- Every edit asserts its target line exists exactly once; if any check
  fails, NOTHING is written.
- Writes to a temp file, syntax-checks it with py_compile, and only then
  copies it into place (shutil.copyfile, so it works across filesystems).
- Rollback: cp /home/asl/backups/20261122/ai_orchestrator.py \
               /home/asl/ai_orchestrator.py
            sudo systemctl restart ai_orchestrator.service

Run as root (or with sudo):  sudo python3 patch_memory_brevity2.py
Then restart the service:    sudo systemctl restart ai_orchestrator.service
Test: ask "what is two plus two", then ask "add four to that answer" —
  it should answer eight. Ask for the 50 capitals — it should list them
  instead of refusing.
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_memory_fix2.py"


def fail(msg):
    print("PATCH ABORTED: " + msg)
    sys.exit(1)


def main():
    if not os.path.exists(BACKUP):
        fail("verified backup not found at " + BACKUP + "; refusing to change anything.")
    with open(TARGET) as f:
        lines = f.readlines()

    def find(marker, what):
        hits = [i for i, ln in enumerate(lines) if marker in ln]
        if len(hits) != 1:
            fail("expected exactly 1 line containing %r for %s, found %d" % (marker, what, len(hits)))
        return hits[0]

    def block_lines(block):
        return [ln + "\n" for ln in block.strip("\n").split("\n")]

    def insert_after(marker, block, what):
        i = find(marker, what)
        lines[i + 1:i + 1] = block_lines(block)
        print("  ok: " + what)

    def insert_before(marker, block, what):
        i = find(marker, what)
        lines[i:i] = block_lines(block)
        print("  ok: " + what)

    def replace_line(marker, new_line, what):
        i = find(marker, what)
        lines[i] = new_line + "\n"
        print("  ok: " + what)

    print("Patching " + TARGET + " ...")
    # (1) Add a history list to global_state.
    insert_after('    "last_ai_reply": "",', '    "history": [],',
                 "history list in global_state")
    # (2) Build the history text just before the system instruction.
    insert_before("    system_instruction = (", r"""
    # Conversation memory: keep the last 5 exchanges so Gemini can refer
    # back to them (e.g. "add four to that answer"). Capped at 5 so it
    # cannot grow unbounded. Shared across callers (not per-person).
    _hist = global_state.get("history", [])
    _hist_text = ""
    if _hist:
        _hist_lines = []
        for _q, _a in _hist:
            _hist_lines.append(f"Caller: {_q}\nHub: {_a}")
        _hist_text = (
            "RECENT CONVERSATION (last few exchanges - the caller may refer back to these):\n"
            + "\n".join(_hist_lines)
            + "\n\n"
        )
""", "build history text before system_instruction")
    # (3) Insert the history block into the prompt after the ADS-B snapshot.
    insert_after('        f"{adsb_snapshot}\\n\\n"', '        f"{_hist_text}"',
                 "history block in system_instruction")
    # (4) Brevity rule: brief by default, but give the full answer when the
    # question needs a list or detail instead of refusing for length.
    replace_line(
        "Keep all spoken responses brief, clean, and completely free of markdown formatting symbols like asterisks or hashtags.",
        '        "Keep all spoken responses brief, clean, and completely free of markdown formatting symbols like asterisks or hashtags. Answer briefly by default, but if the caller asks for a list or something that needs detail, give the full answer, do not refuse just because it is long.\\n"',
        "brevity rule allows long answers when needed")
    # (5) Remember each real exchange (past the noise/identity safeguards)
    # before returning the reply. The return is at 16 spaces (inside the
    # inner JSON-parsing try, whose body is at 16), so these lines must
    # also be at 16 spaces. (v1 used 12 and broke the try/except.)
    insert_before("                return ai_reply", r"""
                # Remember this exchange (cap at 5) so follow-ups can refer back to it.
                _h = global_state.setdefault("history", [])
                _h.append((user_transcript, ai_reply))
                del _h[:-5]
""", "record exchange in history")

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl restart ai_orchestrator.service")
    print("Test: ask 'what is two plus two', then 'add four to that answer' (expect eight).")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


if __name__ == "__main__":
    main()

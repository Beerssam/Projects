#!/usr/bin/env python3
"""Stop the AI hub self-talk loop (AllStar AI hub, /home/asl/ai_orchestrator.py).

PROBLEM (proven by the log Sam pasted, Nov 23 ~10:45-10:47):
  The hub answered "three times three is nine" correctly, then kept
  talking on its own. The log shows the loop plainly:
    10:45:51  Gemini: "Copy that KF0RIZ, good to hear you. 3 times 3 is 9."
    10:46:08  Whisper gate PASSED the hub's own playback as a new clip:
              'Copy that KF0RIZ. Good to hear you. Three times three is nine.'
    10:46:11  Gemini: "Good to hear you too KF0RIZ. Thanks for the contact."
    10:46:26  Gate passed its own playback again, Gemini replied again,
              and so on — each reply recorded and answered as if Sam spoke.
  Why the guards missed it:
  - The Whisper gate only drops our own voice when the transcript EXACTLY
    matches the last reply. Whisper transcribes the playback slightly
    differently each time ("3 times 3 is 9" vs "three times three is
    nine", "U2" vs "you too", callsign mangled), so the exact match
    never fires and the loop never converges.
  - The DASHBOARD BYPASS (flag file) is what stops the hub hearing its
    own playback — but it only works for the FCC beacons, because the
    orchestrator writes the flag before a beacon and NOT before an AI
    reply. So a reply's self-recording sails past the flag check and
    only the brittle exact-match gate stands in its way.

FIX (1 edit):
  Write the same flag file (/var/run/ai_dash_active) at the start of
  play_to_node(), so EVERY playback the hub makes — beacon or AI reply —
  marks its own audio. The main loop then drops that playback's
  self-recording via DASHBOARD BYPASS (and deletes the flag), exactly as
  it already does for beacons. The gate's exact-match check stays as a
  backstop.

SAFETY:
- Refuses to run unless the verified backup exists at
  /home/asl/backups/20261122/ai_orchestrator.py
- The edit asserts its target line exists exactly once; if the check
  fails, NOTHING is written.
- Writes to a temp file, syntax-checks it with py_compile, and only then
  copies it into place (shutil.copyfile, so it works across filesystems).
- Rollback: cp /home/asl/backups/20261122/ai_orchestrator.py \
               /home/asl/ai_orchestrator.py
            sudo systemctl restart ai_orchestrator.service

Run as root (or with sudo):  sudo python3 patch_loop_fix.py
Then restart the service:    sudo systemctl start ai_orchestrator.service
  (the service is currently STOPPED — use start, not restart)
Then watch the log:          tail -f /var/log/ai_orchestrator.log
Look for: the next reply's self-recording dropped as
  [DASHBOARD BYPASS] instead of being passed to Gemini, and no
  unsolicited follow-up replies.
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_loop_fix.py"


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

    print("Patching " + TARGET + " ...")
    # Mark every playback (beacon or AI reply) so its self-recording is
    # dropped by DASHBOARD BYPASS instead of being heard as a new caller.
    insert_after("def play_to_node", r"""
    # Stop the self-talk loop: mark our own playback so the main loop drops
    # its self-recording via DASHBOARD BYPASS instead of hearing it as a
    # new transmission. (Beacons already do this; replies did not, so the
    # gate's exact-match check was the only guard, and Whisper's small
    # transcription differences let our own reply through.)
    try:
        open("/var/run/ai_dash_active", "w").close()
    except Exception:
        pass
""", "flag own playback in play_to_node")

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl start ai_orchestrator.service")
    print("Then watch: tail -f /var/log/ai_orchestrator.log")
    print("Look for: [DASHBOARD BYPASS] dropping the reply's self-recording, no unsolicited replies.")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Stage 2 for /home/asl/ai_orchestrator.py (AllStar AI hub) — wait until the
speaker is done before processing a recording.

PROBLEM (proven by the Nov 23 RF tests):
  The main loop decides a recording is "done" by watching the monitor file
  stop growing for 1.5 s. But live radio audio over the link arrives late
  and in bursts, so that check fires too early and the hub processes a
  partial clip. Sam's 10:16 key-up was dropped as "too short" even though
  the file is 191,084 bytes now (the words arrived after the drop). His
  10:21 key-up was processed with only "This is KF0RIZ." in the file, so
  Gemini had no question and gave the generic greeting instead of "four".

FIX:
  Use the AMI transmit events (RPT_TXKEYED), which the observer now
  captures reliably, as the "speaker is done" signal. The observer records
  the transmitter state in shared memory. Before the main loop trusts a
  file's size, it waits until the transmitter has been unkeyed for TX_TAIL
  seconds. The file-size stability check and the size guard stay as
  backstops, but the real decision is now "Sam is done talking", not
  "the file stopped growing". This is the receive-window design Sam
  approved: decode after the beep, using the transmit state.

  TXKEYED brackets an incoming transmission on this pseudo node (it went
  1 at 10:16:17 and 0 at 10:16:29 for Sam's key-up). It is also 1 while
  the hub itself plays audio, but the hub knows when it is playing, and
  those self-recordings are dropped by the dashboard bypass / echo guard
  anyway — the wait just delays their drop by a few seconds, which is
  harmless.

  Fails open: if the observer has never reported a TXKEYED state (AMI
  down, or no transmission yet), or the wait times out after 60 s, the
  loop proceeds with the old file-size behaviour instead of stalling.

CHANGES (5 edits, all in /home/asl/ai_orchestrator.py):
  1. Two constants: TX_TAIL = 2.0 s, TX_WAIT_TIMEOUT = 60.0 s.
  2. Two shared-state keys in global_state: "tx_keyed" (None/True/False)
     and "tx_keyed_at" (time of the last TXKEYED event).
  3. Observer: on each RPT_TXKEYED event, update tx_keyed / tx_keyed_at.
  4. New function wait_for_transmission_end() (before process_audio).
  5. wait_for_file_stability() calls wait_for_transmission_end() first.

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

Run as root (or with sudo):  sudo python3 patch_stage2.py
Then restart the service:    sudo systemctl restart ai_orchestrator.service
Then watch the log:          tail -f /var/log/ai_orchestrator.log
Look for: a full transcript on the next key-up (the whole question, not
just the callsign) and a real answer instead of the generic greeting.
NOTE: run the ID-safeguard fix (patch_id_fix.py) first if you have not
already — both patches only change the file, so you can run one after
the other and restart the service once at the end.
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_stage2.py"

NEW_FUNC = r"""
def wait_for_transmission_end():
    # Stage 2: wait until the AMI-reported transmitter has been unkeyed for
    # TX_TAIL seconds, so the recording is complete before we process it.
    # Live link audio arrives late/bursty, so the file-size stability check
    # alone fires too early and we process a partial clip. Fails open: if
    # the observer has never reported a TXKEYED state (AMI down / no data
    # yet), or the wait times out, return and let the normal checks decide.
    _start = time.time()
    while True:
        _keyed = global_state.get("tx_keyed")
        if _keyed is None:
            return
        if not _keyed:
            if time.time() - global_state.get("tx_keyed_at", 0) >= TX_TAIL:
                return
        if time.time() - _start > TX_WAIT_TIMEOUT:
            ts_log("AMI", "Transmission-end wait timed out; proceeding anyway.")
            return
        time.sleep(0.25)
"""


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

    def replace_token(marker, old, new, what):
        i = find(marker, what)
        if old not in lines[i]:
            fail("line for %s does not contain %r: %r" % (what, old, lines[i]))
        lines[i] = lines[i].replace(old, new, 1)
        print("  ok: " + what)

    def insert_after(marker, block, what):
        i = find(marker, what)
        lines[i + 1:i + 1] = block_lines(block)
        print("  ok: " + what)

    def insert_before(marker, block, what):
        i = find(marker, what)
        lines[i:i] = block_lines(block)
        print("  ok: " + what)

    print("Patching " + TARGET + " ...")
    # 1. TX constants after the echo-guard constant
    insert_after("REPEATER_TAIL_GUARD = 3.0", r"""
TX_TAIL = 2.0  # seconds the transmitter must stay unkeyed before a clip is processed
TX_WAIT_TIMEOUT = 60.0  # give up waiting after this long (fail open to old behavior)
""", "TX constants")
    # 2. Shared transmitter state in global_state
    replace_token('"last_ai_reply": ""', '"last_ai_reply": ""', '"last_ai_reply": "",\n    "tx_keyed": None,\n    "tx_keyed_at": 0.0', "global_state tx_keyed")
    # 3. Observer: track RPT_TXKEYED state
    insert_before('if "RXKEYED" in block or "TXKEYED" in block:', r"""
                # Stage 2: track the transmitter state so the main loop can wait
                # until the speaker is done before processing a recording.
                if "Event: RPT_TXKEYED" in block:
                    for _ln in block.splitlines():
                        if _ln.startswith("EventValue:"):
                            global_state["tx_keyed"] = (_ln.split(":", 1)[1].strip() == "1")
                            global_state["tx_keyed_at"] = time.time()
                            break
""", "observer tracks TXKEYED")
    # 4. New wait function before process_audio
    insert_before("def process_audio(wav_path):", NEW_FUNC, "wait_for_transmission_end function")
    # 5. wait_for_file_stability waits for the speaker to finish first
    insert_after("def wait_for_file_stability", r"""
    # Stage 2: do not trust the file size until the speaker is done. The
    # transmitter must have been quiet for TX_TAIL seconds, or we wait.
    wait_for_transmission_end()
""", "stability waits for transmission end")

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl restart ai_orchestrator.service")
    print("Then watch: tail -f /var/log/ai_orchestrator.log")
    print("Look for: a full transcript on the next key-up (whole question, not just callsign).")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Conditional ADS-B + KCMO PD helicopters first + 15 closest aircraft.

AllStar AI hub, /home/asl/ai_orchestrator.py. Sam approved on Nov 23.

BACKGROUND:
- Sam's ADS-B data used to send EVERY airplane for 100 miles to Gemini so
  he could ask any airplane question. He liked that, but the huge payload
  kept locking up Gemini. The setup was cut down to just the 5 closest
  aircraft + KCMO PD. He now wants the ADS-B data sent ONLY when he asks
  about planes, so normal calls stay lean, and when he does ask, he wants
  a fuller picture (more than 5) with the KCMO police helicopters first.
- The KCMO PD helicopters (N690PD/N691PD/N692PD) currently come LAST in
  the ADS-B text (closest aircraft first, PD second). Sam wants them first.

CHANGES (3 groups):
  (A) CONDITIONAL ADS-B — only include the plane data when the question is
      about aircraft.
      - whisper_gate() already transcribes locally and returns the text,
        but the main loop throws it away (captured as _gate_text, unused).
        Store it in global_state["last_gate_text"] on the success path so
        process_audio() can read it. (No main-loop change needed.)
      - process_audio(): check that transcript for plane/helicopter words.
        If it matches (or the transcript is empty because Whisper failed —
        fail OPEN so a plane question is never missed), fetch/include the
        ADS-B data as before. Otherwise skip it entirely (no fetch, no
        text in the prompt), so normal calls stay lean.
      - Keywords: plane, aircraft, helicopter, heli, helo, overhead,
        flying, flight, airplane, jet, airport, airspace, kemp, kcmo,
        police. ("kemp"/"kcmo"/"police" catch police-helicopter questions.)
  (B) PD FIRST — in get_nearby_flights(), put the "KCMO PD Fleet Status"
      section BEFORE the "Closest Aircraft" section (both the normal case
      and the no-aircraft case), so the police helicopters take priority
      in what Gemini sees.
  (C) 15 CLOSEST (was 5) — when ADS-B is included, list the 15 closest
      aircraft instead of 5, so Sam can ask about more planes like he used
      to. 15 is ~750 characters of text, about a quarter of the old 60-70
      aircraft dump that locked Gemini up, and it is only sent when he
      asks about planes now. (Sam can change the number; it is the [:15]
      slice in get_nearby_flights().)

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

Run as root (or with sudo):  sudo python3 patch_adsb_conditional.py
Then restart the service:    sudo systemctl restart ai_orchestrator.service
Test: ask a normal question (no ADS-B should be fetched/sent); then ask
  "what aircraft are overhead?" or "where is the police helicopter?" —
  it should answer with the planes, KCMO PD first.
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_adsb_fix.py"


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

    def delete_line(marker, what):
        i = find(marker, what)
        del lines[i]
        print("  ok: " + what)

    print("Patching " + TARGET + " ...")
    # (A1) global_state: track the last Whisper gate transcript.
    insert_after('    "history": [],', '    "last_gate_text": "",',
                 "last_gate_text in global_state")
    # (A2) whisper_gate(): store the transcript in global_state on the
    # success path (right before `return True, text`), so process_audio()
    # can read it. The main loop already calls whisper_gate() before
    # process_audio(), so the value is fresh for each clip.
    insert_before("    return True, text",
                  '    global_state["last_gate_text"] = text',
                  "store gate transcript in global_state")
    # (B1) get_nearby_flights(): empty case — PD section first.
    replace_line(
        'result = "Closest Aircraft: None | KCMO PD Fleet Status: No active assets detected."',
        '                result = "KCMO PD Fleet Status: No active assets detected. | Closest Aircraft: None"',
        "PD first in empty case")
    # (C) get_nearby_flights(): 15 closest instead of 5.
    replace_line(
        "closest_five_elements = [item[\"desc\"] for item in parsed_tracking_pool[:5]]",
        '            closest_elements = [item["desc"] for item in parsed_tracking_pool[:15]]',
        "15 closest aircraft")
    replace_line(
        'closest_section = "Closest Aircraft: " + (" | ".join(closest_five_elements) if closest_five_elements else "None detected.")',
        '            closest_section = "Closest Aircraft: " + (" | ".join(closest_elements) if closest_elements else "None detected.")',
        "closest section uses 15")
    # (B2) get_nearby_flights(): PD section first in the normal case.
    replace_line(
        'result = f"{closest_section}\\n{pd_section}"',
        '            result = f"{pd_section}\\n{closest_section}"',
        "PD first in normal case")
    # (A4) system_instruction: use the conditional block instead of the
    # always-on header + snapshot lines. NOTE: this must run BEFORE (A3),
    # because (A3) inserts a new copy of the header/snapshot text inside
    # the conditional block, and these markers must match exactly once.
    replace_line(
        'f"REAL-TIME LOCAL AIRSPACE POSITION REPOSITORY ({ADSB_RADIUS_NM} NM Radius around Shawnee, KS):\\n"',
        '        f"{adsb_block}"',
        "prompt uses conditional ADS-B block")
    delete_line(
        'f"{adsb_snapshot}\\n\\n"',
        "remove always-on ADS-B snapshot line")
    # (A3) process_audio(): only fetch/include ADS-B when the Whisper
    # transcript asks about aircraft. Fail OPEN on an empty transcript.
    # Runs LAST because its block contains the header/snapshot text that
    # (A4) and the delete above just removed from the prompt.
    replace_line(
        "    adsb_snapshot = get_nearby_flights()",
        r"""
    # ADS-B only when the caller asks about aircraft (per Sam, Nov 23).
    # Check the local Whisper transcript (stored by whisper_gate) for
    # plane/helicopter words. Fail OPEN: if the transcript is empty
    # (Whisper failed), include the data so a plane question is never
    # missed because of a bad transcript.
    _gate_low = (global_state.get("last_gate_text") or "").lower()
    _plane_words = ("plane", "aircraft", "helicopter", "heli", "helo", "overhead", "flying", "flight", "airplane", "jet", "airport", "airspace", "kemp", "kcmo", "police")
    _want_adsb = (not _gate_low) or any(w in _gate_low for w in _plane_words)
    if _want_adsb:
        adsb_snapshot = get_nearby_flights()
        adsb_block = (
            f"REAL-TIME LOCAL AIRSPACE POSITION REPOSITORY ({ADSB_RADIUS_NM} NM Radius around Shawnee, KS):\n"
            f"{adsb_snapshot}\n\n"
        )
    else:
        adsb_block = ""
""",
        "conditional ADS-B block")

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl restart ai_orchestrator.service")
    print("Test: ask a normal question (no ADS-B); then ask 'what aircraft are overhead?' (PD first, 15 closest).")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


if __name__ == "__main__":
    main()

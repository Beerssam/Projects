#!/usr/bin/env python3
"""Add Kansas Highway Patrol and Missouri Highway Patrol aircraft to the
priority list in the ADS-B data, same treatment as the KCMO PD helicopters.

AllStar AI hub, /home/asl/ai_orchestrator.py. Sam approved Nov 23
("just the main ones that normally fly").

AIRCRAFT (FAA registry + photo confirmations, Nov 23):
- Kansas Highway Patrol (6, the ones that normally fly on patrol):
  Helicopters N650HP, N670HP (Airbus AS350B3);
  Airplanes N600HP (Cessna Caravan 208B), N900HP, N940HP, N950HP
  (Cessna 206H). Left out: N550KS (Citation 525B jet, a transport,
  not a patrol bird) — Sam can add it if he wants it.
- Missouri Highway Patrol (6, the ones that normally fly on patrol):
  Helicopters N93MP, N95MP (Bell 407);
  Airplanes N79MP (Cessna 182T), N83MP (King Air B200GT),
  N86MP (Kodiak 200), N94MP (Cessna 182S).
  Left out: N90MP (Hughes 269A trainer), the obscure registry entries
  (N100SM, N116MP, N285MP, N289MP, N873MP, N970MP, N97MP),
  N81MP (seen in a photo as MSHP but not confirmed in the registry pull),
  and N77MP/N96MP (crashed years ago).

CHANGES (in get_nearby_flights()):
  (1) Two new fleet lists next to KCMO_POLICE_FLEET:
      KANSAS_HIGHWAY_PATROL, MISSOURI_HIGHWAY_PATROL.
  (2) Two new "active" lists (active_khp_aircraft, active_mshp_aircraft),
      filled by the same substring match on callsign/registration that
      the KCMO PD check already uses.
  (3) Two new sections ("Kansas Highway Patrol: ...",
      "Missouri Highway Patrol: ..."), placed after the KCMO PD section
      and BEFORE the Closest Aircraft section, in both the normal case
      and the no-aircraft case.
  (4) Docstring updated (it still said "5 closest"; the code now lists 15).

ORDER of the ADS-B text after this patch (when plane data is sent):
  KCMO PD Fleet Status
  Kansas Highway Patrol
  Missouri Highway Patrol
  Closest Aircraft (15 closest)

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

Run as root (or with sudo):  sudo python3 patch_highway_patrol.py
Then restart the service:    sudo systemctl restart ai_orchestrator.service
Test: ask "what aircraft are overhead?" — if a KHP or MSHP aircraft is
  up, it should appear in its own section above the closest list.
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_highway_fix.py"


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

    def replace_line(marker, new_line, what):
        i = find(marker, what)
        lines[i] = new_line + "\n"
        print("  ok: " + what)

    print("Patching " + TARGET + " ...")
    # (1) Fleet lists, next to KCMO_POLICE_FLEET.
    insert_after(
        'KCMO_POLICE_FLEET = ["N690PD", "N691PD", "N692PD"]',
        'KANSAS_HIGHWAY_PATROL = ["N650HP", "N670HP", "N600HP", "N900HP", "N940HP", "N950HP"]\nMISSOURI_HIGHWAY_PATROL = ["N93MP", "N95MP", "N79MP", "N83MP", "N86MP", "N94MP"]',
        "KHP + MSHP fleet lists")
    # (4) Docstring: it still said "5 closest"; the code lists 15.
    replace_line(
        '"""Queries adsb.fi and splits data into two dedicated sections: 5 closest aircraft and KCMO PD status."""',
        '    """Queries adsb.fi and splits data into priority law-enforcement sections (KCMO PD, Kansas Highway Patrol, Missouri Highway Patrol) plus the 15 closest aircraft."""',
        "docstring (15 closest)")
    # (3a) Empty case: all three priority sections first.
    replace_line(
        'result = "KCMO PD Fleet Status: No active assets detected. | Closest Aircraft: None"',
        '                result = "KCMO PD Fleet Status: No active assets detected. | Kansas Highway Patrol: No active assets detected. | Missouri Highway Patrol: No active assets detected. | Closest Aircraft: None"',
        "empty case lists all three agencies")
    # (2a) Active lists for KHP and MSHP.
    insert_after(
        "            active_pd_helicopters = []",
        "            active_khp_aircraft = []\n            active_mshp_aircraft = []",
        "active KHP + MSHP lists")
    # (2b) Match checks, same substring method as the KCMO PD check.
    insert_after(
        "                    active_pd_helicopters.append(formatted_desc)",
        "                is_khp_match = any(reg_no in callsign.upper() or reg_no in reg.upper() for reg_no in KANSAS_HIGHWAY_PATROL)\n                if is_khp_match:\n                    active_khp_aircraft.append(formatted_desc)\n                is_mshp_match = any(reg_no in callsign.upper() or reg_no in reg.upper() for reg_no in MISSOURI_HIGHWAY_PATROL)\n                if is_mshp_match:\n                    active_mshp_aircraft.append(formatted_desc)",
        "KHP + MSHP match checks")
    # (3b) Priority sections, after the KCMO PD section.
    insert_after(
        'pd_section = "KCMO PD Fleet Status: " + (" | ".join(active_pd_helicopters) if active_pd_helicopters else "No active assets detected.")',
        '            khp_section = "Kansas Highway Patrol: " + (" | ".join(active_khp_aircraft) if active_khp_aircraft else "No active assets detected.")\n            mshp_section = "Missouri Highway Patrol: " + (" | ".join(active_mshp_aircraft) if active_mshp_aircraft else "No active assets detected.")',
        "KHP + MSHP sections")
    # (3c) Result order: KCMO PD, KHP, MSHP, then closest.
    replace_line(
        'result = f"{pd_section}\\n{closest_section}"',
        '            result = f"{pd_section}\\n{khp_section}\\n{mshp_section}\\n{closest_section}"',
        "result order: PD, KHP, MSHP, closest")

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl restart ai_orchestrator.service")
    print("Test: ask 'what aircraft are overhead?' — a KHP or MSHP aircraft should appear in its own section above the closest list.")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


if __name__ == "__main__":
    main()

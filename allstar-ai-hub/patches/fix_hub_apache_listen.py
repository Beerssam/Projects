#!/usr/bin/env python3
"""fix_hub_apache_listen.py - Hub Apache: forward /api/listen to
the AI dashboard on 127.0.0.1:62573 (Nov 25 2026)

Why: the hub's HTTPS front door is Apache
(000-asl3-appliance-ssl.conf). It proxies the dashboard's API
through an enumerated list of ProxyPass lines written Nov 24 -
connections, aircraft, recent, ai_status, pool, health, solar,
trail/, route/, stream, action/. The Listen feature added today
(GET /api/listen and /api/listen/<name>) is not in the list, so
browsers arriving via :9443 get a 404 for it while every older
route works.

Change: insert one ProxyPass/ProxyPassReverse pair for
"/api/listen" right after the existing "/api/pool" pair, in the
same style. Without trailing slashes, Apache prefix-matches it,
so the bare list URL and the per-clip audio URLs both forward
with the remainder appended correctly. Nothing else is touched.

Note: the live file is the one in sites-enabled (it differs from
the stock copy in sites-available - the dashboard lines exist
only in sites-enabled). This script edits the sites-enabled
path, which is the file Apache actually loads.

Safety: aborts with no changes if '/api/listen' is already
present or the pool anchor line is not found exactly once; a
timestamped backup is taken first; after the edit the script
runs 'apachectl configtest' and RESTORES THE BACKUP
automatically unless it answers Syntax OK. On success it prints
the reload command for Sam to run.

Run with:  sudo python3 fix_hub_apache_listen.py
Then:      sudo systemctl reload apache2
Rollback: copy the backup back over the conf and reload.
"""
import os
import shutil
import subprocess
import sys
import time

PATH = "/etc/apache2/sites-enabled/000-asl3-appliance-ssl.conf"

ANCHOR = 'ProxyPassReverse "/api/pool" "http://127.0.0.1:62573/api/pool"'
INSERT = [
    'ProxyPass "/api/listen" "http://127.0.0.1:62573/api/listen"',
    'ProxyPassReverse "/api/listen" "http://127.0.0.1:62573/api/listen"',
]

if not os.path.exists(PATH):
    print(f"ABORT: {PATH} not found. No changes made.")
    sys.exit(1)

with open(PATH) as f:
    lines = f.read().split("\n")

if any("/api/listen" in line for line in lines):
    print("ABORT: '/api/listen' already present (fix already applied?). No changes made.")
    sys.exit(1)

hits = [i for i, line in enumerate(lines) if line.strip() == ANCHOR]
if len(hits) != 1:
    print(f"ABORT: pool ProxyPassReverse anchor found {len(hits)} times (need exactly 1). No changes made.")
    sys.exit(1)

idx = hits[0]
indent = lines[idx][: len(lines[idx]) - len(lines[idx].lstrip())]

backup = f"{PATH}.bak-{time.strftime('%Y%m%d-%H%M%S')}-listenapi"
shutil.copy2(PATH, backup)

lines[idx + 1: idx + 1] = [indent + text for text in INSERT]

with open(PATH, "w") as f:
    f.write("\n".join(lines))

# Verify Apache still parses the config; restore on failure.
apachectl = shutil.which("apachectl")
if apachectl is None:
    print(f"PATCH WRITTEN to {PATH} (backup: {backup}) but 'apachectl' was not found to test it.")
    print("Check the config by hand before reloading.")
    sys.exit(0)

test = subprocess.run([apachectl, "configtest"], capture_output=True, text=True)
combined = (test.stdout or "") + (test.stderr or "")
if test.returncode != 0 or "Syntax OK" not in combined:
    shutil.copy2(backup, PATH)
    print("apachectl configtest FAILED - backup restored, live config unchanged. Output:")
    print(combined)
    sys.exit(1)

print(f"PATCH OK in {PATH}. Backup: {backup}")
print("configtest: Syntax OK. Now reload: sudo systemctl reload apache2")

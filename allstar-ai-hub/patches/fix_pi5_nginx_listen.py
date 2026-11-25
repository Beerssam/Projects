#!/usr/bin/env python3
"""fix_pi5_nginx_listen.py - Pi5 nginx: forward /api/listen to the
AI hub dashboard (Nov 25 2026)

Why: the hub dashboard gained a Listen feature today (GET
/api/listen for the clip list, GET /api/listen/<name> for audio).
The Pi5's allstar-hub site forwards API calls through a regex
location whose alternation lists only the routes that existed on
Nov 24:

    location ~ ^/api/(connections|aircraft|recent|ai_status|pool|health|solar|trail|route)(/|$) {
        proxy_pass http://192.168.1.200:62573;

'listen' is not in the list, so /api/listen falls through to the
catch-all that proxies to the hub's Apache - which does not know
it either - and the browser gets a 404 while the rest of the
panel (pool, recent, ...) stays live.

Change: add '|listen' to that one alternation. The regex's (/|$)
tail already covers /api/listen/<name> as well. Nothing else in
the file is touched.

Safety: the alternation must occur exactly once or the script
aborts with no changes; an already-fixed guard covers reruns; a
timestamped backup is taken first; after the edit the script runs
'nginx -t' and RESTORES THE BACKUP automatically if the test
fails. On success it prints the reload command for Sam to run.

Run with:  sudo python3 fix_pi5_nginx_listen.py
Then:      sudo systemctl reload nginx
Rollback: copy the backup back over the site file and reload.
"""
import os
import shutil
import subprocess
import sys
import time

CANDIDATES = [
    "/etc/nginx/sites-enabled/allstar-hub",
    "/etc/nginx/sites-available/allstar-hub",
]

OLD = "(connections|aircraft|recent|ai_status|pool|health|solar|trail|route)"
NEW = "(connections|aircraft|recent|ai_status|pool|health|solar|trail|route|listen)"

path = None
for cand in CANDIDATES:
    if os.path.exists(cand):
        path = os.path.realpath(cand)
        break
if path is None:
    print("ABORT: no allstar-hub site file found in sites-enabled or sites-available. No changes made.")
    sys.exit(1)

with open(path) as f:
    src = f.read()

if NEW in src:
    print("ABORT: 'listen' is already in the API regex (fix already applied?). No changes made.")
    sys.exit(1)

n = src.count(OLD)
if n != 1:
    print(f"ABORT: API alternation found {n} times in {path} (need exactly 1). No changes made.")
    sys.exit(1)

backup = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}-listenapi"
shutil.copy2(path, backup)

src = src.replace(OLD, NEW)

with open(path, "w") as f:
    f.write(src)

# Verify the running configuration still parses; restore on failure.
nginx = shutil.which("nginx")
if nginx is None:
    print(f"PATCH WRITTEN to {path} (backup: {backup}) but 'nginx' was not found to test it.")
    print("Check the config by hand before reloading.")
    sys.exit(0)

test = subprocess.run([nginx, "-t"], capture_output=True, text=True)
if test.returncode != 0:
    shutil.copy2(backup, path)
    print("nginx -t FAILED - backup restored, live config unchanged. Test output:")
    print(test.stdout)
    print(test.stderr)
    sys.exit(1)

print(f"PATCH OK in {path}. Backup: {backup}")
print("nginx -t passed. Now reload: sudo systemctl reload nginx")

#!/usr/bin/env bash
# install_searxng.sh - Self-hosted SearXNG search for the AI hub
# (Nov 25 2026)
#
# Why: DuckDuckGo bot-walls this network on BOTH its html and lite
# endpoints (verified Nov 25: challenge pages, 0 results), so the
# hub's fallback search engine has never returned a single result.
# SearXNG is a self-hosted metasearch engine with a proper JSON
# API. Hosted on the hub itself, the orchestrator's fallback
# queries become localhost calls.
#
# What this script does:
#   1. Installs Docker (docker.io) if it is not already present.
#   2. Writes /home/asl/searxng/settings.yml (secret key generated
#      on this machine, never printed; JSON format enabled;
#      rate limiter off - the API is localhost-only).
#   3. Runs the searxng/searxng container bound to 127.0.0.1:8080
#      ONLY (not reachable from the LAN or the internet),
#      restart-unless-stopped.
#   4. Self-tests with the Raytown query and prints the top
#      results it got back.
#
# Nothing else is touched: no Asterisk, orchestrator, or dashboard
# changes. The orchestrator patch that aims the fallback at
# SearXNG is a separate step after this verifies.
#
# Run with:  sudo bash install_searxng.sh
# Remove:    sudo docker rm -f searxng && sudo rm -rf /home/asl/searxng
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo." >&2
    exit 1
fi

SETTINGS_DIR=/home/asl/searxng
SETTINGS=$SETTINGS_DIR/settings.yml

# --- 1. Docker ---------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found - installing docker.io ..."
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io
    systemctl enable --now docker
else
    echo "Docker already present: $(docker --version)"
    systemctl enable --now docker || true
fi

# --- 2. Settings ---------------------------------------------------
mkdir -p "$SETTINGS_DIR"
if [ ! -f "$SETTINGS" ]; then
    SECRET=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
    cat > "$SETTINGS" <<EOF
use_default_settings: true
server:
  port: 8080
  bind_address: "0.0.0.0"
  secret_key: "$SECRET"
  limiter: false
  image_proxy: true
search:
  safe_search: 0
  autocomplete: ""
  formats:
    - html
    - json
EOF
    echo "Wrote $SETTINGS (secret key generated on this machine)."
else
    echo "Keeping existing $SETTINGS."
fi
chown -R asl:asl "$SETTINGS_DIR" || true

# --- 3. Container ---------------------------------------------------
docker rm -f searxng >/dev/null 2>&1 || true
echo "Pulling searxng/searxng:latest ..."
docker pull searxng/searxng:latest
docker run -d \
    --name searxng \
    --restart unless-stopped \
    -p 127.0.0.1:8080:8080 \
    -v "$SETTINGS_DIR:/etc/searxng:rw" \
    searxng/searxng:latest
echo "Container started (bound to 127.0.0.1:8080 only)."

# --- 4. Self-test ---------------------------------------------------
echo "Waiting for SearXNG to answer, then testing with the Raytown query ..."
ok=""
for i in $(seq 1 30); do
    if curl -s -o /tmp/searxng_test.json -w '' \
        'http://127.0.0.1:8080/search?q=Raytown%20Missouri%20police%20officer%20killed&format=json' \
        && [ -s /tmp/searxng_test.json ]; then
        ok=1
        break
    fi
    sleep 2
done

if [ -z "$ok" ]; then
    echo "SELF-TEST FAILED: SearXNG did not answer on 127.0.0.1:8080."
    echo "Container logs (last 20 lines):"
    docker logs --tail 20 searxng || true
    exit 1
fi

python3 - <<'PYEOF'
import json
try:
    with open("/tmp/searxng_test.json") as f:
        data = json.load(f)
except Exception as e:
    print(f"SELF-TEST FAILED: response was not JSON ({e}).")
    print("First bytes of the response:")
    print(open("/tmp/searxng_test.json", "rb").read(300))
    raise SystemExit(1)
results = data.get("results", [])
print(f"SELF-TEST: {len(results)} results for the Raytown query.")
for r in results[:3]:
    print(" -", (r.get("title") or "")[:100])
if not results:
    print("SearXNG answered but returned no results - its upstream")
    print("engines may be throttling. Show Muse this output.")
    raise SystemExit(1)
print("SEARXNG IS UP. Next step: the orchestrator patch that aims")
print("the hub's fallback search at http://127.0.0.1:8080.")
PYEOF

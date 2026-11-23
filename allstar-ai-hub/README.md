# AllStar AI Hub — Node 625731

Voice AI over AllStar radio. Sam keys up on his radio → home node 625730 →
hub 625731 (Pi 5) → speech-to-text → Google AI (Gemini, free tier) → reply →
text-to-speech → back over the radio. Anyone with AllStar can dial in.

## Files

- `live/` — the current working code on the hub (redacted; see below).
  - `ai_orchestrator.py` — the brain. Watches the Asterisk monitor
    directory, runs the Whisper gate, calls Gemini, plays replies.
  - `ai_dashboard.py` — the Flask dashboard (map, aircraft list, Q&A,
    AI status, Gemini pool, hub health).
  - `ai_orchestrator.service`, `ai_dashboard.service` — systemd units.
- `patches/` — every patch script applied to the hub, newest last.
  Each one is self-contained: it refuses to run unless a verified backup
  exists, asserts each target line, syntax-checks, then copies into place.
  Run with `sudo python3 <patch>.py`, then restart the service it touches.

## Secrets — read this

The live code on the hub contains secrets in plaintext (Gemini API keys in
`ai_orchestrator.py`, the dashboard password in `ai_dashboard.py`). The
copies in `live/` here have those values replaced with
`__REDACTED__` placeholders. **They will not work as-is.** After pulling
them, put your own keys/password back in before running them on the hub.
Never commit the real values to GitHub.

## Pulling a patch on the hub

```bash
curl -o patch_<name>.py 'https://raw.githubusercontent.com/Beerssam/Projects/main/allstar-ai-hub/patches/patch_<name>.py'
sudo python3 patch_<name>.py
sudo systemctl restart ai_orchestrator.service   # or ai_dashboard.service
```

## Rollback

- Orchestrator: `/home/asl/backups/20261122/ai_orchestrator.py`
- Dashboard: `/home/asl/backups/20261123/ai_dashboard.py`

Copy the backup back over the live file and restart the matching service.

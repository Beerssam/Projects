#!/usr/bin/env python3
"""Stage 1 patch for /home/asl/ai_orchestrator.py (AllStar AI hub, node 625731).

What it changes (all in ai_orchestrator.py):
  1. Beep trim - cuts the trailing ~250 ms courtesy tone (ct8) off each clip.
  2. Whisper gate - local Whisper transcribes each clip first; empty/noise/
     own-voice clips are dropped WITHOUT calling Gemini. Fails OPEN.
  3. Echo window 8.0s -> 3.0s (REPEATER_TAIL_GUARD), now only a backstop.
  4. ADS-B summary cached 3 minutes (was fetched fresh every transmission).
  5. Gemini timeout 25s -> 10s (keeps the 4-key rotation).
  6. Short-clip floor 20000 -> 8000 bytes, and logs when it drops one.
  7. File-stability wait 3s -> 1.5s (6 polls -> 3 polls).
  8. Log-only AMI observer thread (proves RX/TX events work; never affects
     the main loop; reads the admin secret from manager.conf at runtime).
  9. Tracks the last played reply text (for the gate's echo check).

SAFETY:
- Refuses to run unless the verified backup exists at
  /home/asl/backups/20261122/ai_orchestrator.py
- Every edit asserts its target line exists exactly once; if any check
  fails, NOTHING is written.
- Writes to a temp file, syntax-checks it with py_compile, and only then
  replaces the original.
- Rollback: cp /home/asl/backups/20261122/ai_orchestrator.py \
               /home/asl/ai_orchestrator.py
            sudo systemctl restart ai_orchestrator.service

Run as root (or with sudo):  sudo python3 patch_stage1.py
Then restart the service:    sudo systemctl restart ai_orchestrator.service
Then watch the log:          tail -f /var/log/ai_orchestrator.log
"""
import os
import shutil
import sys
import py_compile

TARGET = "/home/asl/ai_orchestrator.py"
BACKUP = "/home/asl/backups/20261122/ai_orchestrator.py"
TMP = "/tmp/ai_orchestrator_stage1.py"


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

    def replace_line(marker, block, what):
        i = find(marker, what)
        lines[i:i + 1] = block_lines(block)
        print("  ok: " + what)

    print("Patching " + TARGET + " ...")
    # 1. Echo window 6.0 -> 3.0 (backstop only now; Whisper gate catches our voice by content)
    replace_token("REPEATER_TAIL_GUARD = 6.0", "6.0", "3.0", "echo window 6.0 -> 3.0")
    # 2. Short-clip floor 20000 -> 8000
    replace_token("MIN_FILE_SIZE_BYTES = 20000", "20000", "8000", "size floor 20000 -> 8000")
    # 3. Stability wait 6 -> 3 polls (3s -> 1.5s)
    replace_token("if stable_count >= 6", ">= 6", ">= 3", "stability wait 6 -> 3 polls")
    # 4. Gemini timeout 25 -> 10
    replace_token("timeout=25", "timeout=25", "timeout=10", "Gemini timeout 25 -> 10")
    # 5. Track last reply text (for the Whisper gate's echo check)
    replace_token('"current_key_idx": 0', '"current_key_idx": 0', '"current_key_idx": 0,', "global_state comma")
    insert_after('"current_key_idx": 0,', '    "last_ai_reply": ""', "global_state last_ai_reply")
    # 6. ADS-B cache variables, before get_nearby_flights
    insert_before("def get_nearby_flights():", r"""
_adsb_cache = {"ts": 0.0, "text": ""}
ADSB_CACHE_TTL = 180  # seconds - reuse the plane summary for 3 minutes
""", "ADS-B cache vars")
    # 7. ADS-B cache check at the top of get_nearby_flights
    insert_before('url = f"https://opendata.adsb.fi', r"""
    if time.time() - _adsb_cache["ts"] < ADSB_CACHE_TTL and _adsb_cache["text"]:
        return _adsb_cache["text"]
""", "ADS-B cache check")
    # 8. ADS-B cache store (empty result)
    insert_before('"No aircraft currently in range."', r"""
                _adsb_cache["ts"] = time.time()
                _adsb_cache["text"] = result
""", "ADS-B cache store (empty)")
    # 9. ADS-B cache store (success)
    insert_before("Injected summary.", r"""
            _adsb_cache["ts"] = time.time()
            _adsb_cache["text"] = result
""", "ADS-B cache store (success)")
    # 10. Size guard now logs when it drops a clip
    insert_after("if file_bytes < MIN_FILE_SIZE_BYTES:", r"""
                        ts_log("SIZE SAFEGUARD", f"Dropped short clip (<{MIN_FILE_SIZE_BYTES} bytes): {filename}")
""", "size guard logging")
    # 11. Echo guard uses the constant (was hardcoded 8.0); update its comment too
    replace_token("Increased window look-back to 8.0s", "Increased window look-back to 8.0s to definitively trap slow disk flushing from system IDs", "Short window is now only a backstop - the Whisper gate catches our own voice by content", "echo guard comment")
    replace_token('global_state["ai_finished_at"] + 8.0', "8.0", "REPEATER_TAIL_GUARD", "echo guard uses constant")
    # 12. Track the last played reply in play_to_node
    insert_before('"Hand-off complete. Squelch tail guard protection engaged."', r"""
        global_state["last_ai_reply"] = text
""", "track last played reply")
    # 13. New functions (beep trim, Whisper gate, log-only AMI observer) before process_audio
    insert_before("def process_audio(wav_path):", NEW_FUNCS, "new functions (trim, gate, AMI observer)")
    # 14. Wire trim + gate into monitor_directory
    insert_before('ts_log("MONITOR", f"Processing new clip: {filename}")', r"""
                    # 3. Trim the trailing courtesy beep, then run the local Whisper gate
                    use_path = trim_courtesy_beep(wav_path)
                    gate_ok, _gate_text = whisper_gate(use_path)
                    if not gate_ok:
                        processed_files.add(wav_path)
                        if use_path != wav_path:
                            try: os.remove(use_path)
                            except Exception: pass
                        continue
""", "wire trim + gate")
    replace_line("response_text = process_audio(wav_path)", r"""
                    response_text = process_audio(use_path)
                    if use_path != wav_path:
                        try: os.remove(use_path)
                        except Exception: pass
""", "process trimmed clip + cleanup")
    # 15. Start the AMI observer thread in __main__
    insert_before("    monitor_directory()", r"""
    import threading as _threading
    _ami_thread = _threading.Thread(target=_ami_observer, daemon=True)
    _ami_thread.start()
""", "start AMI observer thread")

    with open(TMP, "w") as f:
        f.writelines(lines)
    py_compile.compile(TMP, doraise=True)
    shutil.copyfile(TMP, TARGET)
    os.remove(TMP)
    print("PATCH OK: all edits applied and syntax-checked.")
    print("Next: sudo systemctl restart ai_orchestrator.service")
    print("Then watch: tail -f /var/log/ai_orchestrator.log")
    print("Rollback: cp " + BACKUP + " " + TARGET + " && sudo systemctl restart ai_orchestrator.service")


NEW_FUNCS = r"""
def trim_courtesy_beep(wav_path, trim_seconds=0.25):
    # Removes the trailing courtesy-tone beep (ct8, ~150 ms + tail) from a monitor WAV.
    # Returns the path to the trimmed copy in /tmp, or the original path on any failure (fail-open).
    try:
        import wave as _wave
        with _wave.open(wav_path, 'rb') as wf:
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            frames = wf.readframes(nframes)
        cut_frames = int(trim_seconds * framerate)
        if nframes <= cut_frames:
            return wav_path
        keep_frames = nframes - cut_frames
        frame_bytes = nchannels * sampwidth
        trimmed_path = "/tmp/" + os.path.basename(wav_path) + ".trim.wav"
        with _wave.open(trimmed_path, 'wb') as out:
            out.setnchannels(nchannels)
            out.setsampwidth(sampwidth)
            out.setframerate(framerate)
            out.writeframes(frames[:keep_frames * frame_bytes])
        return trimmed_path
    except Exception as e:
        ts_log("TRIM", f"Beep trim failed, using original clip: {e}")
        return wav_path

def whisper_gate(wav_path):
    # Local Whisper pre-screen. Returns (ok, transcript).
    # ok=True: clip sounds like a real human transmission - send it to Gemini.
    # ok=False: drop it (empty, noise, beep-only, or our own voice) - do NOT call Gemini.
    # Any Whisper error fails OPEN (ok=True) so a broken gate never silences the hub.
    try:
        from stt_script import transcribe as _transcribe
    except Exception as e:
        ts_log("WHISPER GATE", f"Could not load local transcriber, passing clip through: {e}")
        return True, ""
    try:
        text = (_transcribe(wav_path) or "").strip()
    except Exception as e:
        ts_log("WHISPER GATE", f"Transcription failed, passing clip through: {e}")
        return True, ""
    low = text.lower()
    if not low or low in ("[noise]", "[noise] ", "[id]", "cw", "morse", "[static]"):
        ts_log("WHISPER GATE", f"Dropped non-speech clip: {text!r}")
        return False, text
    norm = low.replace(" ", "").replace(".", "").replace(",", "")
    if "artificialintelligencehub" in norm or "aihub" in norm:
        ts_log("WHISPER GATE", f"Dropped own-voice clip: {text!r}")
        return False, text
    last_reply = (global_state.get("last_ai_reply") or "").strip().lower()
    if last_reply:
        last_norm = last_reply.replace(" ", "").replace(".", "").replace(",", "")
        if last_norm and norm == last_norm:
            ts_log("WHISPER GATE", "Dropped clip matching our last reply (echo).")
            return False, text
    ts_log("WHISPER GATE", f"Passing to Gemini, local transcript: {text!r}")
    return True, text

def _ami_observer():
    # Log-only AMI observer (background thread). Connects to the local manager
    # interface and logs RPT_RXKEYED / RPT_TXKEYED transitions so we can learn the
    # exact event format. It never affects the main loop: on any failure it logs
    # and retries, and the orchestrator keeps working from the monitor files alone.
    import socket as _socket
    buf = [b""]
    def _read_block(sock):
        while b"\r\n\r\n" not in buf[0]:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("AMI closed the connection")
            buf[0] += chunk
        block, buf[0] = buf[0].split(b"\r\n\r\n", 1)
        return block.decode(errors="replace")
    while True:
        try:
            secret = ""
            try:
                with open("/etc/asterisk/manager.conf") as _f:
                    _in_admin = False
                    for _line in _f:
                        _s = _line.strip()
                        if _s.startswith("["):
                            _in_admin = (_s.lower() == "[admin]")
                        elif _in_admin and _s.lower().startswith("secret"):
                            secret = _s.split("=", 1)[1].split(";")[0].strip()
                            break
            except Exception as _e:
                ts_log("AMI", f"Could not read manager secret: {_e}")
            if not secret:
                ts_log("AMI", "No admin secret found; observer disabled.")
                return
            sock = _socket.create_connection(("127.0.0.1", 5038), timeout=10)
            buf[0] = b""
            _read_block(sock)  # banner
            sock.sendall(b"Action: Login\r\nUsername: admin\r\nSecret: " + secret.encode() + b"\r\n\r\n")
            resp = _read_block(sock)
            if "Success" not in resp:
                ts_log("AMI", "Login failed; observer disabled.")
                sock.close()
                return
            sock.sendall(b"Action: Events\r\nEventMask: on\r\n\r\n")
            _read_block(sock)  # events response
            ts_log("AMI", "Observer connected (log-only).")
            while True:
                block = _read_block(sock)
                if "RXKEYED" in block or "TXKEYED" in block:
                    ts_log("AMI EVENT", block.replace("\r\n", " | "))
        except Exception as e:
            ts_log("AMI", f"Observer error ({e}); retrying in 10s.")
            time.sleep(10)

"""

if __name__ == "__main__":
    main()

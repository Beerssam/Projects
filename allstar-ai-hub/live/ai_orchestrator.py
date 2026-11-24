#!/usr/bin/env python3
import os
import time
import glob
import subprocess
import requests
import base64
import json
import re
from datetime import datetime
# --- CONFIGURATION ---
NODE_ID = "625731"
CALLSIGN = "KFORIZ"
STREAM_DIR = f"/var/spool/asterisk/monitor/{NODE_ID}"
# Squelch Tail Guard (Seconds)
REPEATER_TAIL_GUARD = 3.0
TX_TAIL = 1.0  # seconds the transmitter must stay unkeyed before a clip is processed
TX_WAIT_TIMEOUT = 60.0  # give up waiting after this long (fail open to old behavior)
# Geographic Center point for live ADS-B queries (Shawnee, KS)
HOME_LAT = "38.9900"
HOME_LON = "-94.7600"
ADSB_RADIUS_NM = "75"
# Target Fleet Matrix: Kansas City Missouri Police Department Aviation Unit
KCMO_POLICE_FLEET = ["N690PD", "N691PD", "N692PD"]
KANSAS_HIGHWAY_PATROL = ["N650HP", "N670HP", "N600HP", "N900HP", "N940HP", "N950HP"]
MISSOURI_HIGHWAY_PATROL = ["N93MP", "N95MP", "N79MP", "N83MP", "N86MP", "N94MP"]
# Safeguard Baselines
MIN_FILE_SIZE_BYTES = 8000
# Absolute paths for tools
PIPER_BIN = "/usr/local/bin/piper"
MODEL_PATH = "/opt/piper/en_US-amy-medium.onnx"
# --- FAILOVER REDUNDANT API KEY POOL ---
GEMINI_KEYS = [
    "__REDACTED__",
    "__REDACTED__",
    "__REDACTED__",
    "__REDACTED__"
]
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
global_state = {
    "last_fcc_id_minute": -1,
    "ai_finished_at": 0.0,
    "current_key_idx": 0,
    "last_ai_reply": "",
    "history": [],
    "last_gate_text": "",
    "tx_keyed": None,
    "tx_keyed_at": 0.0
}
def ts_log(tag, message):
    """Prints uniform console messages prepended with millisecond-accurate local timestamps."""
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d%H%M%S")  # Reverted strictly to your exact original layout
    print(f"[{now.strftime('%H:%M:%S.%f')[:-3]}] [{tag}] {message}")
# --- AUTO-RESOLVE BINARY PATHS ---
if os.path.isdir(PIPER_BIN):
    potential_bin = os.path.join(PIPER_BIN, "piper")
    if os.path.exists(potential_bin):
        PIPER_BIN = potential_bin
if not os.path.exists(MODEL_PATH):
    found_models = glob.glob("/opt/piper/**/*.onnx", recursive=True)
    if found_models:
        MODEL_PATH = found_models[0]
_adsb_cache = {"ts": 0.0, "text": ""}
ADSB_CACHE_TTL = 180  # seconds - reuse the plane summary for 3 minutes
def get_hub_health():
    """Live Pi/hub health as a short prompt block (stdlib only)."""
    try:
        with open("/proc/uptime") as _uf:
            _up_s = float(_uf.read().split()[0])
    except Exception:
        _up_s = 0.0
    _d = int(_up_s // 86400)
    _h = int((_up_s % 86400) // 3600)
    _m = int((_up_s % 3600) // 60)
    _up_str = (f"{_d}d {_h}h" if _d else (f"{_h}h {_m}m" if _h else f"{_m}m"))
    try:
        _load1 = os.getloadavg()[0]
    except Exception:
        _load1 = None
    _temp_c = None
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as _tf:
            _temp_c = int(_tf.read().strip()) / 1000.0
    except Exception:
        pass
    try:
        _st = os.statvfs("/")
        _free_gb = _st.f_bavail * _st.f_frsize / (1024 ** 3)
    except Exception:
        _free_gb = None
    _mem_gb = None
    try:
        with open("/proc/meminfo") as _mf:
            for _line in _mf:
                if _line.startswith("MemAvailable:"):
                    _mem_gb = int(_line.split()[1]) / (1024 ** 2)
                    break
    except Exception:
        pass
    _parts = [f"Pi uptime {_up_str}"]
    if _load1 is not None:
        _parts.append(f"1-min CPU load {_load1:.2f}")
    if _temp_c is not None:
        _parts.append(f"CPU temp {_temp_c:.1f} C")
    if _free_gb is not None:
        _parts.append(f"disk free {_free_gb:.0f} GB")
    if _mem_gb is not None:
        _parts.append(f"memory available {_mem_gb:.1f} GiB")
    _parts.append("AI service running")
    return (
        "HUB HEALTH (live, just now -- if asked how the hub/Pi is doing, "
        "for a status check, or about its health, answer using this data): "
        + "; ".join(_parts) + ".\n\n"
    )
def get_nearby_flights():
    """Queries adsb.fi and splits data into priority law-enforcement sections (KCMO PD, Kansas Highway Patrol, Missouri Highway Patrol) plus the 15 closest aircraft."""
    if time.time() - _adsb_cache["ts"] < ADSB_CACHE_TTL and _adsb_cache["text"]:
        return _adsb_cache["text"]
    url = f"https://opendata.adsb.fi/api/v3/lat/{HOME_LAT}/lon/{HOME_LON}/dist/{ADSB_RADIUS_NM}"
    try:
        response = requests.get(url, headers={"User-Agent": "AllStarLink-AI-Bot"}, timeout=6)
        if response.status_code == 200:
            data = response.json()
            aircraft_list = data.get("ac", [])
            if not aircraft_list:
                result = "KCMO PD Fleet Status: No active assets detected. | Kansas Highway Patrol: No active assets detected. | Missouri Highway Patrol: No active assets detected. | Closest Aircraft: None"
                _adsb_cache["ts"] = time.time()
                _adsb_cache["text"] = result
                ts_log("ADSB ENRICHMENT", "No aircraft currently in range.")
                return result
            home_lat_f = float(HOME_LAT)
            home_lon_f = float(HOME_LON)
            parsed_tracking_pool = []
            active_pd_helicopters = []
            active_khp_aircraft = []
            active_mshp_aircraft = []

            for ac in aircraft_list:
                callsign = str(ac.get("flight", ac.get("callsign", ""))).strip()
                reg = str(ac.get("r", ac.get("registration", ""))).strip()
                if not callsign or callsign.upper() == "UNK":
                    callsign = reg if reg else "UnknownReg"
                ac_type = ac.get("t", ac.get("type", "UnkType"))
                alt = ac.get("alt_baro", ac.get("altBaro", "Ground"))
                speed = ac.get("gs", ac.get("groundSpeed", "0"))
                alt_str = f"{alt}ft" if str(alt).isdigit() else str(alt)
                formatted_desc = f"{callsign} ({ac_type}) at {alt_str}, {speed}kts"
                try:
                    ac_lat = float(ac.get("lat", 0) or 0)
                    ac_lon = float(ac.get("lon", 0) or 0)
                    planar_distance_sq = (ac_lat - home_lat_f)**2 + (ac_lon - home_lon_f)**2
                except Exception:
                    planar_distance_sq = 999.0

                aircraft_node = {
                    "desc": formatted_desc,
                    "distance": planar_distance_sq
                }

                is_pd_match = any(heli in callsign.upper() or heli in reg.upper() for heli in KCMO_POLICE_FLEET)
                if is_pd_match:
                    active_pd_helicopters.append(formatted_desc)
                is_khp_match = any(reg_no in callsign.upper() or reg_no in reg.upper() for reg_no in KANSAS_HIGHWAY_PATROL)
                if is_khp_match:
                    active_khp_aircraft.append(formatted_desc)
                is_mshp_match = any(reg_no in callsign.upper() or reg_no in reg.upper() for reg_no in MISSOURI_HIGHWAY_PATROL)
                if is_mshp_match:
                    active_mshp_aircraft.append(formatted_desc)
                parsed_tracking_pool.append(aircraft_node)

            parsed_tracking_pool.sort(key=lambda x: x["distance"])
            closest_elements = [item["desc"] for item in parsed_tracking_pool[:15]]

            closest_section = "Closest Aircraft: " + (" | ".join(closest_elements) if closest_elements else "None detected.")
            pd_section = "KCMO PD Fleet Status: " + (" | ".join(active_pd_helicopters) if active_pd_helicopters else "No active assets detected.")
            khp_section = "Kansas Highway Patrol: " + (" | ".join(active_khp_aircraft) if active_khp_aircraft else "No active assets detected.")
            mshp_section = "Missouri Highway Patrol: " + (" | ".join(active_mshp_aircraft) if active_mshp_aircraft else "No active assets detected.")
            result = f"{pd_section}\n{khp_section}\n{mshp_section}\n{closest_section}"
            _adsb_cache["ts"] = time.time()
            _adsb_cache["text"] = result
            ts_log("ADSB ENRICHMENT", f"Success — {len(aircraft_list)} aircraft in range. Injected summary.")
            return result

        # Non-200 response
        ts_log("ADSB ENRICHMENT", f"Failed — HTTP {response.status_code} from adsb.fi")
        return "ADS-B telemetry data feeds are temporarily unreachable."
    except Exception as e:
        ts_log("ADSB ENRICHMENT", f"Failed — {type(e).__name__}: {str(e)}")
        return f"ADS-B Local Parse Error: {str(e)}"
def check_and_run_fcc_id():
    """Polls system time to execute an OTA identification at :00, :10, :20, :30, :40, and :50 past the hour."""
    now = datetime.now()
    current_minute = now.minute
    if current_minute % 10 == 0:
        if global_state["last_fcc_id_minute"] != current_minute:
            # --- ROBUSTNESS: hold the ID if someone is talking or just talked ---
            if global_state.get("tx_keyed"):
                return
            # If a monitor file appeared in the last 20s, a user just transmitted; hold the ID.
            try:
                _now = time.time()
                for _p in glob.glob(os.path.join(STREAM_DIR, "*.wav")):
                    if os.path.getmtime(_p) > (_now - 20.0):
                        return
            except Exception:
                pass
            ts_log("FCC CLOCK BEACON", f"Clock milestone reached (:{current_minute:02d}). Initiating broadcast station ID...")
            # --- TIGHTEN GATE: Drop active bypass file right before automated broadcast ---
            try:
                with open("/var/run/ai_dash_active", "w") as f:
                    f.write("beacon_active")
            except Exception:
                pass
            id_text = f"This is the {' '.join(CALLSIGN)}... Artificial Intelligence Hub."
            path = generate_tts(id_text)
            if path:
                play_to_node(id_text, path)
                global_state["ai_finished_at"] = time.time()
            global_state["last_fcc_id_minute"] = current_minute
def wait_for_file_stability(wav_path):
    # Stage 2: do not trust the file size until the speaker is done. The
    # transmitter must have been quiet for TX_TAIL seconds, or we wait.
    wait_for_transmission_end()
    """Loops dynamically while the user is talking until the file stops growing."""
    last_size = -1
    stable_count = 0
    while True:
        try:
            if not os.path.exists(wav_path): return False
            current_size = os.path.getsize(wav_path)
        except Exception: return False
        if current_size > last_size:
            last_size = current_size
            stable_count = 0
        elif current_size == last_size and current_size > 0:
            stable_count += 1
            if stable_count >= 2: return True
        time.sleep(0.5)
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
    if not low or low in ["noise", "[noise]", "[id]", "cw", "morse", "[static]"]:
        ts_log("WHISPER GATE", f"Dropped non-speech clip: {text!r}")
        return False, text
    norm = low.replace(" ", "").replace(".", "").replace(",", "")
    # Full phrase only: bare "ai hub" appears in normal speech (e.g. "testing the AI hub").
    if "artificialintelligencehub" in norm:
        ts_log("WHISPER GATE", f"Dropped own-voice clip: {text!r}")
        return False, text
    last_reply = (global_state.get("last_ai_reply") or "").strip().lower()
    if last_reply:
        last_norm = last_reply.replace(" ", "").replace(".", "").replace(",", "")
        if last_norm and norm == last_norm:
            ts_log("WHISPER GATE", "Dropped clip matching our last reply (echo).")
            return False, text
    ts_log("WHISPER GATE", f"Passing to Gemini, local transcript: {text!r}")
    global_state["last_gate_text"] = text
    return True, text

def _ami_observer():
    # Log-only AMI observer (background thread). Connects to the local manager
    # interface and logs RPT RXKEYED / RPT TXKEYED transitions so we can learn the
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
    def _read_line(sock):
        while b"\r\n" not in buf[0]:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("AMI closed the connection")
            buf[0] += chunk
        line, buf[0] = buf[0].split(b"\r\n", 1)
        return line.decode(errors="replace")
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
            except Exception as e:
                ts_log("AMI", f"Could not read manager secret: {_e}")
            if not secret:
                ts_log("AMI", "No admin secret found; observer disabled.")
                return
            sock = _socket.create_connection(("127.0.0.1", 5038), timeout=10)
            buf[0] = b""
            _read_line(sock)  # banner (single line, not a block)
            sock.sendall(b"Action: Login\r\nUsername: admin\r\nSecret: " + secret.encode() + b"\r\n\r\n")
            resp = _read_block(sock)
            if "Success" not in resp:
                ts_log("AMI", "Login failed; observer disabled.")
                sock.close()
                return
            sock.settimeout(None) # wait patiently...
            sock.sendall(b"Action: Events\r\nEventMask: on\r\n\r\n")
            _read_block(sock) # events response
            ts_log("AMI", "Observer connected (log-only).")
            while True:
                block = _read_block(sock)
                # Stage 2...
                if "Event: RPT_TXKEYED" in block:
                    for _ln in block.splitlines():
                        if _ln.startswith("EventValue:"):
                            global_state["tx_keyed"] = (_ln.split(":",1)[1].strip() == "1")
                            global_state["tx_keyed_at"] = time.time()
                            break
                if "RXKEYED" in block or "TXKEYED" in block:
                    ts_log("AMI EVENT", block.replace("\r\n", " | "))
        except Exception as e:
            ts_log("AMI", f"Observer error ({e}); retrying in 10s.")
            time.sleep(10)
def wait_for_transmission_end():
    # Stage 2: wait until...
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
def process_audio(wav_path):
    """Encodes transmission and requests response, cycling through keys if a 429 occurs."""
    ts_log("API", f"Encoding {os.path.basename(wav_path)} to Base64...")
    try:
        with open(wav_path, "rb") as f:
            base64_audio = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        ts_log("SCRIPT EXCEPTION", f"Failed to encode WAV file: {e}")
        return "API_ERROR: File system access error."

    # ADS-B only when the caller asks about aircraft (per Sam, Nov 23).
    # Check the local Whisper transcript (stored by whisper_gate) for
    # plane/helicopter words. Fail OPEN: if the transcript is empty
    # (Whisper failed), include the data so a plane question is never
    # missed because of a bad transcript.
    _gate_low = (global_state.get("last_gate_text") or "").lower()
    _plane_words = ("plane", "aircraft", "helicopter", "heli", "helo", "overhead", "flying", "flight", "airplane", "jet", "airport", "airspace", "kemp", "kcmo", "police", "sky", "above")
    _want_adsb = (not _gate_low) or any(w in _gate_low for w in _plane_words)
    if _want_adsb:
        adsb_snapshot = get_nearby_flights()
        adsb_block = (
            f"REAL-TIME LOCAL AIRSPACE POSITION REPOSITORY ({ADSB_RADIUS_NM} NM Radius around Shawnee, KS):\n"
            f"{adsb_snapshot}\n\n"
        )
    else:
        adsb_block = ""
    # Hub health only when the caller asks about the hub/Pi status.
    # Same pattern as ADS-B: check the Whisper transcript for health
    # words. Fail OPEN on an empty transcript so a health question is
    # never missed because of a bad transcript.
    _health_words = ("how are you", "how are you doing", "how's it going", "hows it going", "status", "status check", "health", "temperature", "temp", "uptime", "cpu", "load", "disk", "memory", "ram", "are you okay", "are you ok", "everything good", "everything ok", "everything okay", "how long")
    _want_health = (not _gate_low) or any(w in _gate_low for w in _health_words)
    if _want_health:
        health_block = get_hub_health()
    else:
        health_block = ""

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
    system_instruction = (
        "You are an AllStar Link radio node assistant processing live over-the-air audio streams. Analyze the incoming transmission.\n\n"
        f"{adsb_block}{health_block}"
        f"{_hist_text}"
        "CRITICAL MULTIMODAL AUDIO DIRECTIVE:\n"
        "1. AUTOMATED TELEMETRY / MORSE CODE (CW ID): Listen closely to the raw audio character. If the transmission consists of electronic telegraphy beeps, sinusoidal tones, or Morse code (which often transcribes audio as a raw callsign like 'KFORIZ' or scattered letters), this is an automated station identity cycle. You MUST ignore it and return empty strings (\"\") for both 'transcript' and 'reply' to suppress it completely.\n"
        "2. AUTOMATED VOICE BEACONS: If the audio is an automated robotic system announcement or playback loop from the node itself, return empty strings.\n"
        "3. HUMAN OPERATOR: If the audio contains an actual human voice speaking—even if they are just stating their callsign 'KFORIZ' to legally identify, saying a quick greeting like 'KFORIZ hello', or checking if the node is active—you MUST recognize this as a valid human transmission. Transcribe their words in 'transcript' and provide a short, conversational over-the-air radio response in 'reply' acknowledging them.\n\n"
        "GENERAL RESPONSE RULES:\n"
        "If a human asks about overhead aircraft, use the airspace repository data provided above to answer concisely.\n"
        "Keep all spoken responses brief, clean, and completely free of markdown formatting symbols like asterisks or hashtags. Answer briefly by default, but if the caller asks for a list or something that needs detail, give the full answer, do not refuse just because it is long.\n"
        "Return a valid JSON object string with exactly two keys: 'transcript' and 'reply'. Do not wrap your response in any extra text or conversation outside of the raw JSON object brackets."
    )
    payload = {
        "contents": [{
            "parts": [
                {"text": system_instruction},
                {"inlineData": {"mimeType": "audio/wav", "data": base64_audio}}
            ]
        }],
        "tools": [{"google_search": {}}]
    }
    for attempt in range(len(GEMINI_KEYS)):
        active_idx = global_state["current_key_idx"]
        active_key = GEMINI_KEYS[active_idx]
        ts_log("API", f"Submitting audio using Key Pool Index [{active_idx}]...")
        try:
            response = requests.post(f"{API_URL}?key={active_key}", json=payload, timeout=25)
            res_json = response.json()
            if response.status_code in [429, 503]:
                ts_log("FAILOVER ENGINE", f"Key Index [{active_idx}] met error code {response.status_code}. Cycling context to next key index...")
                global_state["current_key_idx"] = (active_idx + 1) % len(GEMINI_KEYS)
                time.sleep(1.5)
                continue
            if "error" in res_json:
                error_code = res_json["error"].get("code", "Unknown")
                if error_code in [429, 503]:
                    ts_log("FAILOVER ENGINE", f"Key Index [{active_idx}] payload reported error {error_code}. Cycling key context...")
                    global_state["current_key_idx"] = (active_idx + 1) % len(GEMINI_KEYS)
                    time.sleep(1.5)
                    continue
                return f"API ERROR: System error {error_code}."
            raw_text = res_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '').strip()
            cleaned_text = raw_text
            start_idx = cleaned_text.find("{")
            end_idx = cleaned_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                cleaned_text = cleaned_text[start_idx:end_idx+1]
            try:
                parsed_data = json.loads(cleaned_text)
                user_transcript = parsed_data.get("transcript", "")
                ai_reply = parsed_data.get("reply", "")
                match_transcript = user_transcript.strip().lower().replace(" ", "").replace(".", "")
                # Full phrase only: bare "ai hub" appears in normal speech (e.g. "testing the AI hub").
                if "artificialintelligencehub" in match_transcript:
                    ts_log("SAFEGUARD", f"Dropped self-identity voice loops: \"{user_transcript}\"")
                    return None
                print(f"\n============================================================\n")
                ts_log("RADIO INTERPRETATION", f"Heard: \"{user_transcript}\"")
                ts_log("GEMINI RESPONSE", f"Saying: \"{ai_reply}\"")
                print(f"============================================================\n")
                if not ai_reply or user_transcript.strip().lower() in ["", "[noise]", "[noise] ", "[id]", "cw", "morse", "[static]"]:
                    ts_log("SAFEGUARD", "No actionable human speech parsed. Dropping transmission response.")
                    return None
                # Remember this exchange (cap at 5) so follow-ups can refer back to it.
                _h = global_state.setdefault("history", [])
                _h.append((user_transcript, ai_reply))
                del _h[:-5]
                return ai_reply
            except json.JSONDecodeError:
                return raw_text
        except requests.exceptions.RequestException as e:
            ts_log("NETWORK ERROR", f"HTTP connection drop on index [{active_idx}]: {e}")
            global_state["current_key_idx"] = (active_idx + 1) % len(GEMINI_KEYS)
            time.sleep(1.5)
            continue
    ts_log("CRITICAL ERROR", "All API keys in the redundancy pool returned resource exhaustion errors.")
    return "API_ERROR: Full pool exhaustion."
def generate_tts(text):
    """Compiles text via Piper at 22kHz, then downsamples using FFmpeg to 8kHz Mono for Asterisk."""
    try:
        timestamp = int(time.time())
        output_wav = f"/var/lib/asterisk/sounds/ai_resp_{timestamp}.wav"
        temp_wav = "/tmp/piper_raw.wav"
        if os.path.exists(temp_wav): os.remove(temp_wav)
        ts_log("TTS", f"Compiling voice via Piper: '{text}'")
        echo_proc = subprocess.Popen(["echo", text], stdout=subprocess.PIPE)
        piper_proc = subprocess.Popen(
            [PIPER_BIN, "--model", MODEL_PATH, "--output_file", temp_wav], stdin=echo_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        echo_proc.stdout.close()
        piper_proc.communicate()
        if piper_proc.returncode == 0 and os.path.exists(temp_wav):
            ts_log("TTS", "Downsampling audio to 8kHz Mono PCM via FFmpeg for AllStar Link compliance...")
            ffmpeg_cmd = ["ffmpeg", "-y", "-i", temp_wav, "-ar", "8000", "-ac", "1", output_wav]
            subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            os.chmod(output_wav, 0o644)
            return output_wav
        return None
    except Exception as e:
        ts_log("SCRIPT EXCEPTION", f"Failed during TTS generation/resampling: {e}")
        return None
def play_to_node(text, wav_path):
    # Stop the self-talk loop: mark our own playback so the main loop drops
    # its self-recording via DASHBOARD BYPASS instead of hearing it as a
    # new transmission. (Beacons already do this; replies did not, so the
    # gate's exact-match check was the only guard, and Whisper's small
    # transcription differences let our own reply through.)
    try:
        open("/var/run/ai_dash_active", "w").close()
    except Exception:
        pass
    """Passes audio to Asterisk via 'playback' and tracks precise execution completion."""
    if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 100:
        ts_log("ALLSTAR SAFETY", "Playback ABORTED: Valid WAV file not found. Ghost audio prevented.")
        return
    try:
        file_base = os.path.splitext(wav_path)[0]
        audio_duration = 0.0
        try:
            import wave
            with wave.open(wav_path, 'rb') as wf:
                audio_duration = wf.getnframes() / float(wf.getframerate())
        except Exception:
            audio_duration = len(text) * 0.08
        cmd = ["asterisk", "-rx", f"rpt playback {NODE_ID} {file_base}"]
        ts_log("ALLSTAR", f"Executing OTA playback: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        ts_log("ALLSTAR", f"Transmission broadcasting. Holding thread for {audio_duration:.1f}s...")
        time.sleep(audio_duration)
        global_state["ai_finished_at"] = time.time()
        global_state["last_ai_reply"] = text
        ts_log("ALLSTAR", "Hand-off complete. Squelch tail guard protection engaged.")
    except Exception as e:
        ts_log("ALLSTAR ERROR", f"Playback injection failed: {e}")
def monitor_directory():
    """Main loop checking for closed incoming audio streams from the node monitor."""
    ts_log("MONITOR", f"Watching: {STREAM_DIR}")
    ts_log("MONITOR", "System online. Press Ctrl+C to exit safely.")
    processed_files = set(glob.glob(os.path.join(STREAM_DIR, "*.wav")))
    while True:
        try:
            check_and_run_fcc_id()
            current_files = glob.glob(os.path.join(STREAM_DIR, "*.wav"))
            for wav_path in current_files:
                if wav_path in processed_files: continue
                if wait_for_file_stability(wav_path):
                    filename = os.path.basename(wav_path)
                    file_creation_time = os.path.getmtime(wav_path)
                    # 1. Size Safeguard
                    file_bytes = os.path.getsize(wav_path)
                    if file_bytes < MIN_FILE_SIZE_BYTES:
                        ts_log("SIZE SAFEGUARD", f"Dropped short clip (<{MIN_FILE_SIZE_BYTES} bytes): {filename}")
                        processed_files.add(wav_path)
                        continue
                    # 2. Re-applied Squelch Tail / Echo Safeguard with Dashboard State Overrides
                    # A bypass flag only drops a file that started within 12s of the flag
                    # being set (our own playback). A file created well after the flag is
                    # a real user transmission, so it is NOT dropped here.
                    is_dashboard_id = False
                    for _flag in ["/tmp/ai_dash_cooldown", "/var/run/ai_dash_active"]:
                        if os.path.exists(_flag):
                            try:
                                _flag_time = os.path.getmtime(_flag)
                            except Exception:
                                _flag_time = 0.0
                            if file_creation_time < (_flag_time + 12.0):
                                is_dashboard_id = True
                                break
                    # Short window is now only a backstop - the Whisper gate catches our own voice by content
                    if file_creation_time < (global_state["ai_finished_at"] + REPEATER_TAIL_GUARD) or is_dashboard_id:
                        tag = "ECHO SAFEGUARD" if not is_dashboard_id else "DASHBOARD BYPASS"
                        ts_log(tag, f"Dropped self-recorded playback/squelch tail file: {filename}")
                        # Clean up persistence flags safely
                        for flag_file in ["/tmp/ai_dash_cooldown", "/var/run/ai_dash_active"]:
                            if os.path.exists(flag_file):
                                try: os.remove(flag_file)
                                except Exception: pass
                        processed_files.add(wav_path)
                        continue
                    # 3. Trim the trailing courtesy beep, then run the local Whisper gate
                    use_path = trim_courtesy_beep(wav_path)
                    gate_ok, _gate_text = whisper_gate(use_path)
                    if not gate_ok:
                        processed_files.add(wav_path)
                        if use_path != wav_path:
                            try: os.remove(use_path)
                            except Exception: pass
                        continue
                    ts_log("MONITOR", f"Processing new clip: {filename}")
                    response_text = process_audio(use_path)
                    if use_path != wav_path:
                        try: os.remove(use_path)
                        except Exception: pass
                    if response_text:
                        if response_text.startswith("API_ERROR:"):
                            spoken_error = response_text.replace("API_ERROR:", "System notice. ")
                            path = generate_tts(spoken_error)
                            if path: play_to_node(spoken_error, path)
                        else:
                            path = generate_tts(response_text)
                            if path: play_to_node(response_text, path)
                    processed_files.add(wav_path)
            time.sleep(1)
        except KeyboardInterrupt:
            ts_log("MONITOR", "Closing down audio orchestrator safely via interrupt.")
            break
        except Exception as e:
            ts_log("LOOP ERROR", f"Error in runtime thread: {e}")
            time.sleep(2)
if __name__ == "__main__":
    os.makedirs(STREAM_DIR, exist_ok=True)
    import threading as _threading
    _ami_thread = _threading.Thread(target=_ami_observer, daemon=True)
    _ami_thread.start()
    monitor_directory()

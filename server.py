#!/usr/bin/env python3
"""
Majority Radio Web Controller
Controls Majority Pembroke radio via the Magic iRadio REST API (port 80).
Run: python server.py  →  open http://localhost:5000
"""

import json
import logging
import os
import socket
import threading
import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = "majority-radio-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

RADIO_PORT = 80
RADIO_MEDIA_PORT = 8080   # album art / playlogo.jpg served on a separate port
RADIO_AUTH = ("su3g4go6sk7", "ji39454xu/^")  # default Magic iRadio credentials
RADIO_UDP_PORT = 38899
POLL_INTERVAL = 3            # seconds between status polls (3s keeps radio responsive)
INIT_REFRESH_INTERVAL = 30   # seconds between /init refreshes (station name + mode)
PLAYINFO_INTERVAL = 12       # seconds between /playinfo polls (often FAIL; poll infrequently)
ART_CHECK_INTERVAL = 6       # seconds between album art hash checks
MAX_VOL = 20                 # maximum volume for /setvol
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

# Circuit breaker thresholds
CB_FAIL_THRESHOLD = 4        # consecutive poller failures before backing off
CB_BACKOFF_SHORT  = 15       # seconds to back off after first trip
CB_BACKOFF_LONG   = 45       # seconds to back off after repeated trips


# ── Config persistence ─────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load saved settings from config.json (IP, auto-connect flag)."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"ip": "", "auto_connect": False}


def save_config(cfg: dict):
    """Persist settings to config.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError as e:
        log.warning("Could not save config: %s", e)

state = {
    "ip": None,
    "connected": False,
    "last_status": {},
    "hotkeys": [],           # cached preset list: [{"id": "75_256", "name": "BG Radio"}, ...]
    "cur_play_name": "",     # current station name from /init
    "cur_play_menu_id": "",  # current menu id from /init (used as root for station browser)
    "browse_stack": [],      # navigation stack for station browser: list of {"id", "title"}
    "albumart_hash": None,   # last seen hash of playlogo.jpg (used for change detection)
    # Circuit breaker: pause polling when radio returns consecutive errors
    "fail_count":     0,     # consecutive failed poller requests
    "backoff_until":  0.0,   # epoch time; poller skips until this time passes
}

# Maps UI command names → (REST path, extra query params)
# VolumeUp / VolumeDown / Mute are handled separately via /setvol
COMMAND_MAP = {
    "PlayPause":  ("playControl",  {"play": "1"}),
    "Previous":   ("goBackward",   {}),
    "Next":       ("goForward",    {}),
}


# ── HTTP Helpers ───────────────────────────────────────────────────────────────

def _looks_like_xml(text: str) -> bool:
    """Quick check: radio XML always starts with <?xml or <result or <menu."""
    t = text.lstrip()
    return t.startswith("<") and not t.lower().startswith("<!doctype") and "<html" not in t.lower()


def get_from_radio(path: str, retries: int = 1, **params) -> Optional[str]:
    """Send a GET request to the radio REST API with Basic Auth.
    Returns None on timeout, HTTP error, or when the radio returns an HTML error
    page instead of XML (happens when the radio is overloaded / in error state).
    Callers must also check for FAIL/NO_SUPPORT in the returned text.
    """
    ip = state["ip"]
    if not ip:
        return None
    url = f"http://{ip}:{RADIO_PORT}/{path}"
    for attempt in range(1 + retries):
        try:
            resp = requests.get(
                url,
                params=params or None,
                auth=RADIO_AUTH,
                headers={"Accept": "text/xml", "Connection": "close"},
                timeout=4,
            )
            log.debug("GET /%s %s → HTTP %s", path, params, resp.status_code)
            if not resp.ok:
                log.warning("Radio HTTP %s for /%s: %.200s", resp.status_code, path, resp.text[:120])
                return None
            text = resp.text
            # Radio sometimes returns an HTML error page when overloaded
            if not _looks_like_xml(text):
                log.warning("Radio returned non-XML on /%s (overloaded?): %.80s", path, text[:80])
                return None
            return text
        except requests.Timeout:
            if attempt < retries:
                log.warning("Timeout on /%s (attempt %d), retrying…", path, attempt + 1)
            else:
                log.warning("Timeout on /%s after %d attempt(s)", path, attempt + 1)
        except requests.RequestException as e:
            log.warning("Radio HTTP error on /%s: %s", path, e)
            return None
    return None


def _cmd_result(resp: Optional[str], *, cmd: str = "") -> tuple[bool, str]:
    """Interpret a radio response and return (success, reason).
    success=False when resp is None (timeout/error) or contains FAIL/NO_SUPPORT.
    """
    if resp is None:
        return False, "timeout_or_no_response"
    if "FAIL" in resp:
        return False, "device_returned_FAIL"
    if "NO_SUPPORT" in resp:
        return False, "device_returned_NO_SUPPORT"
    return True, "ok"



def parse_xml(xml_text: str) -> dict:
    """Parse radio XML response into a flat dict. Keeps _raw for debug."""
    try:
        root = ET.fromstring(xml_text)
        result = {child.tag: (child.text or "") for child in root}
        result["_raw"] = xml_text
        return result
    except ET.ParseError:
        return {"_raw": xml_text, "_parse_error": "true"}


def _radio_reachable(ip: str) -> bool:
    """TCP connectivity check on the radio's HTTP port."""
    try:
        with socket.create_connection((ip, RADIO_PORT), timeout=2):
            pass
        return True
    except OSError:
        return False


def get_albumart_bytes() -> Optional[bytes]:
    """Fetch album art from the radio's media port (8080). Returns raw bytes or None."""
    ip = state["ip"]
    if not ip:
        return None
    try:
        resp = requests.get(
            f"http://{ip}:{RADIO_MEDIA_PORT}/playlogo.jpg",
            auth=RADIO_AUTH,
            timeout=3,
            stream=False,
        )
        if resp.ok and resp.content:
            return resp.content
        return None
    except requests.RequestException:
        return None


def _emit_status():
    """Broadcast the current tracked state to all connected WebSocket clients."""
    socketio.emit("status", state["last_status"])


def _merge_status(**fields):
    """Update last_status with given fields and emit via WebSocket."""
    state["last_status"].update(fields)
    _emit_status()


# ── Hotkey / Preset cache ──────────────────────────────────────────────────────

def _refresh_hotkeys():
    """Fetch /hotkeylist and cache preset IDs in state["hotkeys"]."""
    xml_text = get_from_radio("hotkeylist")
    if not xml_text:
        return
    try:
        root = ET.fromstring(xml_text)
        hotkeys = []
        for item in root.findall("item"):
            id_el   = item.find("id")
            name_el = item.find("name")
            if id_el is not None:
                hotkeys.append({
                    "id":   (id_el.text or "").strip(),
                    "name": (name_el.text or "").strip() if name_el is not None else "",
                })
        state["hotkeys"] = hotkeys
        log.info("Cached %d hotkeys", len(hotkeys))
    except ET.ParseError as e:
        log.warning("Failed to parse hotkeylist: %s", e)


# ── Background Status Poller ───────────────────────────────────────────────────

def status_poller():
    """Poll the radio at POLL_INTERVAL seconds.

    Request budget per cycle (worst case):
      Every 3s  → /background_play_status  (1 req, no retry)
      Every 6s  → /playlogo.jpg art check   (1 req, no retry)
      Every 12s → /playinfo                 (1 req, no retry — often FAIL on j327)
      Every 30s → /init                     (1 req, no retry)
      FM only   → /GetFMStatus every 3s     (1 req, no retry)

    retries=0 on all poller calls — a missed poll is acceptable;
    retries are reserved for user-initiated commands where failure matters.
    """
    last_init_time  = 0.0
    last_art_time   = 0.0
    last_pi_time    = 0.0

    while True:
        if state["connected"] and state["ip"]:
            now = time.time()

            # ── Circuit breaker: pause polling when radio is overwhelmed ──────
            if now < state["backoff_until"]:
                remaining = int(state["backoff_until"] - now)
                log.debug("Circuit breaker active — backing off %ds more", remaining)
                time.sleep(POLL_INTERVAL)
                continue

            cycle_ok = False   # set True if at least one poll request succeeds

            # ── /init (every 30s): station name + play mode ──────────────────
            if now - last_init_time >= INIT_REFRESH_INTERVAL:
                init_resp = get_from_radio("init", retries=0, language="en")
                if init_resp:
                    cycle_ok = True
                    info = parse_xml(init_resp)
                    if info.get("rt") != "NO_SUPPORT":
                        state["cur_play_name"] = info.get("cur_play_name", state["cur_play_name"])
                        state["cur_play_menu_id"] = info.get("cur_play_menu_id", state["cur_play_menu_id"])
                        play_mode = info.get("PlayMode", "")
                        if play_mode:
                            state["last_status"].setdefault("Mode", play_mode)
                last_init_time = now

            # ── /background_play_status (every cycle): vol + mute ────────────
            bg_resp = get_from_radio("background_play_status", retries=0)
            if bg_resp and "FAIL" not in bg_resp and "NO_SUPPORT" not in bg_resp:
                cycle_ok = True
                bg = parse_xml(bg_resp)
                if "vol" in bg:
                    state["last_status"]["vol"] = bg["vol"]
                if "mute" in bg:
                    state["last_status"]["mute"] = bg["mute"]

            # ── /playinfo (every 12s): play status + stream format ───────────
            # Polled infrequently because it returns FAIL on most requests on j327.
            if now - last_pi_time >= PLAYINFO_INTERVAL:
                pi_resp = get_from_radio("playinfo", retries=0)
                if pi_resp and "FAIL" not in pi_resp and "NO_SUPPORT" not in pi_resp:
                    cycle_ok = True
                    pi = parse_xml(pi_resp)
                    for field in ("status", "stream_format", "Bitrate", "SongTitle", "StationName"):
                        if field in pi and pi[field]:
                            state["last_status"][field] = pi[field]
                last_pi_time = now

            # ── /GetFMStatus (every cycle, FM only): freq + signal + RDS ─────
            current_mode = str(state["last_status"].get("Mode", ""))
            if current_mode == "2":
                fm_resp = get_from_radio("GetFMStatus", retries=0)
                if fm_resp and "FAIL" not in fm_resp and "NO_SUPPORT" not in fm_resp:
                    cycle_ok = True
                    fm = parse_xml(fm_resp)
                    for field in ("Freq", "Signal", "Sound", "RDS", "Search"):
                        if field in fm:
                            state["last_status"][field] = fm[field]
                    if "vol" in fm:
                        state["last_status"]["vol"] = fm["vol"]
                    if "mute" in fm:
                        state["last_status"]["mute"] = fm["mute"]

            # ── Album art hash (every 6s): detect station changes ─────────────
            if now - last_art_time >= ART_CHECK_INTERVAL:
                art = get_albumart_bytes()
                if art:
                    cycle_ok = True
                    art_hash = hash(art)
                    if art_hash != state["albumart_hash"]:
                        state["albumart_hash"] = art_hash
                        log.info("Album art changed — station changed (hash=%s)", art_hash)
                        state["last_status"]["_art_changed"] = str(art_hash)
                last_art_time = now

            # ── Circuit breaker: count consecutive all-failed cycles ──────────
            if cycle_ok:
                if state["fail_count"] > 0:
                    log.info("Radio recovered after %d failed cycle(s)", state["fail_count"])
                state["fail_count"] = 0
                socketio.emit("radio_health", {"ok": True})
            else:
                state["fail_count"] += 1
                log.warning("Poll cycle %d: all requests failed", state["fail_count"])
                if state["fail_count"] >= CB_FAIL_THRESHOLD:
                    trips = state["fail_count"] // CB_FAIL_THRESHOLD
                    backoff = CB_BACKOFF_SHORT if trips == 1 else CB_BACKOFF_LONG
                    state["backoff_until"] = time.time() + backoff
                    log.warning("Circuit breaker tripped (trip #%d) — pausing %ds", trips, backoff)
                    socketio.emit("radio_health", {"ok": False, "backoff": backoff,
                                                   "msg": f"Radio overloaded — pausing {backoff}s"})

            state["last_status"]["cur_play_name"] = state["cur_play_name"]
            state["last_status"].pop("_raw", None)
            _emit_status()
        else:
            if state["ip"] and not _radio_reachable(state["ip"]):
                state["connected"] = False
                socketio.emit("disconnected", {})
        time.sleep(POLL_INTERVAL)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/connect", methods=["POST"])
def api_connect():
    data = request.get_json(force=True)
    ip = (data.get("ip") or "").strip()
    if not ip:
        return jsonify(error="IP address required"), 400

    state["ip"] = ip
    state["connected"] = False
    # Reset circuit breaker on fresh connect
    state["fail_count"] = 0
    state["backoff_until"] = 0.0

    # Use /init to verify the radio is reachable and get device info
    resp = get_from_radio("init", language="en")
    if resp is None:
        if not _radio_reachable(ip):
            return jsonify(error=f"No response from {ip}:{RADIO_PORT}"), 502
        state["connected"] = True
        log.info("Connected to radio at %s (init not supported)", ip)
        return jsonify(ok=True, status={})

    device_info = parse_xml(resp)
    state["connected"] = True
    state["cur_play_name"] = device_info.get("cur_play_name", "")
    state["cur_play_menu_id"] = device_info.get("cur_play_menu_id", "")
    log.info("Connected to radio at %s — firmware %s", ip, device_info.get("version", "?"))

    # Seed the status with a real /playinfo call (may return NO_SUPPORT/FAIL on some firmware)
    status_resp = get_from_radio("playinfo")
    status = {}
    if status_resp:
        parsed = parse_xml(status_resp)
        real_fields = [k for k in parsed if not k.startswith("_")]
        if real_fields and parsed.get("rt") != "NO_SUPPORT":
            status = parsed
            status["cur_play_name"] = state["cur_play_name"]
            status["cur_play_menu_id"] = state["cur_play_menu_id"]

    # Read current vol+mute from /background_play_status (reliable on this firmware)
    bg_resp = get_from_radio("background_play_status")
    if bg_resp:
        bg = parse_xml(bg_resp)
        if "vol" in bg:
            status["vol"] = bg["vol"]
            status["mute"] = bg.get("mute", "0")
            log.info("Initial volume: %s (mute=%s)", bg["vol"], bg.get("mute", "0"))

    # Inject PlayMode from /init as the initial source mode
    play_mode = device_info.get("PlayMode", "")
    if play_mode and "Mode" not in status:
        status["Mode"] = play_mode

    status["cur_play_name"] = state["cur_play_name"]
    status["cur_play_menu_id"] = state["cur_play_menu_id"]
    state["last_status"] = status

    # Cache preset list in background so it's ready for preset buttons
    threading.Thread(target=_refresh_hotkeys, daemon=True).start()

    return jsonify(ok=True, status=status, device=device_info)


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    state["ip"] = None
    state["connected"] = False
    state["last_status"] = {}
    state["hotkeys"] = []
    state["cur_play_name"] = ""
    state["cur_play_menu_id"] = ""
    return jsonify(ok=True)


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """UDP broadcast scan. Works only if the network allows broadcast packets."""
    found = []
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(3)
        # Probe with a lightweight GET-style ping packet
        s.sendto(b"GET /init HTTP/1.0\r\n\r\n", ("<broadcast>", RADIO_UDP_PORT))
        while True:
            try:
                _, addr = s.recvfrom(1024)
                found.append(addr[0])
            except socket.timeout:
                break
    except OSError as e:
        log.warning("UDP scan error: %s", e)
    finally:
        if s:
            s.close()
    return jsonify(found=list(set(found)))


@app.route("/api/command", methods=["POST"])
def api_command():
    data = request.get_json(force=True)
    command = data.get("command")
    if not command:
        return jsonify(error="command required"), 400
    if not state["ip"]:
        return jsonify(error="Not connected to radio"), 409

    # ── VolumeUp ──────────────────────────────────────────────────────────────
    if command == "VolumeUp":
        cur_vol = int(state["last_status"].get("vol", 10) or 10)
        new_vol = min(MAX_VOL, cur_vol + 1)
        resp = get_from_radio("setvol", vol=new_vol, mute=0)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"VolumeUp failed: {reason}"), 502
        confirmed = parse_xml(resp)
        actual_vol = confirmed.get("vol", str(new_vol))
        log.info("VolumeUp %d → %d", cur_vol, int(actual_vol))
        _merge_status(vol=actual_vol, mute="0")
        return jsonify(ok=True, vol=actual_vol, mute=0, raw=resp)

    # ── VolumeDown ────────────────────────────────────────────────────────────
    if command == "VolumeDown":
        cur_vol = int(state["last_status"].get("vol", 10) or 10)
        new_vol = max(0, cur_vol - 1)
        resp = get_from_radio("setvol", vol=new_vol, mute=0)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"VolumeDown failed: {reason}"), 502
        confirmed = parse_xml(resp)
        actual_vol = confirmed.get("vol", str(new_vol))
        log.info("VolumeDown %d → %d", cur_vol, int(actual_vol))
        _merge_status(vol=actual_vol, mute="0")
        return jsonify(ok=True, vol=actual_vol, mute=0, raw=resp)

    # ── Mute (toggle) ─────────────────────────────────────────────────────────
    if command == "Mute":
        cur_mute = int(state["last_status"].get("mute", 0) or 0)
        new_mute = 0 if cur_mute else 1
        cur_vol = int(state["last_status"].get("vol", 10) or 10)
        resp = get_from_radio("setvol", vol=cur_vol, mute=new_mute)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"Mute failed: {reason}"), 502
        confirmed = parse_xml(resp)
        actual_mute = confirmed.get("mute", str(new_mute))
        log.info("Mute toggle → mute=%s", actual_mute)
        _merge_status(mute=actual_mute)
        return jsonify(ok=True, mute=actual_mute, raw=resp)

    # ── SwitchMode ────────────────────────────────────────────────────────────
    # /switchMode returns NO_SUPPORT on firmware j327. We navigate via gochild.
    # Menu IDs confirmed from reverse engineering:
    #   0/1 = Internet Radio (id=52), 2 = FM (id=5), 3 = DAB (id=91)
    #   4 = Bluetooth (id=104), 5 = AUX (id=47)
    MODE_MENU_IDS = {"0": "52", "1": "52", "2": "5", "3": "91", "4": "104", "5": "47"}
    MODE_NAMES    = {"0": "Internet Radio", "1": "Internet Radio", "2": "FM",
                     "3": "DAB+", "4": "Bluetooth", "5": "AUX"}
    if command == "SwitchMode":
        mode = str(data.get("Mode", data.get("mode", 0)))
        menu_id = MODE_MENU_IDS.get(mode)
        if not menu_id:
            return jsonify(ok=False, error=f"Unknown mode {mode}"), 400
        nav_resp = get_from_radio("gochild", id=menu_id)
        ok, reason = _cmd_result(nav_resp, cmd=command)
        mode_name = MODE_NAMES.get(mode, f"Mode {mode}")
        log.info("SwitchMode mode=%s (%s) → gochild id=%s → %s", mode, mode_name, menu_id, reason)
        if not ok:
            return jsonify(ok=False, error=f"SwitchMode failed: {reason}", raw=nav_resp), 502
        _merge_status(Mode=mode)
        return jsonify(ok=True, mode=mode, name=mode_name,
                       note=f"Switched to {mode_name} (menu id={menu_id})")

    # ── PlayFavorite (hotkey by 1-based index via /playhotkey?key=N) ─────────────
    if command == "PlayFavorite":
        index = int(data.get("Index", data.get("index", 1)))
        hotkeys = state["hotkeys"]
        if not hotkeys:
            _refresh_hotkeys()
            hotkeys = state["hotkeys"]
        entry = hotkeys[index - 1] if hotkeys and 0 < index <= len(hotkeys) else None
        name = entry["name"] if entry else f"Preset {index}"
        resp = get_from_radio("playhotkey", key=index)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"PlayFavorite failed: {reason}"), 502
        log.info("PlayFavorite #%d → %s", index, name)
        confirmed = parse_xml(resp)
        merge_fields = {"cur_play_name": name}
        if "vol" in confirmed:
            merge_fields["vol"] = confirmed["vol"]
        if "mute" in confirmed:
            merge_fields["mute"] = confirmed["mute"]
        state["cur_play_name"] = name
        _merge_status(**merge_fields)
        return jsonify(ok=True, raw=resp, name=name)

    if command == "SetFMFreq":
        freq = str(data.get("freq", data.get("Freq", ""))).strip()
        if not freq:
            return jsonify(error="freq required"), 400
        resp = get_from_radio("SetFMFreq", freq=freq)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"SetFMFreq failed: {reason}", raw=resp), 502
        log.info("SetFMFreq → %s MHz", freq)
        _merge_status(Freq=freq, Mode="2")
        return jsonify(ok=True, freq=freq, raw=resp)

    if command == "FMTuneUp":
        resp = get_from_radio("Sendkey", key=2)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"FMTuneUp failed: {reason}", raw=resp), 502
        return jsonify(ok=True, raw=resp)

    if command == "FMTuneDown":
        resp = get_from_radio("Sendkey", key=3)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"FMTuneDown failed: {reason}", raw=resp), 502
        return jsonify(ok=True, raw=resp)

    if command == "SetFMMode":
        mode = data.get("mode", "stereo")
        resp = get_from_radio("SetFMMode", mode=mode)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"SetFMMode failed: {reason}", raw=resp), 502
        log.info("SetFMMode → %s", mode)
        return jsonify(ok=True, raw=resp)

    if command == "PlayDABHotkey":
        key = int(data.get("key", data.get("Key", 1)))
        resp = get_from_radio("playDABhotkey", key=key)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"PlayDABHotkey failed: {reason}", raw=resp), 502
        log.info("PlayDABHotkey #%d", key)
        _merge_status(Mode="3")
        return jsonify(ok=True, raw=resp)

    if command == "GotoFMFav":
        fav = int(data.get("fav", data.get("Fav", 1)))
        resp = get_from_radio("GotoFMfav", fav=fav)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"GotoFMFav failed: {reason}", raw=resp), 502
        log.info("GotoFMFav #%d", fav)
        _merge_status(Mode="2")
        return jsonify(ok=True, raw=resp)

    if command == "SendKey":
        key = data.get("key", data.get("Key", ""))
        if not key:
            return jsonify(error="key required"), 400
        resp = get_from_radio("Sendkey", key=key)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"SendKey failed: {reason}", raw=resp), 502
        log.info("SendKey → key=%s", key)
        return jsonify(ok=True, raw=resp)

    if command == "PlayStation":
        stn_id = data.get("id", "")
        name   = data.get("name", "")
        if not stn_id:
            return jsonify(error="id required"), 400
        resp = get_from_radio("play_stn", id=stn_id)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"PlayStation failed: {reason}", raw=resp), 502
        log.info("PlayStation → %s (%s)", name, stn_id)
        if name:
            state["cur_play_name"] = name
            _merge_status(cur_play_name=name)
        return jsonify(ok=True, raw=resp, name=name)

    # ── Generic mapped commands ───────────────────────────────────────────────
    if command in COMMAND_MAP:
        path, params = COMMAND_MAP[command]
        resp = get_from_radio(path, **params)
        ok, reason = _cmd_result(resp, cmd=command)
        if not ok:
            return jsonify(ok=False, error=f"{command} failed: {reason}", raw=resp), 502
        log.info("CMD %s → GET /%s %s", command, path, params)
        return jsonify(ok=True, raw=resp)

    # ── Pass-through for unknown commands (path = command name) ───────────────
    extras = {k: v for k, v in data.items() if k != "command"}
    resp = get_from_radio(command, **extras)
    ok, reason = _cmd_result(resp, cmd=command)
    if not ok:
        return jsonify(ok=False, error=f"{command} failed: {reason}", raw=resp), 502
    log.info("CMD %s %s", command, extras)
    return jsonify(ok=True, raw=resp)


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    """Return saved connection settings."""
    return jsonify(load_config())


@app.route("/api/settings", methods=["POST"])
def api_settings_post():
    """Save connection settings (ip, auto_connect)."""
    data = request.get_json(force=True)
    cfg = load_config()
    if "ip" in data:
        cfg["ip"] = (data["ip"] or "").strip()
    if "auto_connect" in data:
        cfg["auto_connect"] = bool(data["auto_connect"])
    save_config(cfg)
    return jsonify(ok=True, settings=cfg)


@app.route("/api/status")
def api_status():
    return jsonify(state["last_status"])


@app.route("/api/hotkeys")
def api_hotkeys():
    """Return the cached hotkey/preset list."""
    return jsonify(state["hotkeys"])


@app.route("/api/sources")
def api_sources():
    """Return available source modes by listing the root menu (id=1).
    This is the definitive list of what the device actually supports.
    Useful for showing only available sources in the UI.
    """
    if not state["ip"]:
        return jsonify(error="Not connected"), 409
    xml_text = get_from_radio("list", retries=0, id=1, start=1, count=15)
    if not xml_text:
        return jsonify(error="No response from radio"), 502
    try:
        root = ET.fromstring(xml_text)
        sources = []
        for item in root.findall("item"):
            id_el   = item.find("id")
            name_el = item.find("name")
            if id_el is not None:
                sources.append({
                    "id":   (id_el.text or "").strip(),
                    "name": (name_el.text or "").strip() if name_el is not None else "",
                })
        return jsonify(sources=sources)
    except ET.ParseError as e:
        return jsonify(error="XML parse error", raw=xml_text), 500


@app.route("/api/browse")
def api_browse():
    """Browse a radio menu category. Pass ?id=XX to list items at that menu node.
    Returns list of items with {id, name, type} where type is 'file' (playable) or 'dir' (folder).
    If no id given, tries cur_play_menu_id then falls back to id=0."""
    if not state["ip"]:
        return jsonify(error="Not connected"), 409
    menu_id = request.args.get("id", "").strip()
    if not menu_id:
        menu_id = state["cur_play_menu_id"] or "0"
    start = int(request.args.get("start", 1))
    count = int(request.args.get("count", 250))
    xml_text = get_from_radio("list", id=menu_id, start=start, count=count)
    if not xml_text:
        return jsonify(error="No response from radio"), 502
    try:
        root = ET.fromstring(xml_text)
        items = []
        for item in root.findall("item"):
            id_el     = item.find("id")
            name_el   = item.find("name")
            status_el = item.find("status")
            if id_el is not None:
                items.append({
                    "id":   (id_el.text or "").strip(),
                    "name": (name_el.text or "").strip() if name_el is not None else "",
                    "type": (status_el.text or "file").strip() if status_el is not None else "file",
                })
        total = root.findtext("item_total", default="0")
        return jsonify(id=menu_id, total=int(total), items=items)
    except ET.ParseError as e:
        log.warning("Browse parse error for id=%s: %s", menu_id, e)
        return jsonify(error="XML parse error", raw=xml_text), 500


@app.route("/api/navigate", methods=["POST"])
def api_navigate():
    """Navigate into a sub-menu (gochild) then list it.
    POST body: {"id": "87_2"}  → calls /gochild?id=87_2 then /list?id=87_2"""
    if not state["ip"]:
        return jsonify(error="Not connected"), 409
    data = request.get_json(force=True)
    menu_id = (data.get("id") or "").strip()
    if not menu_id:
        return jsonify(error="id required"), 400
    nav_resp = get_from_radio("gochild", id=menu_id)
    if nav_resp is None:
        return jsonify(error="No response from radio on gochild"), 502
    # Now list the items at that node
    xml_text = get_from_radio("list", id=menu_id, start=1, count=250)
    if not xml_text:
        return jsonify(error="No response from radio on list"), 502
    try:
        root = ET.fromstring(xml_text)
        items = []
        for item in root.findall("item"):
            id_el     = item.find("id")
            name_el   = item.find("name")
            status_el = item.find("status")
            if id_el is not None:
                items.append({
                    "id":   (id_el.text or "").strip(),
                    "name": (name_el.text or "").strip() if name_el is not None else "",
                    "type": (status_el.text or "file").strip() if status_el is not None else "file",
                })
        total = root.findtext("item_total", default="0")
        return jsonify(id=menu_id, total=int(total), items=items)
    except ET.ParseError as e:
        log.warning("Navigate parse error for id=%s: %s", menu_id, e)
        return jsonify(error="XML parse error", raw=xml_text), 500


@app.route("/api/albumart")
def api_albumart():
    """Proxy the album art image from the radio's media port (8080).
    The image changes when the station changes — useful for change detection."""
    from flask import Response
    if not state["ip"]:
        return jsonify(error="Not connected"), 409
    art = get_albumart_bytes()
    if not art:
        return jsonify(error="No album art available"), 404
    return Response(art, mimetype="image/jpeg", headers={
        "Cache-Control": "no-store",
        "X-Art-Hash": str(hash(art)),
    })


@app.route("/api/search")
def api_search():
    """Search for internet radio stations by name.
    GET /api/search?q=hits  → calls /searchstn?str=hits, then /list on the results."""
    if not state["ip"]:
        return jsonify(error="Not connected"), 409
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(error="Query parameter 'q' required"), 400
    search_resp = get_from_radio("searchstn", str=q)
    if not search_resp:
        return jsonify(error="No response from radio"), 502
    parsed = parse_xml(search_resp)
    result_id = parsed.get("id")
    if not result_id or parsed.get("rt") == "NO_SUPPORT":
        return jsonify(error="Search not supported or no results", raw=search_resp), 404
    xml_text = get_from_radio("list", id=result_id, start=1, count=100)
    if not xml_text:
        return jsonify(error="No list response from radio"), 502
    try:
        root = ET.fromstring(xml_text)
        items = []
        for item in root.findall("item"):
            id_el   = item.find("id")
            name_el = item.find("name")
            if id_el is not None:
                items.append({
                    "id":   (id_el.text or "").strip(),
                    "name": (name_el.text or "").strip() if name_el is not None else "",
                    "type": "file",
                })
        total = root.findtext("item_total", default="0")
        return jsonify(query=q, result_id=result_id, total=int(total), items=items)
    except ET.ParseError as e:
        return jsonify(error="XML parse error", raw=xml_text), 500


@app.route("/api/dab_hotkeys")
def api_dab_hotkeys():
    """Return DAB preset/hotkey list from the device."""
    if not state["ip"]:
        return jsonify(error="Not connected"), 409
    xml_text = get_from_radio("DABhotkeylist")
    if not xml_text:
        return jsonify(error="No response from radio"), 502
    try:
        root = ET.fromstring(xml_text)
        items = []
        for item in root.findall("item"):
            id_el     = item.find("id")
            name_el   = item.find("name")
            status_el = item.find("status")
            if id_el is not None:
                items.append({
                    "id":     (id_el.text or "").strip(),
                    "name":   (name_el.text or "").strip() if name_el is not None else "",
                    "status": (status_el.text or "").strip() if status_el is not None else "",
                })
        return jsonify(items=items)
    except ET.ParseError as e:
        return jsonify(error="XML parse error", raw=xml_text), 500


@app.route("/api/fm_favorites")
def api_fm_favorites():
    """Return FM favorite frequencies from the device (/GetFMFAVlist)."""
    if not state["ip"]:
        return jsonify(error="Not connected"), 409
    xml_text = get_from_radio("GetFMFAVlist")
    if not xml_text:
        return jsonify(error="No response from radio"), 502
    try:
        root = ET.fromstring(xml_text)
        favorites = []
        for item in root.findall("item"):
            id_el   = item.find("id")
            freq_el = item.find("Freq")
            name_el = item.find("name")
            if id_el is not None:
                freq = (freq_el.text or "").strip() if freq_el is not None else ""
                name = (name_el.text or "").strip() if name_el is not None else ""
                if not name and freq:
                    name = freq + " MHz"
                favorites.append({
                    "id":   (id_el.text or "").strip(),
                    "freq": freq,
                    "name": name or ("Fav " + (id_el.text or "").strip()),
                })
        total = root.findtext("item_total", default="0")
        return jsonify(total=int(total), favorites=favorites)
    except ET.ParseError as e:
        return jsonify(error="XML parse error", raw=xml_text), 500


@app.route("/api/sysinfo")
def api_sysinfo():
    """Return device system info from /GetSystemInfo + /init fields."""
    if not state["ip"]:
        return jsonify(error="Not connected"), 409

    result = {}

    # /GetSystemInfo — firmware, MAC, UUID, etc.
    sys_xml = get_from_radio("GetSystemInfo")
    if sys_xml and "FAIL" not in sys_xml and "NO_SUPPORT" not in sys_xml:
        sys_info = parse_xml(sys_xml)
        for k, v in sys_info.items():
            if not k.startswith("_"):
                result[k] = v
        result["_raw_sysinfo"] = sys_xml

    # /init — version, PlayMode, cur_play_name
    init_xml = get_from_radio("init", language="en")
    if init_xml:
        init_info = parse_xml(init_xml)
        for field in ("version", "PlayMode", "cur_play_name", "cur_play_menu_id",
                      "language", "country", "timezone"):
            if field in init_info and init_info[field]:
                result.setdefault(field, init_info[field])
        result["_raw_init"] = init_xml

    # Inject known state
    result["ip"] = state["ip"]
    result["connected"] = state["connected"]
    result["cached_hotkeys"] = len(state["hotkeys"])

    return jsonify(result)


def _auto_connect():
    """If config has auto_connect=True, attempt to connect at server startup."""
    cfg = load_config()
    if cfg.get("auto_connect") and cfg.get("ip"):
        ip = cfg["ip"]
        log.info("Auto-connect: trying %s …", ip)
        time.sleep(1)  # brief delay so SocketIO is ready
        state["ip"] = ip
        resp = get_from_radio("init", language="en")
        if resp is None:
            if _radio_reachable(ip):
                state["connected"] = True
                log.info("Auto-connect: connected to %s (init not supported)", ip)
            else:
                state["ip"] = None
                log.warning("Auto-connect: %s unreachable, skipping", ip)
            return
        device_info = parse_xml(resp)
        state["connected"] = True
        state["cur_play_name"] = device_info.get("cur_play_name", "")
        state["cur_play_menu_id"] = device_info.get("cur_play_menu_id", "")
        log.info("Auto-connect: connected to %s — firmware %s", ip, device_info.get("version", "?"))
        threading.Thread(target=_refresh_hotkeys, daemon=True).start()


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=status_poller, daemon=True).start()
    threading.Thread(target=_auto_connect, daemon=True).start()
    log.info("Server starting → http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)

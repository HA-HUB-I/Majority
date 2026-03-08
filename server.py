#!/usr/bin/env python3
"""
Majority Radio Web Controller
Controls Majority Pembroke radio via the Magic iRadio REST API (port 80).
Run: python server.py  →  open http://localhost:5000
"""

import logging
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
RADIO_AUTH = ("su3g4go6sk7", "ji39454xu/^")  # default Magic iRadio credentials
RADIO_UDP_PORT = 38899
POLL_INTERVAL = 2       # seconds between /playinfo polls
INIT_REFRESH_INTERVAL = 30  # seconds between /init refreshes (updates station name)
MAX_VOL = 20            # maximum volume for /setvol

state = {
    "ip": None,
    "connected": False,
    "last_status": {},
    "hotkeys": [],           # cached preset list: [{"id": "75_256", "name": "BG Radio"}, ...]
    "cur_play_name": "",     # current station name from /init
    "cur_play_menu_id": "",  # current menu id from /init
}

# Maps UI command names → (REST path, extra query params)
# VolumeUp / VolumeDown / Mute are handled separately via /setvol
COMMAND_MAP = {
    "PlayPause":  ("playControl",  {"play": "1"}),
    "Previous":   ("goBackward",   {}),
    "Next":       ("goForward",    {}),
}


# ── HTTP Helpers ───────────────────────────────────────────────────────────────

def get_from_radio(path: str, **params) -> Optional[str]:
    """Send a GET request to the radio REST API with Basic Auth."""
    ip = state["ip"]
    if not ip:
        return None
    try:
        resp = requests.get(
            f"http://{ip}:{RADIO_PORT}/{path}",
            params=params or None,
            auth=RADIO_AUTH,
            headers={"Accept": "text/xml", "Connection": "close"},
            timeout=3,
        )
        log.debug("GET /%s %s → %s", path, params, resp.status_code)
        if not resp.ok:
            log.warning("Radio returned HTTP %s for /%s: %.200s", resp.status_code, path, resp.text)
            return None
        return resp.text
    except requests.RequestException as e:
        log.warning("Radio HTTP error on /%s: %s", path, e)
        return None


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
    """Poll /playinfo every POLL_INTERVAL seconds and refresh /init every INIT_REFRESH_INTERVAL seconds."""
    last_init_time = 0.0
    while True:
        if state["connected"] and state["ip"]:
            now = time.time()

            # Periodically refresh /init to keep station name up to date
            if now - last_init_time >= INIT_REFRESH_INTERVAL:
                init_resp = get_from_radio("init", language="en")
                if init_resp:
                    info = parse_xml(init_resp)
                    if info.get("rt") != "NO_SUPPORT":
                        state["cur_play_name"] = info.get("cur_play_name", state["cur_play_name"])
                        state["cur_play_menu_id"] = info.get("cur_play_menu_id", state["cur_play_menu_id"])
                last_init_time = now

            resp = get_from_radio("playinfo")
            if resp:
                status = parse_xml(resp)
                if status.get("rt") != "NO_SUPPORT":
                    # Inject station name from cached /init data
                    status["cur_play_name"] = state["cur_play_name"]
                    status["cur_play_menu_id"] = state["cur_play_menu_id"]
                    state["last_status"] = status
                    socketio.emit("status", status)
            else:
                if not _radio_reachable(state["ip"]):
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

    # Seed the status with a real /playinfo call
    status_resp = get_from_radio("playinfo")
    status = {}
    if status_resp:
        status = parse_xml(status_resp)
        if status.get("rt") == "NO_SUPPORT":
            status = {}
        else:
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
        if resp is None:
            return jsonify(error="No response from radio"), 502
        log.info("VolumeUp %d → %d", cur_vol, new_vol)
        state["last_status"]["vol"] = str(new_vol)
        return jsonify(ok=True, raw=resp)

    # ── VolumeDown ────────────────────────────────────────────────────────────
    if command == "VolumeDown":
        cur_vol = int(state["last_status"].get("vol", 10) or 10)
        new_vol = max(0, cur_vol - 1)
        resp = get_from_radio("setvol", vol=new_vol, mute=0)
        if resp is None:
            return jsonify(error="No response from radio"), 502
        log.info("VolumeDown %d → %d", cur_vol, new_vol)
        state["last_status"]["vol"] = str(new_vol)
        return jsonify(ok=True, raw=resp)

    # ── Mute (toggle) ─────────────────────────────────────────────────────────
    if command == "Mute":
        cur_mute = int(state["last_status"].get("mute", 0) or 0)
        new_mute = 0 if cur_mute else 1
        cur_vol = int(state["last_status"].get("vol", 10) or 10)
        resp = get_from_radio("setvol", vol=cur_vol, mute=new_mute)
        if resp is None:
            return jsonify(error="No response from radio"), 502
        log.info("Mute toggle → mute=%d", new_mute)
        state["last_status"]["mute"] = str(new_mute)
        return jsonify(ok=True, raw=resp)

    # ── SwitchMode ────────────────────────────────────────────────────────────
    if command == "SwitchMode":
        mode = data.get("Mode", data.get("mode", 0))
        resp = get_from_radio("switchMode", mode=mode)
        if resp is None:
            return jsonify(error="No response from radio"), 502
        log.info("SwitchMode → mode=%s", mode)
        return jsonify(ok=True, raw=resp)

    # ── PlayFavorite (hotkey by 1-based index) ────────────────────────────────
    if command == "PlayFavorite":
        index = int(data.get("Index", data.get("index", 1)))
        hotkeys = state["hotkeys"]
        if not hotkeys:
            _refresh_hotkeys()
            hotkeys = state["hotkeys"]
        if not hotkeys:
            return jsonify(error="Hotkey list not available"), 503
        entry = hotkeys[index - 1] if 0 < index <= len(hotkeys) else None
        if not entry:
            return jsonify(error=f"No hotkey at index {index}"), 404
        resp = get_from_radio("play_stn", id=entry["id"])
        if resp is None:
            return jsonify(error="No response from radio"), 502
        log.info("PlayFavorite #%d → %s (%s)", index, entry["name"], entry["id"])
        return jsonify(ok=True, raw=resp, name=entry["name"])

    # ── Generic mapped commands ───────────────────────────────────────────────
    if command in COMMAND_MAP:
        path, params = COMMAND_MAP[command]
        resp = get_from_radio(path, **params)
        if resp is None:
            return jsonify(error="No response from radio"), 502
        log.info("CMD %s → GET /%s %s", command, path, params)
        return jsonify(ok=True, raw=resp)

    # ── Pass-through for unknown commands (path = command name) ───────────────
    extras = {k: v for k, v in data.items() if k != "command"}
    resp = get_from_radio(command, **extras)
    if resp is None:
        return jsonify(error="No response from radio"), 502
    log.info("CMD %s %s", command, extras)
    return jsonify(ok=True, raw=resp)


@app.route("/api/status")
def api_status():
    return jsonify(state["last_status"])


@app.route("/api/hotkeys")
def api_hotkeys():
    """Return the cached hotkey/preset list."""
    return jsonify(state["hotkeys"])


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=status_poller, daemon=True).start()
    log.info("Server starting → http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)

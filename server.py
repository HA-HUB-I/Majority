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
RADIO_MEDIA_PORT = 8080   # album art / playlogo.jpg served on a separate port
RADIO_AUTH = ("su3g4go6sk7", "ji39454xu/^")  # default Magic iRadio credentials
RADIO_UDP_PORT = 38899
POLL_INTERVAL = 2       # seconds between status polls
INIT_REFRESH_INTERVAL = 30  # seconds between /init refreshes (updates station name)
MAX_VOL = 20            # maximum volume for /setvol

state = {
    "ip": None,
    "connected": False,
    "last_status": {},
    "hotkeys": [],           # cached preset list: [{"id": "75_256", "name": "BG Radio"}, ...]
    "cur_play_name": "",     # current station name from /init
    "cur_play_menu_id": "",  # current menu id from /init (used as root for station browser)
    "browse_stack": [],      # navigation stack for station browser: list of {"id", "title"}
    "albumart_hash": None,   # last seen hash of playlogo.jpg (used for change detection)
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
    """Poll status every POLL_INTERVAL seconds.
    Since /playinfo returns NO_SUPPORT on this firmware, we:
    1. Poll /playinfo (handles firmware that does support it)
    2. Fetch /playlogo.jpg hash from port 8080 — if it changes, the station changed
    3. Emit current manually-tracked state so the UI stays alive
    """
    last_init_time = 0.0
    while True:
        if state["connected"] and state["ip"]:
            now = time.time()

            # Periodically refresh /init to keep station name + mode up to date
            if now - last_init_time >= INIT_REFRESH_INTERVAL:
                init_resp = get_from_radio("init", language="en")
                if init_resp:
                    info = parse_xml(init_resp)
                    if info.get("rt") != "NO_SUPPORT":
                        state["cur_play_name"] = info.get("cur_play_name", state["cur_play_name"])
                        state["cur_play_menu_id"] = info.get("cur_play_menu_id", state["cur_play_menu_id"])
                        play_mode = info.get("PlayMode", "")
                        if play_mode:
                            state["last_status"].setdefault("Mode", play_mode)
                last_init_time = now

            # Try /playinfo — works on standard firmware, returns NO_SUPPORT on j327...
            resp = get_from_radio("playinfo")
            if resp:
                status = parse_xml(resp)
                if status.get("rt") == "NO_SUPPORT":
                    # Firmware doesn't support /playinfo — use album art hash to detect changes
                    art = get_albumart_bytes()
                    if art:
                        art_hash = hash(art)
                        if art_hash != state["albumart_hash"]:
                            state["albumart_hash"] = art_hash
                            log.info("Album art changed — station may have changed (hash=%s)", art_hash)
                            # Signal UI that art changed (triggers img refresh)
                            state["last_status"]["_art_changed"] = str(art_hash)

                    state["last_status"]["cur_play_name"] = state["cur_play_name"]
                    _emit_status()
                else:
                    status["cur_play_name"] = state["cur_play_name"]
                    status["cur_play_menu_id"] = state["cur_play_menu_id"]
                    state["last_status"].update(status)
                    _emit_status()
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

    # Seed the status with a real /playinfo call (may return NO_SUPPORT on some firmware)
    status_resp = get_from_radio("playinfo")
    status = {}
    if status_resp:
        status = parse_xml(status_resp)
        if status.get("rt") == "NO_SUPPORT":
            status = {}
        else:
            status["cur_play_name"] = state["cur_play_name"]
            status["cur_play_menu_id"] = state["cur_play_menu_id"]

    # If /playinfo didn't give us vol, try /getvol (read-only on some firmware)
    if "vol" not in status:
        getvol_resp = get_from_radio("getvol")
        if getvol_resp:
            getvol = parse_xml(getvol_resp)
            if "vol" in getvol:
                status["vol"] = getvol["vol"]
                status["mute"] = getvol.get("mute", "0")

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
        if resp is None:
            return jsonify(error="No response from radio"), 502
        # Parse confirmed vol/mute from radio response and emit to UI immediately
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
        if resp is None:
            return jsonify(error="No response from radio"), 502
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
        if resp is None:
            return jsonify(error="No response from radio"), 502
        confirmed = parse_xml(resp)
        actual_mute = confirmed.get("mute", str(new_mute))
        log.info("Mute toggle → mute=%s", actual_mute)
        _merge_status(mute=actual_mute)
        return jsonify(ok=True, mute=actual_mute, raw=resp)

    # ── SwitchMode ────────────────────────────────────────────────────────────
    # NOTE: /switchMode returns NO_SUPPORT on firmware j327...
    # Internet Radio is activated via menu navigation (/gochild + /list + /play_stn).
    # FM/DAB/BT/AUX menu IDs are not yet discovered — see API_DISCOVERY.md.
    if command == "SwitchMode":
        mode = str(data.get("Mode", data.get("mode", 0)))
        # Try the standard API first (works on newer firmware)
        resp = get_from_radio("switchMode", mode=mode)
        if resp:
            parsed = parse_xml(resp)
            if parsed.get("rt") != "NO_SUPPORT" and "FAIL" not in resp:
                log.info("SwitchMode → mode=%s (standard API)", mode)
                _merge_status(Mode=mode)
                return jsonify(ok=True, raw=resp)
        # Standard API not supported — try navigating to Internet Radio via menu
        if mode in ("0", "1"):
            nav_resp = get_from_radio("gochild", id="87")
            log.info("SwitchMode mode=%s → navigated to Internet Radio menu (gochild id=87)", mode)
            _merge_status(Mode=mode)
            return jsonify(ok=True, note="Navigated to Internet Radio menu. Use Stations browser to pick a station.")
        # FM/DAB/BT/AUX — menu IDs not yet discovered
        log.warning("SwitchMode mode=%s — menu ID unknown for this firmware", mode)
        return jsonify(
            ok=False,
            error=f"Source switching to mode {mode} is not supported on this firmware. "
                  f"Menu navigation IDs for FM/DAB/BT/AUX are not yet discovered.",
            hint="Use the Stations browser for Internet Radio. FM/DAB require menu ID discovery.",
        ), 501

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
        # Update station name in tracked state
        state["cur_play_name"] = entry["name"]
        _merge_status(cur_play_name=entry["name"])
        return jsonify(ok=True, raw=resp, name=entry["name"])

    # ── PlayStation (play by raw menu id, e.g. "87_3") ───────────────────────
    if command == "PlayStation":
        stn_id = data.get("id", "")
        name   = data.get("name", "")
        if not stn_id:
            return jsonify(error="id required"), 400
        resp = get_from_radio("play_stn", id=stn_id)
        if resp is None:
            return jsonify(error="No response from radio"), 502
        log.info("PlayStation → %s (%s)", name, stn_id)
        if name:
            state["cur_play_name"] = name
            _merge_status(cur_play_name=name)
        return jsonify(ok=True, raw=resp, name=name)

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


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=status_poller, daemon=True).start()
    log.info("Server starting → http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)

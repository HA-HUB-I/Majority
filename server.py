#!/usr/bin/env python3
"""
Majority Radio Web Controller
Controls Majority Pembroke radio via Magic M6/M7 XML protocol on port 8080.
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

RADIO_XML_PORT = 8080
RADIO_UDP_PORT = 38899
POLL_INTERVAL = 2  # seconds between GetStatus polls

state = {
    "ip": None,
    "connected": False,
    "last_status": {},
}


# ── XML Helpers ────────────────────────────────────────────────────────────────

def build_xml(command: str, **params) -> str:
    root = ET.Element("YMP-Command")
    ET.SubElement(root, "Command").text = command
    for key, value in params.items():
        ET.SubElement(root, key).text = str(value)
    return '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="unicode")


def send_to_radio(xml: str) -> Optional[str]:
    """Send an XML command to the radio via HTTP POST on port 8080."""
    ip = state["ip"]
    if not ip:
        return None
    try:
        resp = requests.post(
            f"http://{ip}:{RADIO_XML_PORT}",
            data=xml.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8", "Connection": "close"},
            timeout=3,
        )
        if not resp.ok:
            log.warning("Radio returned HTTP %s: %.200s", resp.status_code, resp.text)
            return None
        return resp.text
    except requests.RequestException as e:
        log.warning("Radio HTTP error: %s", e)
        return None


# Keep the old name as an alias so any future callers still work.
post_to_radio = send_to_radio


def parse_status(xml_text: str) -> dict:
    """Parse GetStatus XML into a flat dict. Keeps _raw for debug display."""
    try:
        root = ET.fromstring(xml_text)
        result = {child.tag: (child.text or "") for child in root}
        result["_raw"] = xml_text
        return result
    except ET.ParseError:
        return {"_raw": xml_text, "_parse_error": "true"}


# ── Background Status Poller ───────────────────────────────────────────────────

def _radio_reachable(ip: str) -> bool:
    """Return True if the radio's XML port is reachable via TCP."""
    try:
        with socket.create_connection((ip, RADIO_XML_PORT), timeout=2) as s:
            pass
        return True
    except OSError:
        return False


def status_poller():
    while True:
        if state["connected"] and state["ip"]:
            resp = post_to_radio(build_xml("GetStatus"))
            if resp:
                status = parse_status(resp)
                state["last_status"] = status
                socketio.emit("status", status)
            else:
                # GetStatus failed (e.g. radio returned 501).  Fall back to a
                # plain TCP reachability check before declaring disconnection so
                # that radios that don't implement GetStatus stay "connected".
                if not _radio_reachable(state["ip"]):
                    state["connected"] = False
                    socketio.emit("disconnected", {})
                else:
                    log.debug("GetStatus failed for %s but radio is still reachable", state["ip"])
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

    resp = post_to_radio(build_xml("GetStatus"))
    if resp is None:
        # GetStatus may return a non-2xx code (e.g. 501) on some firmware.
        # Fall back to a plain TCP check so we still connect if the port is open.
        if not _radio_reachable(ip):
            return jsonify(error=f"No response from {ip}:{RADIO_XML_PORT}"), 502
        state["connected"] = True
        log.info("Connected to radio at %s (GetStatus not supported)", ip)
        return jsonify(ok=True, status={})

    status = parse_status(resp)
    state["connected"] = True
    state["last_status"] = status
    log.info("Connected to radio at %s", ip)
    return jsonify(ok=True, status=status)


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    state["ip"] = None
    state["connected"] = False
    state["last_status"] = {}
    return jsonify(ok=True)


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """UDP broadcast on port 38899. Works only if network allows broadcast packets."""
    found = []
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(3)
        probe = build_xml("GetStatus").encode("utf-8")
        s.sendto(probe, ("<broadcast>", RADIO_UDP_PORT))
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

    extras = {k: v for k, v in data.items() if k != "command"}
    xml = build_xml(command, **extras)
    log.info("TX: %s %s", command, extras)

    resp = post_to_radio(xml)
    if resp is None:
        return jsonify(error="No response from radio"), 502

    log.info("RX: %s", resp)
    return jsonify(ok=True, raw=resp)


@app.route("/api/status")
def api_status():
    return jsonify(state["last_status"])


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    threading.Thread(target=status_poller, daemon=True).start()
    log.info("Server starting → http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)

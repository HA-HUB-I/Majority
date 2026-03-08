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
    """Send an XML command to the radio via HTTP GET.

    The radio's embedded HTTP server (port 8080) uses GET, not POST.
    Sending POST results in "501 Not Implemented – The requested method
    is not recognized".  The XML payload is placed in the request body
    exactly as before; the only change is the HTTP verb.
    """
    ip = state["ip"]
    if not ip:
        return None
    try:
        resp = requests.get(
            f"http://{ip}:{RADIO_XML_PORT}",
            data=xml.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8"},
            timeout=3,
        )
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

def status_poller():
    while True:
        if state["connected"] and state["ip"]:
            resp = post_to_radio(build_xml("GetStatus"))
            if resp:
                status = parse_status(resp)
                state["last_status"] = status
                socketio.emit("status", status)
            else:
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

    resp = post_to_radio(build_xml("GetStatus"))
    if resp is None:
        return jsonify(error=f"No response from {ip}:{RADIO_XML_PORT}"), 502

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

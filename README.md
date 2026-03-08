# Majority Radio Web Controller

Browser-based remote control for **Majority Pembroke** internet radio using the Magic iRadio XML REST API (port 80).

## Requirements

- Python 3.8+
- Radio and PC on the same local network

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python server.py
```

Open **http://localhost:5000** in your browser (or `http://<your-pc-ip>:5000` from another device on the network).

## Connect to Radio

1. Find the radio's IP address (check your router's DHCP table, or try the **Scan** button)
2. Enter the IP in the connection field and click **Connect**
3. ✅ Check **Remember IP** to save the address for future sessions
4. ✅ Check **Auto-connect on start** to connect automatically next time the server starts
5. Status updates automatically every 2 seconds via WebSocket

The **Connect** button turns into a **Disconnect** button when connected.  
Settings are saved to `config.json` in the project folder.

## Controls

| Control | Description |
|---|---|
| VOL − / VOL + | Volume down / up |
| MUTE | Toggle mute (button lights up when active) |
| ⏮ / ⏯ / ⏭ | Previous / Play-Pause / Next station |
| INET / FM / DAB / BT / AUX | Switch source mode (INET navigates to station menu) |
| Preset buttons | Play saved preset/favourite — names loaded from device |

Preset buttons show the **real station names** saved on the radio (e.g. "BG Radio", "Radio 1").  
The active preset is highlighted in blue.

## Features

- **Real-time volume status** — updated immediately after every VOL/MUTE command
- **Album art** — fetched from the radio's media port (port 8080), auto-refreshed every 5 s, changes when station changes
- **Station browser** — navigate the radio's menu tree and click any station to play it
- **Preset names** — loaded from the device on connect and shown on buttons
- **IP persistence** — IP and auto-connect preference saved in `config.json`
- **Auto-connect** — server connects to saved IP automatically on startup if configured
- **WebSocket** — all status updates pushed to the browser in real time (no page refresh needed)

## Ports Used

| Port | Purpose |
|---|---|
| 5000 (TCP) | This web server |
| 80 (TCP) | Radio XML REST API (GET requests with Basic Auth) |
| 8080 (TCP) | Radio media port — album art (`/playlogo.jpg`) |
| 38899 (UDP) | Optional auto-discovery broadcast scan |

## Troubleshooting

### Status panel shows "FAIL" or "NO_SUPPORT" repeatedly

This firmware (`j32720190327h`) does **not** support the `/playinfo` endpoint — it returns
`<result>FAIL</result>` or `<result><rt>NO_SUPPORT</rt></result>`.  
The server detects this and emits the last known manually-tracked state instead, so
volume, station name and source mode are still shown correctly.  The debug panel
suppresses these non-informative XML responses.

### Source switching (FM / DAB / BT / AUX) does not work

The `/switchMode` command returns `NO_SUPPORT` on this firmware.  
Only **INET** mode works via a menu navigation fallback (`/gochild?id=87`).  
FM/DAB/BT/AUX switching is not supported by this firmware version.

### Album art not loading

Album art is served on port 8080 with Basic Auth.  The web server proxies it via
`/api/albumart` to avoid browser CORS/auth issues.  Make sure port 8080 is reachable
from the PC running the server.

### UDP scan not finding the radio

UDP scan may not work if your router blocks broadcast packets.  
Manual IP entry is the reliable method.  Use your router's DHCP table to find the radio's IP.

## Debug

Expand the **RAW DEBUG** panel in the UI to see raw XML from the radio.  
Only responses with actual data are logged — FAIL/NO_SUPPORT noise is suppressed.

## API Endpoints (Server)

| Endpoint | Method | Description |
|---|---|---|
| `/api/connect` | POST | Connect to radio `{ip}` |
| `/api/disconnect` | POST | Disconnect |
| `/api/settings` | GET | Read saved settings (ip, auto_connect) |
| `/api/settings` | POST | Save settings |
| `/api/status` | GET | Current tracked state |
| `/api/hotkeys` | GET | Cached preset list |
| `/api/browse` | GET | Browse station menu `?id=XX` |
| `/api/navigate` | POST | Navigate into menu `{id}` |
| `/api/albumart` | GET | Proxy album art from radio port 8080 |
| `/api/cmd` | POST | Send command to radio |
| `/api/scan` | POST | UDP broadcast scan |

See `API_DISCOVERY.md` for full documentation of the radio's own REST API endpoints.

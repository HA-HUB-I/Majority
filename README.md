# Majority Radio Web Controller

Browser-based remote control for **Majority Pembroke** internet radio using the Magic M6/M7 XML protocol.

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
3. Status updates automatically every 2 seconds via WebSocket

## Controls

| Control | Description |
|---|---|
| VOL − / VOL + | Volume down / up |
| MUTE | Toggle mute |
| ⏮ / ⏯ / ⏭ | Previous / Play-Pause / Next station |
| INET / FM / DAB / BT / AUX | Switch source mode |
| 1–8 | Play preset/favourite by index |

## Ports Used

| Port | Purpose |
|---|---|
| 5000 (TCP) | This web server |
| 8080 (TCP) | Radio XML command API |
| 38899 (UDP) | Optional auto-discovery broadcast |

## Troubleshooting

### Debug panel shows "501 Not Implemented / The requested method is not recognized" repeatedly

Some Majority Pembroke firmware versions do not implement the `GetStatus` XML command and
return HTTP 501 for it.  `server.py` now treats any non-2xx HTTP response as a failure
(returns `None`) so these error pages are **never** shown as status data.  When
`GetStatus` is unavailable the server falls back to a plain TCP reachability check to
decide whether the radio is still connected, so control commands (volume, presets, etc.)
continue to work.

### Radio returns a "can't open 'index.html'" connection error

The Majority Pembroke's embedded HTTP server (port 8080) uses **POST** requests for
the XML command API.  Sending **GET** requests causes the radio to attempt to serve its
built-in web UI (`index.html`), which fails and returns a non-HTTP response, resulting in
a `BadStatusLine` / `Connection aborted` error.  Make sure you are running the latest
version of `server.py` which uses POST when communicating with the radio.

### Is there a default password?

The web interface (`http://localhost:5000`) has **no password** – just open it in a
browser.  The radio itself also does not require a PIN for the YMP XML API on port 8080.

## Debug

Expand the **RAW DEBUG** panel in the UI to see the raw XML exchanged with the radio.  
This is useful for discovering exact field names returned by `GetStatus` responses.

> **Note:** UDP scan may not work if your router blocks broadcast packets.  
> Manual IP entry is the reliable method.

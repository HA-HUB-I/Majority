# Majority Radio — Magic iRadio API Discovery

**Device:** Majority Pembroke Internet Radio  
**Firmware:** `j32720190327h`  
**HTTP API:** port 80, Basic Auth `su3g4go6sk7` / `ji39454xu/^`  
**Media port:** 8080 (album art)  
**Protocol:** Magic iRadio / UIProto (mediayou.net)

---

## Menu Tree (Confirmed IDs)

| Menu ID | Name |
|---|---|
| `1` | Root |
| `52` | Internet Radio |
| `87` | Local Radio / Favorites |
| `5` | FM |
| `91` | DAB/DAB+ |
| `104` | Bluetooth |
| `47` | AUX In |
| `2` | Media Center |
| `3` | Information Center |
| `6` | Configuration |
| `71` | Unknown submenu |
| `75` | Hotkey/Preset base |
| `100` | Search results (dynamic) |

---

## Confirmed Working Endpoints

### `/init?language=en` OK
Returns device info. Called at connect to verify reachability.
PlayMode values: 1=Internet Radio, 2=FM, 3=DAB, 4=BT, 5=AUX

### `/background_play_status` OK PRIMARY STATUS ENDPOINT
The most reliable status on this firmware. Returns vol+mute always.
Polled every 2 seconds by the server.
Fields: sid, playtime_left, vol, mute, name

### `/setvol?vol=0-20&mute=0|1` OK
Set volume and mute. Returns confirmed vol/mute.
Sometimes returns FAIL - treat as no-op.

### `/hotkeylist` OK
Returns 5 saved Internet Radio presets.
WARNING: Some IDs are duplicated (75_0) - use /playhotkey?key=N by index, NOT play_stn?id=

### `/playhotkey?key=N` OK CORRECT PRESET PLAY
Play internet radio preset by 1-based key number. Returns vol+mute+status.

### `/DABhotkeylist` OK
Returns DAB+ preset list.

### `/playDABhotkey?key=N` OK
Play DAB preset by 1-based key.

### `/GetFMStatus` OK
FM mode status: vol, mute, Signal, Sound, Freq, RDS.

### `/GetFMFAVlist` OK
Returns saved FM favorite frequencies as list of {id, Freq}.

### `/GotoFMfav?fav=N` OK
Switch to FM favorite by 1-based index.

### `/GetBTStatus` OK
Bluetooth status: vol, mute, Status.

### `/gochild?id=N` OK
Navigate into menu node. Used for SwitchMode:
  FM: gochild?id=5
  DAB: gochild?id=91
  BT: gochild?id=104
  AUX: gochild?id=47
  INET: gochild?id=52

### `/list?id=N&start=1&count=250` OK
List menu items. status=file=playable, status=content=folder.

### `/play_stn?id=N_M` OK
Play station by menu ID.

### `/searchstn?str=QUERY` OK
Search internet radio stations. Returns result_id, then list with /list?id=result_id.

### `/Sendkey?key=N` OK
Simulate remote control key press.
Keys: 1=Home, 2=Up, 3=Down, 4=Left, 5=Right, 6=Enter, 8=Mute, 9=Vol+, 10=Vol-,
      11=Alarm, 12=Sleep, 14=Light, 15=Star, 28=Mode, 29=Play/Pause, 31=Next, 32=Prev, 106=PowerOff

### `/back` OK
Navigate back in menu.

### `/stop` OK
Stop playback.

### `/GetSystemInfo` OK
Device network info (IP, MAC, SSID, firmware).

### `/play_url?id=N_M` OK
Get stream URL for a station.

### `http://<IP>:8080/playlogo.jpg` OK
Current station logo/album art. Changes when station changes.

---

## Confirmed NOT Working on j32720190327h

| Endpoint | Returns | Notes |
|---|---|---|
| /playinfo | FAIL | Always fails on this firmware |
| /switchMode?mode=N | NO_SUPPORT | Use gochild navigation instead |
| /setfav | FAIL | Cannot save new favorites |

---

## Sendkey Remote Control Keys

| Key | Action |
|---|---|
| 1 | Home |
| 2 | Up |
| 3 | Down |
| 4 | Left |
| 5 | Right |
| 6 | Enter |
| 8 | Mute |
| 9 | Vol+ |
| 10 | Vol- |
| 11 | Alarm |
| 12 | Sleep |
| 14 | Light |
| 15 | Star (Favorite) |
| 19 | EQ |
| 28 | Mode |
| 29 | Play/Pause |
| 31 | Next |
| 32 | Prev |
| 106 | Power Off |

---

## Server API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| /api/connect | POST | Connect {ip} |
| /api/disconnect | POST | Disconnect |
| /api/settings | GET/POST | Persist IP + auto_connect to config.json |
| /api/status | GET | Current tracked state |
| /api/hotkeys | GET | Cached internet radio presets |
| /api/dab_hotkeys | GET | DAB preset list |
| /api/fm_favorites | GET | FM favorite frequencies |
| /api/browse?id=N | GET | Browse menu tree |
| /api/navigate | POST | Navigate into menu node {id} |
| /api/search?q=... | GET | Search internet radio stations |
| /api/albumart | GET | Proxy album art from port 8080 |
| /api/cmd | POST | Send command to radio |
| /api/scan | POST | UDP broadcast scan |

### Commands (/api/cmd POST body)

| command | Params | Description |
|---|---|---|
| VolumeUp | - | +1 volume |
| VolumeDown | - | -1 volume |
| Mute | - | Toggle mute |
| PlayFavorite | Index | Play INET preset by 1-based index |
| PlayDABHotkey | key | Play DAB preset by 1-based index |
| GotoFMFav | fav | Play FM favorite by 1-based index |
| SwitchMode | Mode | Switch source (0=INET,2=FM,3=DAB,4=BT,5=AUX) |
| PlayStation | id, name | Play station by menu id |
| SendKey | key | Simulate remote control key |
| PlayPause | - | Play/Pause |
| Previous | - | Previous station |
| Next | - | Next station |

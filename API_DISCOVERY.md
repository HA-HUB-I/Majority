# Majority Pembroke — Magic iRadio API Discovery

**Устройство:** Majority Pembroke Internet Radio  
**IP:** 192.168.11.16  
**HTTP порт:** 80 (основен API)  
**HTTP порт:** 8080 (медийни файлове — album art)  
**Firmware:** `j32720190327h`  
**Аутентикация:** HTTP Basic Auth → `su3g4go6sk7` / `ji39454xu/^`  
**Протокол:** Magic iRadio REST API (GET заявки, XML отговори)  
**Лог файл:** `logger/192.168.11.16_2026_03_08_16_06_24.har` + session txt файлове  

---

## ✅ Потвърдени работещи endpoints

### `GET /setvol?vol={0-20}&mute={0|1}`
**Цел:** Задава сила на звука и mute  
**Работи:** ✅ Потвърдено  
**Порт:** 80  

**Заявка:**
```
GET /setvol?vol=8&mute=0 HTTP/1.1
Authorization: Basic c3UzZzRnbzZzazc6amkzOTQ1NHh1L14=
```

**Отговор:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <vol>8</vol>
  <mute>0</mute>
</result>
```

**Бележки:**
- `vol` диапазон: `0` до `20`
- `mute=1` заглушава, `mute=0` включва звука
- Отговорът потвърждава реалните стойности (може да се ползва за четене на vol/mute след задаване)
- Когато `mute=1`, `vol` в отговора пак показва реалния volume (не 0)

---

### `GET /back_stop`
**Цел:** Връща обща информация за устройството (device info / init)  
**Работи:** ✅ Потвърдено  
**Порт:** 80  

**Отговор:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <id>1</id>
  <version>j32720190327h</version>
  <lang>en</lang>
  <wifi_set_url>http://192.168.78.1/scan_wifi</wifi_set_url>
  <ptver>20170921</ptver>
  <hotkey_fav>1</hotkey_fav>
  <push_talk>1</push_talk>
  <leave_msg>1</leave_msg>
  <leave_msg_ios>1</leave_msg_ios>
  <M7_SUPPORT>0</M7_SUPPORT>
  <SMS_SUPPORT>0</SMS_SUPPORT>
  <MKEY_SUPPORT>0</MKEY_SUPPORT>
  <UART_CD>0</UART_CD>
  <ALEXA>0</ALEXA>
  <PlayMode>1</PlayMode>
  <SWUpdate>NO</SWUpdate>
</result>
```

**Полета:**
| Поле | Стойност | Описание |
|------|----------|----------|
| `id` | `1` | Device ID |
| `version` | `j32720190327h` | Firmware версия |
| `lang` | `en` | Текущ език |
| `hotkey_fav` | `1` | Хотки/любими поддържани |
| `PlayMode` | `1` | Текущ режим на възпроизвеждане (**виж секция PlayMode**) |
| `SWUpdate` | `NO` | Няма наличен firmware update |
| `ALEXA` | `0` | Alexa не се поддържа |
| `M7_SUPPORT` | `0` | Magic M7 API не се поддържа |

**⚠️ Внимание:** Може да е и команда за спиране на възпроизвеждането — не е ясно дали извикването спира радиото или само връща info. **Изисква тест.**

---

### `GET /list?id={menuId}&start={N}&count={N}`
**Цел:** Зарежда списък с елементи от дадено меню  
**Работи:** ✅ Потвърдено  
**Порт:** 80  

**Пример — любими (id=87):**
```
GET /list?id=87&start=1&count=250
```

**Отговор:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<menu>
  <item_total>10</item_total>
  <item_return>10</item_return>
  <item><id>87_1</id><status>file</status><name>Radio 1</name></item>
  <item><id>87_2</id><status>file</status><name>BG Radio</name></item>
  <item><id>87_3</id><status>file</status><name>Radio Veronika</name></item>
  <item><id>87_4</id><status>file</status><name>Radio ENERGY Bulgaria</name></item>
  <item><id>87_5</id><status>file</status><name>Radio 1 Rock</name></item>
  <item><id>87_6</id><status>file</status><name>bTV Radio</name></item>
  <item><id>87_7</id><status>file</status><name>Radio City</name></item>
  <item><id>87_8</id><status>file</status><name>DJ ZONE HOUSE RADIO</name></item>
  <item><id>87_9</id><status>file</status><name>Radio Hot Dance</name></item>
  <item><id>87_10</id><status>file</status><name>Folk Radio Nazdrave</name></item>
</menu>
```

**Структура на item:**
| Поле | Тип | Описание |
|------|-----|----------|
| `id` | string | Уникален ID на елемента (формат `{menuId}_{N}`) |
| `status` | `file` или `dir` | `file` = директно пускане; `dir` = под-меню |
| `name` | string | Показвано име |

**Известни menu ID-та:**
| ID | Съдържание |
|----|------------|
| `87` | Потребителски любими (10 български радиа) |
| `52` | Друга категория (съдържанието не е уловено) |

---

### `GET /gochild?id={itemId}`
**Цел:** Навигация — влиза в под-меню или категория  
**Работи:** ✅ Потвърдено (заявката е уловена; отговорът не е уловен)  
**Порт:** 80  

**Известни извиквания:**
```
GET /gochild?id=87       → влиза в категория "Любими" (menu 87)
GET /gochild?id=87_2     → влиза в елемент BG Radio
GET /gochild?id=52       → влиза в категория с ID 52
```

**⚠️ Отговорите не са уловени.** Очакваем XML формат — пренасочване или потвърждение. След `gochild` трябва `list?id=XX` за да се вземат елементите.

---

### `GET /play_stn?id={itemId}`
**Цел:** Пуска радиостанция по ID  
**Работи:** ✅ Потвърдено (заявката е уловена; отговорът не е уловен)  
**Порт:** 80  

**Пример:**
```
GET /play_stn?id=87_3   → пуска Radio Veronika
```

**⚠️ Отговорът не е уловен.** Очакван: `<result>OK</result>` или подобен.

---

### `GET /play_url?id={itemId}`
**Цел:** Връща streaming URL за дадена станция  
**Работи:** ✅ Потвърдено  
**Порт:** 80  

**Пример:**
```
GET /play_url?id=87_3
```

**Отговор:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <url>http://b1.mediayou.net/embedded/playURL.php?id=7632&sc=N9XX_AAC</url>
</result>
```

**Бележки:**
- Връща реалния stream URL (не играе директно — само дава URL-а)
- Може да се ползва за показване на stream info или за директно свързване

---

### `GET /switchMode?mode={N}`
**Цел:** Смяна на source (INET/FM/DAB/BT/AUX)  
**Работи:** ❌ НЕ РАБОТИ — връща `NO_SUPPORT`  

**Отговор:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <rt>NO_SUPPORT</rt>
</result>
```

**Заобикаляне:** За Internet Radio се ползва `/gochild?id=87` (навигация в менюто). За FM/DAB/BT/AUX — menu ID-тата не са открити.

---

### `GET /setfav?id={menuId}&item={N}&favpos={pos}`
**Цел:** Добавя/задава любима станция на определена позиция  
**Работи:** ❌ Връща FAIL  
**Порт:** 80  

**Пример:**
```
GET /setfav?id=87&item=3&favpos=4
```

**Отговор:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>FAIL</result>
```

**⚠️ Не работи на това устройство.** Може да изисква различни параметри или разрешения.

---

### `GET /playlogo.jpg` (порт 8080)
**Цел:** Album art / лого на текущо пускащата се станция  
**Работи:** ✅ Потвърдено (5140 bytes JPEG)  
**Порт:** 8080 (различен от основния!)  

**Заявка:**
```
GET http://192.168.11.16:8080/playlogo.jpg
```

**Бележки:**
- Различен порт — **8080**, не 80
- Изображение в JPEG формат — директно достъпно
- **Сменя се при смяна на станция** → ползва се за change detection!
  - Хеш на изображението се проверява на всеки POLL_INTERVAL
  - Ако хешът се смени → станцията е сменена (работи без `/playinfo`)
- Нашият сървър го проксира на `/api/albumart` (заобикаля CORS, добавя auth)
- UI го показва в Now Playing секцията, опреснява на всеки 5 сек

---

### `GET /init?language=en`
**Цел:** Инициализация и устройствена информация  
**Работи:** ✅ Частично (потвърдено от server log)  
**Порт:** 80  

**Бележки от server log:**
```
Connected to radio at 192.168.11.16 — firmware j32720190327h
```
Сървърът извлича `version` успешно. Обаче полетата `cur_play_name` и `cur_play_menu_id` **не се попълват** — вероятно ги няма в тази firmware версия.

**⚠️ Пълният XML отговор не е уловен.** Трябва capture за да се знаят точните полета.

---

## ❌ Непотвърдени / НЕ работещи endpoints

### `GET /playinfo`
**Цел:** Текущо статус на възпроизвеждане (vol, mute, station, mode)  
**Работи:** ❌ НЕ РАБОТИ — връща `NO_SUPPORT`  
**Извиква се:** 30+ пъти в HAR лога (всеки 2 сек)  

**Отговор:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <rt>NO_SUPPORT</rt>
</result>
```

**⚠️ Критичен проблем** — това е основната причина UI не показваше volume, station name и mode. Заобиколено чрез ръчно state tracking след setvol команди.

---

### `GET /switchMode?mode={0|2|3|4|5}`
**Цел:** Смяна на source (INET/FM/DAB/BT/AUX)  
**Работи:** ❓ НЕИЗВЕСТНО  

**Изпратено от нашия сървър, но:**
- Не е уловено в HAR/session логовете
- Отговорът е неизвестен
- Може да върне `NO_SUPPORT` като `/playinfo`

**Mode числа (стандартни за Magic iRadio):**
| Число | Source |
|-------|--------|
| `0` | Internet Radio |
| `2` | FM |
| `3` | DAB+ |
| `4` | Bluetooth |
| `5` | AUX |

**⚠️ Трябва тест** — дали работи на тази firmware.

---

### `GET /hotkeylist`
**Цел:** Списък на preset/hotkey бутоните (1-5)  
**Работи:** ✅ Частично (от server log: `Cached 5 hotkeys`)  

**Бележки:**
- Пълният XML отговор не е уловен
- Структурата се предполага: `<item><id>...</id><name>...</name></item>`
- Тези са различни от `/list?id=87` (5 preset бутона vs 10 любими станции)

---

### `GET /playControl?play=1`
**Цел:** Play/Pause toggle  
**Работи:** ❓ НЕИЗВЕСТНО — не е тествано на тази firmware  

---

### `GET /goBackward`  
**Цел:** Предишна станция  
**Работи:** ❓ НЕИЗВЕСТНО  

---

### `GET /goForward`  
**Цел:** Следваща станция  
**Работи:** ❓ НЕИЗВЕСТНО  

---

### `GET /getvol`
**Цел:** Четене на текущия volume без промяна (read-only)  
**Работи:** ❓ НЕИЗВЕСТНО — добавено в кода като fallback при connect  

---

## 🔍 Какво трябва да се открие

### Приоритет 1 — Критично

| Endpoint | Въпрос |
|----------|--------|
| `/back_stop` | Спира ли реално възпроизвеждането или е само device-info? Безопасно ли е да се извиква? |
| `/switchMode` | ❌ ПОТВЪРДЕНО: НЕ работи → `NO_SUPPORT`. Алтернативата е навигация с `/gochild` |
| `/playControl` | Работи ли play/pause? |
| `/getvol` | Съществува ли read-only endpoint за текущия volume? |
| Root menu ID | Кое е root menu ID (`/list?id=?`) за пълно браузване на всички категории? |
| FM menu ID | Кое е menu ID за FM (аналог на `87` за Internet Radio)? |
| DAB menu ID | Кое е menu ID за DAB+? |
| BT menu ID | Кое е menu ID за Bluetooth? |

### Приоритет 2 — Важно

| Endpoint | Въпрос |
|----------|--------|
| `/init` | Пълен XML отговор — кои полета съдържа? `cur_play_name`? `cur_play_menu_id`? |
| `/list?id=52` | Какви станции/категории съдържа menu ID 52? |
| `/play_stn` response | Какъв точно XML отговор връща при успех/грешка? |
| `/gochild` response | Какъв XML отговор връща? |
| `/hotkeylist` | Пълен XML — какви полета имат items-ите? |

### Приоритет 3 — Допълнително

| Endpoint | Въпрос |
|----------|--------|
| `/setfav` | Защо FAIL? Правилни ли са параметрите? Нужна ли е различна аутентикация? |
| `/goBackward` / `/goForward` | Работят ли? Какъв отговор? |
| `/volumeCtrl?action=plus/minus` | Работи ли алтернативният volume endpoint? |
| `/getNowPlaying` / `/playerStatus` | Съществуват ли алтернативни status endpoints? |
| FM/DAB menu IDs | Кои са menu ID-тата за FM и DAB категориите? |
| `/search?...` | Съществува ли търсене по станция? |
| `/setlang?lang=...` | Смяна на език |

---

## 📋 PlayMode стойности

Полето `<PlayMode>` в `/back_stop` отговора:

| Стойност | Значение | Потвърдено? |
|----------|----------|-------------|
| `0` | Internet Radio | ❓ |
| `1` | Internet Radio (алт.) | ✅ (видяно в лога) |
| `2` | FM | ❓ |
| `3` | DAB+ | ❓ |
| `4` | Bluetooth | ❓ |
| `5` | AUX | ❓ |

**⚠️ Не е ясно** дали PlayMode в `/back_stop` е идентично с Mode в `/switchMode`.

---

## 🗂️ Структура на Menu ID системата

```
Root (id=?)
├── Любими / Favorites (id=87)
│   ├── 87_1  Radio 1
│   ├── 87_2  BG Radio
│   ├── 87_3  Radio Veronika
│   ├── 87_4  Radio ENERGY Bulgaria
│   ├── 87_5  Radio 1 Rock
│   ├── 87_6  bTV Radio
│   ├── 87_7  Radio City
│   ├── 87_8  DJ ZONE HOUSE RADIO
│   ├── 87_9  Radio Hot Dance
│   └── 87_10 Folk Radio Nazdrave
├── Категория (id=52)
│   └── [СЪДЪРЖАНИЕ НЕИЗВЕСТНО]
└── ... (останалите категории неизвестни)
```

---

## 🔐 Аутентикация

```
Схема:   HTTP Basic Auth
User:    su3g4go6sk7
Pass:    ji39454xu/^
Base64:  c3UzZzRnbzZzazc6amkzOTQ1NHh1L14=
Header:  Authorization: Basic c3UzZzRnbzZzazc6amkzOTQ1NHh1L14=
```

Всички API заявки изискват тази аутентикация.

---

## 📝 Обща архитектура на API-то

```
[Browser] ←WebSocket→ [Flask :5000] ←HTTP/Basic Auth→ [Majority Radio :80]
                                                                     ↕
                                                          [Album Art :8080]
```

**Нашият сървър (Flask)** е proxy — получава команди от браузъра и ги превежда към радиото.

---

## 🐛 Известни проблеми / Заобикаляния

| Проблем | Заобикаляне |
|---------|-------------|
| `/playinfo` → `NO_SUPPORT` | Ръчно state tracking; emit при всяка setvol/switchMode команда |
| `cur_play_name` не идва от `/init` | Обновява се при PlayFavorite/PlayStation команди |
| Начален volume неизвестен | Показва `—` докато потребителят не натисне VOL +/- |
| `/setfav` → FAIL | Добавянето на любими не работи |
| `/switchMode` → `NO_SUPPORT` | За INET: навигация с `/gochild?id=87`; FM/DAB/BT/AUX menu ID-та не са открити |
| Root menu ID неизвестен | Browser зарежда от `cur_play_menu_id` или се опитва с id=0 |
| Album art е на порт 8080 | Проксирано чрез `/api/albumart`; ползва се и за station-change detection |

---

## 🧪 Как да тестваш нови endpoints

```bash
# Базова команда за тест
curl -u "su3g4go6sk7:ji39454xu/^" http://192.168.11.16/{endpoint}

# Примери:
curl -u "su3g4go6sk7:ji39454xu/^" http://192.168.11.16/getvol
curl -u "su3g4go6sk7:ji39454xu/^" http://192.168.11.16/playinfo
curl -u "su3g4go6sk7:ji39454xu/^" http://192.168.11.16/switchMode?mode=0
curl -u "su3g4go6sk7:ji39454xu/^" http://192.168.11.16/playControl?play=1
curl -u "su3g4go6sk7:ji39454xu/^" http://192.168.11.16/list?id=0&start=1&count=50
curl -u "su3g4go6sk7:ji39454xu/^" http://192.168.11.16/list?id=52&start=1&count=250
curl -u "su3g4go6sk7:ji39454xu/^" http://192.168.11.16/goBackward
curl -u "su3g4go6sk7:ji39454xu/^" http://192.168.11.16/goForward
```

За Windows PowerShell:
```powershell
$cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("su3g4go6sk7:ji39454xu/^"))
Invoke-WebRequest -Uri "http://192.168.11.16/getvol" -Headers @{ Authorization = "Basic $cred" }
```

---

*Последна актуализация: 2026-03-08 — базирана на HAR capture `192.168.11.16_2026_03_08_16_06_24.har` и session log файлове [292]-[322]*
 Root menu ID и FM/DAB menu ID-та — без тях смяната на source не е възможна. Добрият начин е да логнеш още HAR сесии докато навигираш в Android приложението между FM/DAB/INET.
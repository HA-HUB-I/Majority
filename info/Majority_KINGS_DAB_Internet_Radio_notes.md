
# Majority Kings Internet DAB+ Radio - Notes

A collection of notes on the inner workings of the majority kings radio.


## Features

**Media:**

- Internet Radio
- Spotify Connect
- IR Remote Control
- DAB/DAB+
- FM
- Bluetooth
- AUX In
- USB - Play & Charge. USB supports MP2/MP3/AAC/FLAC/OGG/WMA/WAV
- Media Centre with UPNP
- colour LCD screen

**Functionality Features:**

- 150+ preset options for internet, DAB/DAB+ and FM
- Dual Alarm Clock
- Local Weather Display

## Software:

There is an http server listening on port 8080, static content is located in `/UIData` The CSS styles etc referenced within the html were not there.

UIProto is the heart of the radio. A statically compiled application that listens to port 80, launches mplayer , displays information on the screen, and much more. By the number of references to the name of this binary on the Internet, it seems that it was developed by an outsourcing company (mediayou.net) for most Chinese Internet radios.

UIProto saves the favorites playlist in binary format to the file /flash/myradio.cfg . It is possible to read it through the terminal output, but only as text. To get the file completely I had to sweat a little. Fortunately, busybox on the radio is compiled with support for the ftpput and ftpget commands . I used them to copy the file to the computer for further study, after setting up the FTP server.


***

## Interface

Port 80 HTTP server, identifies as `magic iradio`


## API Reference

Using invalid commands returns

```xml
<result>
<rt>INVALID_CMD</rt>
</result>
```

Doing things it doesnt undertsand:

`GET ../../../tmp/wifi.cfg`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
	<rt>NO_SUPPORT</rt>
</result>
```

`GET /GetSystemInfo HTTP/1.1`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<menu>
    <SW_Ver>AD9THCCR-i801h-i724**ad-i725a-(DB:20210527)</SW_Ver>
    <wifi_info>
        <status>connected</status>
        <MAC>74EE2AE9298A</MAC>
        <SSID>FREE_WIFI!</SSID>
        <Signal>0</Signal>
        <Encryption>--</Encryption>
        <IP>192.168.1.10</IP>
        <Subnet>255.255.255.0</Subnet>
        <Gateway>192.168.1.1</Gateway >
        <DNS1>192.168.1.1</DNS1>
        <DNS2>8.8.8.8</DNS2>
    </wifi_info>
</menu>
```
### INIT
`GET /init?language=en`

`GET /init?language=de`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
    <id>1</id>
    <version>i80120180801h</version>
    <lang>en</lang>
    <wifi_set_url>http://192.168.78.1/scan_wifi</wifi_set_url>
    <ptver>20170822</ptver>
    <hotkey_fav>1</hotkey_fav>
    <push_talk>1</push_talk>
    <leave_msg>1</leave_msg>
    <leave_msg_ios>1</leave_msg_ios>
    <M7_SUPPORT>0</M7_SUPPORT>
    <SMS_SUPPORT>0</SMS_SUPPORT>
    <MKEY_SUPPORT>0</MKEY_SUPPORT>
    <UART_CD>1</UART_CD>
    <PlayMode>1</PlayMode>
    <SWUpdate>NO</SWUpdate>
</result>
```
***Note the error in the address for the wifi scan URL above***

## hotkeylist
`GET /hotkeylist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<menu>
    <item_total>5</item_total>
    <item_return>5</item_return>
    <item>
        <id>75_256</id>
        <status>emptyfile</status>
        <name>Empty</name>
    </item>
    <item>
        <id>75_770</id>
        <status>emptyfile</status>
        <name>Empty</name>
    </item>
    <item><id>75_4</id>
    <status>emptyfile</status>
    <name>Empty</name>
    </item>
    <item>
        <id>75_0</id>
        <status>emptyfile</status>
        <name>Empty</name>
        </item>
    <item>
	 <id>75_0</id>
	 <status>emptyfile</status>
	 <name>Empty</name>
    </item>
</menu>

```
# List

`GET /list?id=1&start=1&count=15`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<menu>
  <item_total>10</item_total>
  <item_return>10</item_return>
  <item>
    <id>87</id>
    <status>content</status>
    <name>Local Radio</name>
  </item>
  <item>
    <id>52</id>
    <status>content</status>
    <name>Internet Radio</name>
  </item>
  <item>
    <id>2</id>
    <status>content</status>
    <name>Media Center</name>
  </item>
  <item>
    <id>5</id>
    <status>content</status>
    <name>FM</name>
  </item>
  <item>
    <id>91</id>
    <status>content</status>
    <name>DAB/DAB+</name>
  </item>
  <item>
    <id>146</id>
    <status>content</status>
    <name>CD</name>
  </item>
  <item>
    <id>3</id>
    <status>content</status>
    <name>Information Center</name>
  </item>
  <item>
    <id>47</id>
    <status>content</status>
    <name>AUX</name>
  </item>
  <item>
    <id>104</id>
    <status>content</status>
    <name>Bluetooth</name>
  </item>
  <item>
    <id>6</id>
    <status>content</status>
    <name>Configuration</name>
  </item>
</menu>
```

`GET /list?id=91&start=1&count=500`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<menu>
  <item_total>89</item_total>
  <item_return>10</item_return>
  <item>
    <id>91_1</id>
    <status>file</status>
    <name>Absolute C Rock </name>
  </item>
  <item>
    <id>91_2</id>
    <status>file</status>
    <name>Absolute C Rock </name>
  </item>
  <item>
    <id>91_3</id>
    <status>file</status>
    <name>Absolute Country </name>
  </item>
  <item>
    <id>91_4</id>
    <status>file</status>
    <name>Absolute Country </name>
  </item>
  <item>
    <id>91_5</id>
    <status>file</status>
    <name>Absolute Rad 80s </name>
  </item>
  <item>
    <id>91_6</id>
    <status>file</status>
    <name>Absolute Rad 90s </name>
  </item>
  <item>
    <id>91_7</id>
    <status>file</status>
    <name>Absolute Radio   </name>
  </item>
  <item>
    <id>91_8</id>
    <status>file</status>
    <name>BBC Lancashire   </name>
  </item>
  <item>
    <id>91_9</id>
    <status>file</status>
    <name>BBC Merseyside   </name>
  </item>
  <item>
    <id>91_10</id>
    <status>file</status>
    <name>BBC R Cymru 2    </name>
  </item>
</menu>
```
# gochild

`GET /gochild?id=91`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <id>91</id>
</result>
```
# playinfo
`GET /playinfo`


```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>FAIL</result>
```
When playing media (DAB radio in this case)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
    <vol>3</vol>
    <mute>0</mute>
    <status>Playing </status>
    <Signal>1</Signal>
</result>
```

`GET /DABhotkeylist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<menu>
  <item_total>5</item_total>
  <item_return>5</item_return>
  <item>
    <id>137_0</id>
    <status>file</status>
    <name>Smooth Chill     </name>
  </item>
  <item>
    <id>137_1</id>
    <status>emptyfile</status>
    <name>Empty</name>
  </item>
  <item>
    <id>137_2</id>
    <status>emptyfile</status>
    <name>Empty</name>
  </item>
  <item>
    <id>137_3</id>
    <status>emptyfile</status>
    <name>Empty</name>
  </item>
  <item>
    <id>137_4</id>
    <status>emptyfile</status>
    <name>Empty</name>
  </item>
</menu>
```
`GET /playDABhotkey?key=1`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <id>137</id>
  <rt>OK</rt>
</result>
```

`GET /LocalPlay?url=http://192.168.1.100/msg.wav&name=intercom`

seams to work only for special files/domains

```xml
```

`GET /LocalPlay?url=http://192.168.1.100/msg.wav&save=1`

```xml
<result><rt>OK</rt></result>
```

`GET /play_stn?id=91_6`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <id>91_6</id>
  <isfav>0</isfav>
</result>
```
`GET /irdevice.xml`

```xml
<?xml version="1.0"?>
<root>
<device>
<friendlyName>AirMusic</friendlyName>
</device>
</root>
```

`GET /stop`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>OK</result>
```
`GET /exit`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>OK</result>
```

## Sendkey from Remote Control
`GET /Sendkey?key=2`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <rt>OK</rt>
</result>
```

Remote Control Keys

| Key | Description |
|-----|-------------|
| 2  | UP          |
| 3  | Down |
| 4  | LEFT        |
| 5  | Right |
| 6  | ENTER       |
| 8  | MUTE        |
| 9  | Vol+ |
| 10 | Vol - |
| 28 | Mode |
| 1  | Home |
| 15 | Star |
| 168| KEY |
| 12 | Sleep |
| 11 | Alarm |
| 14 | Light |
| 32 | prev |
| 29 | play/pause |
| 31 | next |
|115 | 1 |
|116 | 2 |
|116 | 3|
|117 | 4 |
|118 | 5 |
|19  | EQ |
|106 | OFF |
| 7  |  |

`GET /back`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <id>52</id>
</result>
```

`http://<RADIO IP>:8080/playlogo.jpg
Reurns Radio Staion Logo if transmitted.

`GET /background_play_status`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <sid>6</sid>
  <playtime_left>00:00:00</playtime_left>
  <vol>9</vol>
  <mute>0</mute>
</result>
```
`GET /GetFMFAVlist`

If there are no FM favourites:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<menu>
  <item_total>0</item_total>
  <item_return>0</item_return>
</menu>
```
If there are favourites:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<menu>
	<item_total>26</item_total>
	<item_return>26</item_return>
	<item>
		<id>1</id>
		<Freq>87.60</Freq>
	</item>
	<item>
		<id>2</id>
		<Freq>88.70</Freq>
	</item>
	<item>
		<id>3</id>
		<Freq>89.10</Freq>
	</item>
	<item>
		<id>4</id>
		<Freq>89.50</Freq>
	</item>
	<item>
		<id>5</id>
		<Freq>90.30</Freq>
	</item>
	<item>
		<id>6</id>
		<Freq>91.70</Freq>
	</item>
	<item>
		<id>7</id>
		<Freq>92.30</Freq>
	</item>
	<item>
		<id>8</id>
		<Freq>93.00</Freq>
	</item>
	<item>
		<id>9</id>
		<Freq>94.20</Freq>
	</item>
	<item>
		<id>10</id>
		<Freq>95.00</Freq>
	</item>
	<item>
		<id>11</id>
		<Freq>96.00</Freq>
	</item>
	<item>
		<id>12</id>
		<Freq>97.10</Freq>
	</item>
	<item>
		<id>13</id>
		<Freq>98.10</Freq>
	</item>
	<item>
		<id>14</id>
		<Freq>99.20</Freq>
	</item>
	<item>
		<id>15</id>
		<Freq>100.00</Freq>
	</item>
	<item>
		<id>16</id>
		<Freq>100.60</Freq>
	</item>
	<item>
		<id>17</id>
		<Freq>102.90</Freq>
	</item>
	<item>
		<id>18</id>
		<Freq>103.20</Freq>
	</item>
	<item>
		<id>19</id>
		<Freq>103.60</Freq>
	</item>
	<item>
		<id>20</id>
		<Freq>104.00</Freq>
	</item>
	<item>
		<id>21</id>
		<Freq>104.50</Freq>
	</item>
	<item>
		<id>22</id>
		<Freq>105.10</Freq>
	</item>
	<item>
		<id>23</id>
		<Freq>106.40</Freq>
	</item>
	<item>
		<id>24</id>
		<Freq>106.80</Freq>
	</item>
	<item>
		<id>25</id>
		<Freq>107.40</Freq>
	</item>
	<item>
		<id>26</id>
		<Freq>108.00</Freq>
	</item>
</menu>
```
`GET /GotoFMfav?fav=5`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>OK</result>
```

`GET /setvol?vol=9&mute=0`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <vol>9</vol>
  <mute>0</mute>
</result>
```

`GET /GetFMStatus`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <vol>1</vol>
  <mute>0</mute>
  <Signal>3</Signal>
  <Sound>STEREO</Sound>
  <Search>FALSE</Search>
  <Freq>90.30</Freq>
  <RDS> </RDS>
</result>
```

`GET /GetBTStatus`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <vol>1</vol>
  <mute>0</mute>
  <Status>2</Status>
</result>
```
## Search for station called 'hits'
`GET /searchstn?str=hits`
-> returns id=100
```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <id>100</id>
  <rt>OK</rt>
</result>
```

`GET /gochild?id=100`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
  <id>100</id>
</result>
```

Search Results
`GET /list?id=100&start=1&count=100`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<menu>
	<item_total>248</item_total>
	<item_return>20</item_return>
	<item>
		<id>100_1</id>
		<status>file</status>
		<name>#%RD RADIO.DISCOunt</name>
	</item>
	<item>
		<id>100_2</id>
		<status>file</status>
		<name>#POPHITS</name>
	</item>
	<item>
		<id>100_3</id>
		<status>file</status>
		<name>#Pop Radio</name>
	</item>
	<item>
		<id>100_4</id>
		<status>file</status>
		<name>'t Is Vloms Radio</name>
	</item>
	<item>
		<id>100_5</id>
		<status>file</status>
		<name>'MEGA RADIO</name>
	</item>
	<item>
		<id>100_6</id>
		<status>file</status>
		<name>(((EBM Radio)))</name>
	</item>
	<item>
		<id>100_7</id>
		<status>file</status>
		<name>(a)ac Radio FM</name>
	</item>
	<item>
		<id>100_8</id>
		<status>file</status>
		<name>1 Classic</name>
	</item>
	<item>
		<id>100_9</id>
		<status>file</status>
		<name>1 HITS 50s</name>
	</item>
	<item>
		<id>100_10</id>
		<status>file</status>
		<name>1 HITS 60s</name>
	</item>
	<item>
		<id>100_11</id>
		<status>file</status>
		<name>1 HITS 70s</name>
	</item>
	<item>
		<id>100_12</id>
		<status>file</status>
		<name>1 HITS 80s</name>
	</item>
	<item>
		<id>100_13</id>
		<status>file</status>
		<name>1 HITS 90s</name>
	</item>
	<item>
		<id>100_14</id>
		<status>file</status>
		<name>1 MASTER HIP-HOP</name>
	</item>
	<item>
		<id>100_15</id>
		<status>file</status>
		<name>1 Music Radio</name>
	</item>
	<item>
		<id>100_16</id>
		<status>file</status>
		<name>1 Pure EDM Radio</name>
	</item>
	<item>
		<id>100_17</id>
		<status>file</status>
		<name>1 Radio Dance</name>
	</item>
	<item>
		<id>100_18</id>
		<status>file</status>
		<name>1 Radio Jazz</name>
	</item>
	<item>
		<id>100_19</id>
		<status>file</status>
		<name>1 Radio Lounge</name>
	</item>
	<item>
		<id>100_20</id>
		<status>file</status>
		<name>1-Dance</name>
	</item>
</menu>
```
choose a station from the list:

`GET /play_url?id=154_2`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<result>
 <url>http://b1.mediayou.net/embedded/playURL_sleep.php?id=2&sc=N9XX_AAC</url>
</result>
```
Note the parameter 'sc' has the value 'N9XX_AAC', the radio uses a N32903U5DN processor, which can decode an AAC stream.

`GET /set_dname?name=AirMusic`
```html
<html><head><meta content="text/html; charset=UTF-8" http-equiv="Content-Type"><meta content="width=device-width, initial-scale=1.0, user-scalable=no, minimum-scale=1.0, maximum-scale=1.0" name="viewport"><title>AirMusic</title><link type="text/css" rel="stylesheet" href="http://192.168.1.10:8080/style.css">
<script src="http://192.168.1.10:8080/magic.js" type="text/javascript"></script></head><body>
<script language="JavaScript">
function scan()
{ window.location ="/scan_wifi";}
</script>
<script language="JavaScript">
function SaveDrvName( dname )
{ window.location ="/set_dname?name="+document.getElementById(dname).value;}
</script>
<div class="cls_body">
<div class="cls_topbar_title1">Setting</div>
<div class="cls_mid"><div class="contentf_bor"><table id="aplist" class="contentf1">
<tbody>
<tbody><tr class="cls_contitem_top" onclick="SetDevName("AirMusic","")">
<td class="cls_contitem_i1_aplist">Change Device Name
<div id="wifi_AirMusic" class="cls_div" style="visibility:hidden;display:none;border:1px solid #666666;border-top:none;background-color:#373737;">Device Name :
<input id="inp_AirMusic" name="inp_AirMusic" type="text" class="form-text" size="12" maxlength="32">
<br><div class="cls_center1"><input type="button" class="cls_btn" onClick="SaveDrvName('inp_AirMusic');" value="Save">
</div></div></td>
<td class="cls_contitem_i2_aplist">
<img id="unfold_AirMusic" src="http://192.168.1.10:8080/tab_unfold.png" height="36" width="36" onClick="SetDevName('AirMusic','');">
<img id="fold_AirMusic" src="http://192.168.1.10:8080/tab_fold.png" height="36" width="36" onClick="SetDevName('AirMusic','cancel');" style="visibility:hidden;display:none;" >
</td></tr></tbody>
<tr class="cls_contitem_top" onclick="scan()">
<tbody><td class="cls_contitem_i1_aplist">Wifi Setting
<td class="cls_contitem_i2_aplist">
<img id="unfold_AirMusic" src="http://192.168.1.10:8080/tab_right.png" height="36" width="36" onClick="scan();">
</td></tr></tbody>
<tbody><tr class="cls_contitem_top" onclick="SWDisp("AirMusic","")">
<td class="cls_contitem_i1_aplist">Software Update
<div id="sw_AirMusic" class="cls_div" style="visibility:hidden;display:none;border:1px solid #666666;border-top:none;background-color:#373737;">AD9THCCR-i801h-i724**ad-<br>i725a-(DB:20210527)
</div></td>
<td class="cls_contitem_i2_aplist">
<img id="swunfold_AirMusic" src="http://192.168.1.10:8080/tab_unfold.png" height="36" width="36" onClick="SWDisp('AirMusic','');">
<img id="swfold_AirMusic" src="http://192.168.1.10:8080/tab_fold.png" height="36" width="36" onClick="SWDisp('AirMusic','cancel');" style="visibility:hidden;display:none;" >
</td></tr></tbody>
</table></div></div></div></body></html>
```
`GET /scan_wifi`

`GET /scan_results`

`GET /con_result`

```xml
<result>OK</result>
```

## UPNP


## Appendix

Firmware Update

The firmware can be updated via MediaU or local USB adapter. MediaU also provides the Radio stream library, weather and stock data.
The firmware update via MediaU goes like this:

My system version shows: BT000D5A-a809-a721-a803-c723

UIProto makes this call to MediaU: `http://b1.mediayou.net/cgi-bin/GetSW?PD=%s&MP=%s&DS=%s&UI=%s%s&OSD=%s&SER1=%s&SER2=%s`

- PD= ProductID (BT000D5A)
- MP= mplayer version (a80320100803) (a803) /tmp/mv.dat
- DS= 
- UI= UIProto version
- OSD= W950OSD version (a80920100809) (a809) /tmp/W950OSDVer.dat
- SER1= 000000445588
- SER2= 20100721 ?

`GET http://b1.mediayou.net/cgi-bin/GetSW?PD=BT000D5A` > [GetFile]vps.mediayou.net/update/stn-d201_005.dat.gz.upd
That gives for this device only the station update list.

For other similar devices:

http://b1.mediayou.net/cgi-bin/GetSW?PD=HS0015BL > [GetFile]vps.mediayou.net/update/stn-d125_SW75.dat.gz.upd
earlier it gave this :)
[GetFile]download.mediayou.net/mplayer-c619_HS15.gz.upd
[GetFile]download.mediayou.net/UIProto-ba18_kicker.gz.upd
[GetFile]download.mediayou.net/W950OSD-b719_kicker.gz.upd

http://b1.mediayou.net/cgi-bin/GetSW?PD=HS00015A > [GetFile]vps.mediayou.net/update/stn-d201_005.dat.gz.upd
earlier it gave this :)
[GetFile]www.mediayou.net/SWUpdate/mplayer-a612_HS.gz.upd
[GetFile]www.mediayou.net/SWUpdate/UIProto-a612_HS.gz.upd
[GetFile]www.mediayou.net/SWUpdate/W950OSD-a612_HS.gz.upd 

The online firmware update downloads these [Getfuile]*.gz.upd files. 

The process is as follows:
- files are downloaded in /tmp/*.upd.tmp
- then /mplayer/mrun CRC is run to make /tmp/*.gz.aaa files 
- /tmp/*.gz.aaa files are renamed to /tmp/*.gz then updated by UIProto

type `/mplayer/mrun UPDATE`  or use Software Update on device to complete the process.
If you downloaded the upd file manually you can copy them from an USB stick to /tmp, run /mplayer/mrun CRC,  rename them from *.gz.aaa to *.gz and run /mplayer/mrun UPDATE

Files that can be flashed / Software Updated from an USB stick are:

/attach/ms0/UIProto.gz   - the GUI
/attach/ms0/mplayer.gz  - streaming player
/attach/ms0/stn.dat.gz   - internet radio list
/attach/ms0/W950OSD.gz - OSD manager
/attach/ms0/fontv  - the font bitmap file
/attach/ms0/info   -  ???
/attach/ms0/flashbin  - 8 Mb flash file, whole firmware
/attach/ms0/logobin  - the boot logo


Problems

The main problem with the device was that it didn't respond to the remote after a few days of operation and standby cycles.
Afyter decompiling UIProto I found that the CPU has 3 clock states. The lowest one is 32 Mhz by default. That turned out to be the problem. Probably some device drivers (like ir and wifi) couldn't handle that freq. So I changed it to 64 Mhz in the UIProto binary. It worked.
echo 192 > /sys/devices/platform/nuc930-clk/clock
echo 144 > /sys/devices/platform/nuc930-clk/clock
echo 32 > /sys/devices/platform/nuc930-clk/clock << changed to 64, 32 problems with ir and wifi


## Improvements

Adding Spotify Connect
Adding DNLA
  
## Author

- [@hsiboy](https://www.github.com/hsiboy)

  


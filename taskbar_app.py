#!/usr/bin/env python3
"""
Windows Taskbar Integration for Majority Radio Controller
=========================================================
Provides a system tray icon, a borderless popup control panel, and Windows
thumbnail toolbar buttons (Volume −, Mute, Volume +, Prev Preset, Next Preset)
that appear when hovering over the taskbar icon.

Usage:
    python taskbar_app.py          # starts Flask server + tray icon + popup
    python taskbar_app.py --no-server  # tray only (Flask server already running)

Requirements (Windows):
    pip install pystray Pillow pywin32
Requirements (non-Windows / fallback):
    pip install pystray Pillow
"""

import ctypes
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk

import requests
from PIL import Image, ImageDraw, ImageFont

try:
    import pystray
    from pystray import MenuItem as item, Menu
    HAS_PYSTRAY = True
except Exception:
    HAS_PYSTRAY = False

# Windows-only thumbnail toolbar support via pywin32 + comtypes
IS_WINDOWS = sys.platform == "win32"
HAS_WIN32 = False

if IS_WINDOWS:
    try:
        import win32gui
        import win32con
        HAS_WIN32 = True
    except ImportError:
        pass

log = logging.getLogger(__name__)

API_BASE = "http://localhost:5000"
POLL_INTERVAL = 2  # seconds between status refreshes in popup

# ── Color scheme (matches existing dark UI) ───────────────────────────────────
BG      = "#0d0d0d"
SURFACE = "#161616"
BORDER  = "#2a2a2a"
GREEN   = "#00e676"
DIM     = "#4a4a4a"
TEXT    = "#e0e0e0"
RED     = "#ff5252"

# ── Thumbnail toolbar button IDs ──────────────────────────────────────────────
BTN_PREV    = 1001
BTN_VOLDOWN = 1002
BTN_MUTE    = 1003
BTN_VOLUP   = 1004
BTN_NEXT    = 1005


# ══════════════════════════════════════════════════════════════════════════════
# Windows COM / Win32 definitions (only compiled when pywin32 is present)
# ══════════════════════════════════════════════════════════════════════════════

if IS_WINDOWS and HAS_WIN32:
    import ctypes.wintypes as wintypes

    # ── THUMBBUTTON structure (Windows SDK) ───────────────────────────────────
    class THUMBBUTTON(ctypes.Structure):
        _pack_ = 1
        _fields_ = [
            ("dwMask",  ctypes.c_uint32),
            ("iId",     ctypes.c_uint),
            ("iBitmap", ctypes.c_uint),
            ("hIcon",   ctypes.c_void_p),
            ("szTip",   ctypes.c_wchar * 260),
            ("dwFlags", ctypes.c_uint32),
        ]

    # dwMask flags
    THB_ICON    = 0x0002
    THB_TOOLTIP = 0x0004
    THB_FLAGS   = 0x0008
    # dwFlags
    THBF_ENABLED      = 0x0000
    THBF_NOBACKGROUND = 0x0004

    WM_TASKBARBUTTONCREATED = win32gui.RegisterWindowMessage(
        "TaskbarButtonCreated")

    # ── ITaskbarList3 COM interface (full vtable, via comtypes) ───────────────
    _HAS_COMTYPES = False
    try:
        import comtypes
        import comtypes.client

        CLSID_TaskbarList = comtypes.GUID(
            "{56FDF344-FD6D-11D0-958A-006097C9A090}")

        class _ITaskbarList(comtypes.IUnknown):
            _iid_ = comtypes.GUID(
                "{56FDF342-FD6D-11D0-958A-006097C9A090}")
            _methods_ = [
                comtypes.COMMETHOD([], comtypes.HRESULT, "HrInit"),
                comtypes.COMMETHOD([], comtypes.HRESULT, "AddTab",
                    (['in'], ctypes.c_void_p, "hwnd")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "DeleteTab",
                    (['in'], ctypes.c_void_p, "hwnd")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "ActivateTab",
                    (['in'], ctypes.c_void_p, "hwnd")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "SetActiveAlt",
                    (['in'], ctypes.c_void_p, "hwnd")),
            ]

        class _ITaskbarList2(_ITaskbarList):
            _iid_ = comtypes.GUID(
                "{602D4995-B13A-429B-A66E-1935E44F4317}")
            _methods_ = [
                comtypes.COMMETHOD([], comtypes.HRESULT,
                    "MarkFullscreenWindow",
                    (['in'], ctypes.c_void_p, "hwnd"),
                    (['in'], ctypes.c_int, "fFullscreen")),
            ]

        class ITaskbarList3(_ITaskbarList2):
            """Full COM interface for Windows taskbar list operations."""
            _iid_ = comtypes.GUID(
                "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}")
            _methods_ = [
                comtypes.COMMETHOD([], comtypes.HRESULT, "SetProgressValue",
                    (['in'], ctypes.c_void_p, "hwnd"),
                    (['in'], ctypes.c_uint64, "ullCompleted"),
                    (['in'], ctypes.c_uint64, "ullTotal")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "SetProgressState",
                    (['in'], ctypes.c_void_p, "hwnd"),
                    (['in'], ctypes.c_int, "tbpFlags")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "RegisterTab",
                    (['in'], ctypes.c_void_p, "hwndTab"),
                    (['in'], ctypes.c_void_p, "hwndMDI")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "UnregisterTab",
                    (['in'], ctypes.c_void_p, "hwndTab")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "SetTabOrder",
                    (['in'], ctypes.c_void_p, "hwndTab"),
                    (['in'], ctypes.c_void_p, "hwndInsertBefore")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "SetTabActive",
                    (['in'], ctypes.c_void_p, "hwndTab"),
                    (['in'], ctypes.c_void_p, "hwndMDI"),
                    (['in'], ctypes.c_uint32, "dwReserved")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "ThumbBarAddButtons",
                    (['in'], ctypes.c_void_p, "hwnd"),
                    (['in'], ctypes.c_uint, "cButtons"),
                    (['in'], ctypes.POINTER(THUMBBUTTON), "pButton")),
                comtypes.COMMETHOD([], comtypes.HRESULT,
                    "ThumbBarUpdateButtons",
                    (['in'], ctypes.c_void_p, "hwnd"),
                    (['in'], ctypes.c_uint, "cButtons"),
                    (['in'], ctypes.POINTER(THUMBBUTTON), "pButton")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "ThumbBarSetImageList",
                    (['in'], ctypes.c_void_p, "hwnd"),
                    (['in'], ctypes.c_void_p, "himl")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "SetOverlayIcon",
                    (['in'], ctypes.c_void_p, "hwnd"),
                    (['in'], ctypes.c_void_p, "hIcon"),
                    (['in'], ctypes.c_wchar_p, "pszDescription")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "SetThumbnailTooltip",
                    (['in'], ctypes.c_void_p, "hwnd"),
                    (['in'], ctypes.c_wchar_p, "pszTip")),
                comtypes.COMMETHOD([], comtypes.HRESULT, "SetThumbnailClip",
                    (['in'], ctypes.c_void_p, "hwnd"),
                    (['in'], ctypes.POINTER(wintypes.RECT), "prcClip")),
            ]

        _HAS_COMTYPES = True
    except Exception as _e:
        log.debug("comtypes unavailable for ITaskbarList3: %s", _e)

    def _pil_to_hicon(img: Image.Image) -> int:
        """Convert a 20×20 PIL image to a Windows HICON via a temp ICO file."""
        img_resized = img.convert("RGBA").resize((20, 20), Image.LANCZOS)
        fd, tmp_path = tempfile.mkstemp(suffix=".ico")
        try:
            os.close(fd)
            img_resized.save(tmp_path, format="ICO")
            hicon = win32gui.LoadImage(
                0, tmp_path, win32con.IMAGE_ICON,
                20, 20,
                win32con.LR_LOADFROMFILE | win32con.LR_LOADTRANSPARENT,
            )
            return hicon
        except Exception as exc:
            log.debug("_pil_to_hicon failed: %s", exc)
            return 0
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _create_itaskbarlist3():
        """Instantiate ITaskbarList3 via COM and return the proxy."""
        if not _HAS_COMTYPES:
            return None
        try:
            obj = comtypes.client.CreateObject(
                CLSID_TaskbarList, interface=ITaskbarList3)
            obj.HrInit()
            return obj
        except Exception as exc:
            log.warning("Could not create ITaskbarList3: %s", exc)
            return None


# ══════════════════════════════════════════════════════════════════════════════
# Radio API client
# ══════════════════════════════════════════════════════════════════════════════

class RadioClient:
    """Thin wrapper around the Flask server's REST API."""

    def status(self) -> dict:
        try:
            r = requests.get(f"{API_BASE}/api/status", timeout=2)
            return r.json()
        except Exception:
            return {}

    def hotkeys(self) -> list:
        try:
            r = requests.get(f"{API_BASE}/api/hotkeys", timeout=2)
            data = r.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def command(self, cmd: str, **params) -> dict:
        try:
            payload = {"command": cmd, **params}
            r = requests.post(f"{API_BASE}/api/command", json=payload, timeout=2)
            return r.json()
        except Exception:
            return {}

    def volume_up(self):
        self.command("VolumeUp")

    def volume_down(self):
        self.command("VolumeDown")

    def mute(self):
        self.command("Mute")

    def play_preset(self, index: int):
        """Play internet-radio preset (1-based index)."""
        self.command("PlayFavorite", Index=index)

    def play_next_preset(self):
        self.command("Next")

    def play_prev_preset(self):
        self.command("Previous")


# ══════════════════════════════════════════════════════════════════════════════
# Icon builder (PIL)
# ══════════════════════════════════════════════════════════════════════════════

def _make_tray_icon(size: int = 64, muted: bool = False) -> Image.Image:
    """Create a simple radio-wave icon for the system tray."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = (0, 230, 118)   # --green
    if muted:
        c = (255, 82, 82)   # --red

    # Outer arc
    margin = 6
    d.arc([margin, margin, size - margin, size - margin],
          start=200, end=340, fill=c, width=4)
    # Middle arc
    m2 = 16
    d.arc([m2, m2, size - m2, size - m2],
          start=200, end=340, fill=c, width=4)
    # Speaker body
    cx, cy = size // 2, size // 2 + 4
    sw, sh = 10, 14
    d.rectangle([cx - sw // 2, cy - sh // 2, cx + sw // 2, cy + sh // 2],
                fill=c)
    # Speaker cone
    d.polygon([
        (cx + sw // 2, cy - sh // 2 - 2),
        (cx + sw // 2 + 8, cy - sh // 2 - 8),
        (cx + sw // 2 + 8, cy + sh // 2 + 8),
        (cx + sw // 2, cy + sh // 2 + 2),
    ], fill=c)
    return img


def _make_button_icon(symbol: str, size: int = 20) -> Image.Image:
    """Create a small icon with a text symbol for thumbnail toolbar buttons."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        fnt = ImageFont.truetype("arial.ttf", size - 2)
    except (OSError, IOError):
        fnt = ImageFont.load_default()
    bbox = d.textbbox((0, 0), symbol, font=fnt)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) // 2, (size - th) // 2), symbol,
           font=fnt, fill=(0, 230, 118))
    return img


# ══════════════════════════════════════════════════════════════════════════════
# Windows Thumbnail Toolbar
# ══════════════════════════════════════════════════════════════════════════════

class ThumbnailToolbar:
    """
    Adds ⏮ Vol− Mute Vol+ ⏭ buttons to the Windows thumbnail toolbar of a
    given window handle (HWND).  Requires pywin32 and comtypes; degrades
    gracefully to a no-op on non-Windows or when those libraries are absent.

    Windows sends a WM_TASKBARBUTTONCREATED message when the taskbar is ready
    to accept thumbnail buttons.  We subclass the window procedure to intercept
    that message and call ITaskbarList3::ThumbBarAddButtons, then handle
    WM_COMMAND for subsequent button clicks.
    """

    _BUTTONS_DEF = [
        (BTN_PREV,    "⏮", "Previous preset"),
        (BTN_VOLDOWN, "🔉", "Volume down"),
        (BTN_MUTE,    "🔇", "Mute / Unmute"),
        (BTN_VOLUP,   "🔊", "Volume up"),
        (BTN_NEXT,    "⏭", "Next preset"),
    ]

    def __init__(self, hwnd: int, radio_client: "RadioClient"):
        self.hwnd = hwnd
        self.api = radio_client
        self._registered = False
        self._buttons = None        # THUMBBUTTON array kept alive
        self._wndproc_ref = None    # WNDPROC reference kept alive

    def setup(self):
        """Subclass the window procedure to handle taskbar messages."""
        if not IS_WINDOWS or not HAS_WIN32:
            return
        try:
            self._build_buttons()
            self._subclass_wndproc()
            self._registered = True
            log.info("Thumbnail toolbar registered (HWND=0x%x)", self.hwnd)
        except Exception as exc:
            log.warning("Thumbnail toolbar setup failed: %s", exc)

    # ── Button array construction ─────────────────────────────────────────────

    def _build_buttons(self):
        n = len(self._BUTTONS_DEF)
        BtnArray = THUMBBUTTON * n
        btns = BtnArray()
        for i, (bid, sym, tip) in enumerate(self._BUTTONS_DEF):
            hicon = _pil_to_hicon(_make_button_icon(sym, 20))
            btns[i].dwMask  = THB_TOOLTIP | THB_FLAGS | THB_ICON
            btns[i].iId     = bid
            btns[i].szTip   = tip
            btns[i].dwFlags = THBF_ENABLED | THBF_NOBACKGROUND
            btns[i].hIcon   = hicon
        self._buttons = btns

    # ── Window-procedure subclassing ──────────────────────────────────────────

    def _subclass_wndproc(self):
        old_wndproc = win32gui.GetWindowLong(self.hwnd, win32con.GWL_WNDPROC)

        def _wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_TASKBARBUTTONCREATED:
                self._register_buttons()
            elif msg == win32con.WM_COMMAND:
                btn_id = wparam & 0xFFFF
                self._handle_button(btn_id)
            return win32gui.CallWindowProc(old_wndproc, hwnd, msg,
                                           wparam, lparam)

        # Keep the WNDPROC reference alive for the lifetime of this object
        self._wndproc_ref = win32gui.WNDPROC(_wndproc)
        win32gui.SetWindowLong(self.hwnd, win32con.GWL_WNDPROC,
                               self._wndproc_ref)

    # ── ThumbBarAddButtons via ITaskbarList3 ──────────────────────────────────

    def _register_buttons(self):
        """Call ITaskbarList3::ThumbBarAddButtons with the prepared array."""
        if self._buttons is None:
            return
        tbl3 = _create_itaskbarlist3()
        if tbl3 is None:
            log.warning(
                "ITaskbarList3 unavailable — thumbnail toolbar buttons "
                "will not appear.  Install comtypes: pip install comtypes")
            return
        try:
            n = len(self._BUTTONS_DEF)
            tbl3.ThumbBarAddButtons(self.hwnd, n, self._buttons)
            log.info("ThumbBarAddButtons succeeded (%d buttons)", n)
        except Exception as exc:
            log.warning("ThumbBarAddButtons failed: %s", exc)

    # ── Button click dispatch ─────────────────────────────────────────────────

    def _handle_button(self, btn_id: int):
        handlers = {
            BTN_PREV:    self.api.play_prev_preset,
            BTN_VOLDOWN: self.api.volume_down,
            BTN_MUTE:    self.api.mute,
            BTN_VOLUP:   self.api.volume_up,
            BTN_NEXT:    self.api.play_next_preset,
        }
        fn = handlers.get(btn_id)
        if fn:
            threading.Thread(target=fn, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# Popup Control Panel (tkinter)
# ══════════════════════════════════════════════════════════════════════════════

class PopupWindow:
    """
    Borderless floating control panel that appears above the system taskbar.
    Shows station name, volume controls, mute, playback controls, and up to
    8 preset buttons loaded from the device.
    """

    MAX_PRESETS = 8

    def __init__(self, root: tk.Tk, api: RadioClient):
        self.root = root
        self.api = api
        self.visible = False
        self._poll_job = None
        self._state: dict = {}
        self._hotkeys: list = []
        self._build()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        self.win = tk.Toplevel(self.root)
        self.win.withdraw()
        self.win.overrideredirect(True)   # borderless
        self.win.attributes("-topmost", True)
        self.win.configure(bg=BORDER)    # 1-px border effect via padding

        inner = tk.Frame(self.win, bg=BG)
        inner.pack(padx=1, pady=1, fill="both", expand=True)

        # ── Header bar ────────────────────────────────────────────────────────
        header = tk.Frame(inner, bg=SURFACE, pady=6, padx=10)
        header.pack(fill="x")

        tk.Label(header, text="● MAJORITY RADIO", bg=SURFACE, fg=GREEN,
                 font=("Courier New", 9, "bold"), anchor="w").pack(side="left")

        close_btn = tk.Label(header, text="✕", bg=SURFACE, fg=DIM,
                             font=("Courier New", 10), cursor="hand2", padx=4)
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda _e: self.hide())

        # Drag handle
        header.bind("<Button-1>",  self._drag_start)
        header.bind("<B1-Motion>", self._drag_move)
        self._drag_x = 0
        self._drag_y = 0

        # ── Station / Status ──────────────────────────────────────────────────
        status_frame = tk.Frame(inner, bg=BG, padx=10, pady=6)
        status_frame.pack(fill="x")

        self._lbl_station = tk.Label(
            status_frame, text="—", bg=BG, fg=TEXT,
            font=("Courier New", 10, "bold"),
            wraplength=240, justify="left", anchor="w")
        self._lbl_station.pack(fill="x")

        self._lbl_mode = tk.Label(
            status_frame, text="", bg=BG, fg=DIM,
            font=("Courier New", 8), anchor="w")
        self._lbl_mode.pack(fill="x")

        # ── Volume row ────────────────────────────────────────────────────────
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x")

        vol_frame = tk.Frame(inner, bg=BG, padx=8, pady=6)
        vol_frame.pack(fill="x")

        tk.Label(vol_frame, text="VOL", bg=BG, fg=DIM,
                 font=("Courier New", 7), width=4).pack(side="left")

        self._btn_voldown = self._make_btn(vol_frame, "−", self._vol_down)
        self._btn_voldown.pack(side="left", padx=2)

        self._vol_canvas = tk.Canvas(vol_frame, bg=BG, height=20, width=100,
                                     bd=0, highlightthickness=0)
        self._vol_canvas.pack(side="left", padx=4)

        self._btn_volup = self._make_btn(vol_frame, "+", self._vol_up)
        self._btn_volup.pack(side="left", padx=2)

        self._btn_mute = self._make_btn(vol_frame, "🔇", self._mute, width=3)
        self._btn_mute.pack(side="left", padx=(6, 2))

        self._lbl_vol = tk.Label(vol_frame, text="—", bg=BG, fg=GREEN,
                                 font=("Courier New", 9, "bold"), width=4)
        self._lbl_vol.pack(side="left")

        # ── Playback controls ─────────────────────────────────────────────────
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x")

        pb_frame = tk.Frame(inner, bg=BG, padx=8, pady=4)
        pb_frame.pack(fill="x")

        for sym, cmd in [("⏮", "Previous"), ("⏯", "PlayPause"), ("⏭", "Next")]:
            b = self._make_btn(
                pb_frame, sym,
                lambda c=cmd: threading.Thread(
                    target=lambda _c=c: self.api.command(_c),
                    daemon=True).start(),
                width=3)
            b.pack(side="left", padx=2)

        # ── Favorites ─────────────────────────────────────────────────────────
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x")

        fav_header = tk.Frame(inner, bg=SURFACE, padx=10, pady=3)
        fav_header.pack(fill="x")
        tk.Label(fav_header, text="FAVORITES", bg=SURFACE, fg=DIM,
                 font=("Courier New", 7, "bold")).pack(side="left")

        self._preset_frame = tk.Frame(inner, bg=BG, padx=8, pady=6)
        self._preset_frame.pack(fill="x")

        self._preset_btns: list = []
        for i in range(self.MAX_PRESETS):
            idx = i + 1
            b = tk.Button(
                self._preset_frame,
                text=f"P{idx}", bg=SURFACE, fg=TEXT, relief="flat",
                font=("Courier New", 8), padx=4, pady=3, cursor="hand2",
                activebackground=BORDER, activeforeground=GREEN,
                command=lambda n=idx: self._play_preset(n))
            row, col = divmod(i, 4)
            b.grid(row=row, column=col, padx=2, pady=2, sticky="ew")
            self._preset_frame.columnconfigure(col, weight=1)
            self._preset_btns.append(b)

        # ── Footer link ───────────────────────────────────────────────────────
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x")

        footer = tk.Frame(inner, bg=SURFACE, padx=10, pady=4)
        footer.pack(fill="x")
        open_lbl = tk.Label(footer, text="⧉ Open full control panel",
                            bg=SURFACE, fg=DIM, font=("Courier New", 8),
                            cursor="hand2")
        open_lbl.pack(side="left")
        open_lbl.bind("<Button-1>", lambda _e: self._open_browser())
        open_lbl.bind("<Enter>", lambda _e: open_lbl.config(fg=GREEN))
        open_lbl.bind("<Leave>", lambda _e: open_lbl.config(fg=DIM))

        self.win.bind("<FocusOut>", self._on_focus_out)

    def _make_btn(self, parent, text: str, command, width: int = 2) -> tk.Button:
        return tk.Button(
            parent, text=text, command=command,
            bg=SURFACE, fg=TEXT, relief="flat",
            font=("Courier New", 9), padx=4, pady=2,
            width=width, cursor="hand2",
            activebackground=BORDER, activeforeground=GREEN)

    # ── Drag support ──────────────────────────────────────────────────────────

    def _drag_start(self, event):
        self._drag_x = event.x_root - self.win.winfo_x()
        self._drag_y = event.y_root - self.win.winfo_y()

    def _drag_move(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.win.geometry(f"+{x}+{y}")

    # ── Show / Hide ───────────────────────────────────────────────────────────

    def show(self):
        """Position the popup above the taskbar and reveal it."""
        self._refresh_hotkeys()
        self._position()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.visible = True
        self._schedule_poll()

    def hide(self):
        if self._poll_job:
            self.win.after_cancel(self._poll_job)
            self._poll_job = None
        self.win.withdraw()
        self.visible = False

    def toggle(self):
        if self.visible:
            self.hide()
        else:
            self.show()

    def _position(self):
        """Position in the lower-right corner above the taskbar (~40 px)."""
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        h = self.win.winfo_reqheight()
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        self.win.geometry(f"{w}x{h}+{sw - w - 12}+{sh - h - 50}")

    # ── Auto-hide on focus loss ───────────────────────────────────────────────

    def _on_focus_out(self, _event):
        if self.visible:
            self.win.after(200, self._check_focus)

    def _check_focus(self):
        try:
            focused = self.win.focus_get()
        except Exception:
            focused = None
        if focused is None and self.visible:
            self.hide()

    # ── Polling ───────────────────────────────────────────────────────────────

    def _schedule_poll(self):
        if self.visible:
            self._poll_job = self.win.after(POLL_INTERVAL * 1000, self._poll)

    def _poll(self):
        threading.Thread(target=self._fetch_and_update, daemon=True).start()

    def _fetch_and_update(self):
        st = self.api.status()
        self.win.after(0, lambda: self._apply_state(st))

    def _apply_state(self, st: dict):
        if not self.visible:
            return
        self._state = st
        connected = st.get("connected", False)
        station   = st.get("station_name") or st.get("cur_play_name") or "—"
        mode      = st.get("play_mode", "")
        vol       = st.get("volume", None)
        muted     = st.get("mute", False)
        active_id = str(st.get("active_preset_index", ""))

        self._lbl_station.config(
            text=station if connected else "Not connected")
        mode_str = mode.upper() if mode else ""
        if muted:
            mode_str += "  🔇 MUTED"
        self._lbl_mode.config(text=mode_str)

        # Volume bar
        self._vol_canvas.delete("all")
        if vol is not None:
            pct = vol / 20.0
            w = 100
            self._vol_canvas.create_rectangle(0, 6, w, 14,
                                               fill=BORDER, outline="")
            fill_color = RED if muted else GREEN
            self._vol_canvas.create_rectangle(0, 6, int(w * pct), 14,
                                               fill=fill_color, outline="")
            self._lbl_vol.config(text=str(vol))
        else:
            self._lbl_vol.config(text="—")

        self._btn_mute.config(fg=RED if muted else DIM)

        for i, btn in enumerate(self._preset_btns):
            active = str(i + 1) == active_id
            btn.config(fg=GREEN if active else TEXT,
                       bg=BORDER if active else SURFACE)

        self._schedule_poll()

    # ── Controls ──────────────────────────────────────────────────────────────

    def _vol_up(self):
        threading.Thread(target=self.api.volume_up, daemon=True).start()

    def _vol_down(self):
        threading.Thread(target=self.api.volume_down, daemon=True).start()

    def _mute(self):
        threading.Thread(target=self.api.mute, daemon=True).start()

    def _play_preset(self, index: int):
        threading.Thread(
            target=lambda: self.api.play_preset(index), daemon=True).start()

    def _open_browser(self):
        import webbrowser
        webbrowser.open(API_BASE)

    # ── Preset name loading ───────────────────────────────────────────────────

    def _refresh_hotkeys(self):
        threading.Thread(target=self._fetch_hotkeys, daemon=True).start()

    def _fetch_hotkeys(self):
        keys = self.api.hotkeys()
        self.win.after(0, lambda: self._apply_hotkeys(keys))

    def _apply_hotkeys(self, hotkeys: list):
        self._hotkeys = hotkeys
        for i, btn in enumerate(self._preset_btns):
            if i < len(hotkeys):
                name = hotkeys[i].get("name", f"P{i+1}")
                btn.config(text=(name[:9] + "…") if len(name) > 10 else name)
            else:
                btn.config(text=f"P{i+1}")


# ══════════════════════════════════════════════════════════════════════════════
# System Tray Application (pystray)
# ══════════════════════════════════════════════════════════════════════════════

class TrayApp:
    """
    Manages the system tray icon and coordinates the popup window and
    (on Windows with pywin32) the thumbnail toolbar.
    """

    def __init__(self, api: RadioClient, popup: PopupWindow):
        self.api = api
        self.popup = popup
        self._icon_img = _make_tray_icon()
        self._tray: object = None  # pystray.Icon
        self._muted = False
        self._station = "—"

    # ── Tray menu ─────────────────────────────────────────────────────────────

    def _build_menu(self):
        preset_items = []
        try:
            for i, hk in enumerate(self.api.hotkeys()[:self.popup.MAX_PRESETS]):
                name = hk.get("name", f"Preset {i+1}")
                idx  = i + 1
                preset_items.append(
                    item(name, lambda _, n=idx: self._play_preset(n)))
        except Exception:
            pass

        fav_menu = (Menu(*preset_items) if preset_items
                    else Menu(item("(not connected)", None, enabled=False)))

        return Menu(
            item("Show / Hide Panel",  self._toggle_popup, default=True),
            item("Open in browser",    self._open_browser),
            Menu.SEPARATOR,
            item("Volume +",           lambda _: self._vol_up()),
            item("Volume −",           lambda _: self._vol_down()),
            item("Mute / Unmute",      lambda _: self._mute()),
            Menu.SEPARATOR,
            item("Favorites ▶",        fav_menu),
            Menu.SEPARATOR,
            item("Exit",               self._exit),
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def _toggle_popup(self, *_):
        self.popup.root.after(0, self.popup.toggle)

    def _open_browser(self, *_):
        import webbrowser
        webbrowser.open(API_BASE)

    def _vol_up(self):
        threading.Thread(target=self.api.volume_up, daemon=True).start()

    def _vol_down(self):
        threading.Thread(target=self.api.volume_down, daemon=True).start()

    def _mute(self):
        threading.Thread(target=self.api.mute, daemon=True).start()

    def _play_preset(self, index: int):
        threading.Thread(
            target=lambda: self.api.play_preset(index), daemon=True).start()

    def _exit(self, *_):
        if self._tray:
            self._tray.stop()
        self.popup.root.after(0, self.popup.root.quit)

    # ── Status icon updater ───────────────────────────────────────────────────

    def _status_updater(self):
        """Background thread: refreshes tray icon and tooltip every 2 s."""
        while True:
            try:
                st      = self.api.status()
                muted   = st.get("mute", False)
                station = st.get("station_name") or st.get("cur_play_name") or "—"
                vol     = st.get("volume", "")
                if station != self._station or muted != self._muted:
                    self._station = station
                    self._muted   = muted
                    icon_img  = _make_tray_icon(muted=muted)
                    tooltip   = f"Majority Radio | {station}"
                    if vol:
                        tooltip += f" | Vol {vol}/20"
                    if muted:
                        tooltip += " | MUTED"
                    if self._tray:
                        self._tray.icon  = icon_img
                        self._tray.title = tooltip
                        self._tray.menu  = self._build_menu()
            except Exception:
                pass
            time.sleep(POLL_INTERVAL)

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self):
        if not HAS_PYSTRAY:
            log.error(
                "pystray not installed — system tray icon unavailable. "
                "Run: pip install pystray")
            self.popup.root.mainloop()
            return

        threading.Thread(target=self._status_updater, daemon=True).start()

        def _tray_thread():
            self._tray = pystray.Icon(
                "majority_radio",
                self._icon_img,
                "Majority Radio",
                menu=self._build_menu(),
            )
            self._tray.on_activate = self._toggle_popup
            self._tray.run()

        threading.Thread(target=_tray_thread, daemon=True).start()

        # Show popup on first launch
        self.popup.root.after(500, self.popup.show)

        # tkinter event loop runs on the main thread
        self.popup.root.mainloop()

        if self._tray:
            self._tray.stop()


# ══════════════════════════════════════════════════════════════════════════════
# Flask server launcher
# ══════════════════════════════════════════════════════════════════════════════

def _start_flask_server():
    """Launch server.py as a subprocess and wait up to 10 s for it to start."""
    server_path = os.path.join(os.path.dirname(__file__), "server.py")
    proc = subprocess.Popen(
        [sys.executable, server_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        time.sleep(0.5)
        try:
            requests.get(f"{API_BASE}/api/status", timeout=1)
            log.info("Flask server is up.")
            return proc
        except Exception:
            pass
    log.warning("Flask server did not respond in 10 s — continuing anyway.")
    return proc


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def _pil_to_tk(root: tk.Tk, img: Image.Image) -> "tk.PhotoImage":
    from PIL import ImageTk
    return ImageTk.PhotoImage(img, master=root)


def _get_hwnd(widget: tk.Tk) -> "int | None":
    """Return the Win32 HWND of a tkinter window (Windows + pywin32 only)."""
    if not IS_WINDOWS or not HAS_WIN32:
        return None
    try:
        return win32gui.FindWindow(None, widget.title())
    except Exception:
        return None


def main():
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Majority Radio — Windows taskbar integration")
    parser.add_argument(
        "--no-server", action="store_true",
        help="Skip starting the Flask server (use when it is already running)")
    args = parser.parse_args()

    flask_proc = None
    if not args.no_server:
        flask_proc = _start_flask_server()

    api = RadioClient()

    # ── Tkinter root (hidden; drives event loop + HWND for thumbnail toolbar) ─
    root = tk.Tk()
    root.withdraw()
    root.title("Majority Radio")
    root.iconphoto(True, _pil_to_tk(root, _make_tray_icon(48)))

    # On Windows: keep the window minimised so it appears in the taskbar
    # (required for WM_TASKBARBUTTONCREATED to be sent to its HWND)
    if IS_WINDOWS:
        root.wm_attributes("-alpha", 1.0)
        root.deiconify()
        root.iconify()

    popup = PopupWindow(root, api)

    # ── Register thumbnail toolbar after window is mapped ─────────────────────
    if IS_WINDOWS and HAS_WIN32:
        def _setup_toolbar():
            root.update()
            hwnd = _get_hwnd(root)
            if hwnd:
                ThumbnailToolbar(hwnd, api).setup()

        root.after(1000, _setup_toolbar)

    tray = TrayApp(api, popup)
    try:
        tray.run()
    finally:
        if flask_proc:
            flask_proc.terminate()


if __name__ == "__main__":
    main()

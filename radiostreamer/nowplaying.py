"""Detecting 'now playing' text for live sources: music app window titles or a Last.fm user."""

import re
import subprocess
import sys

from . import tools

BROWSERS = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "opera_gx.exe",
            "vivaldi.exe", "arc.exe"}
_IGNORED_SPOTIFY = {"spotify", "spotify premium", "spotify free", "advertisement", "spotify - web player"}


def _spotify(title):
    t = title.strip()
    return None if not t or t.lower() in _IGNORED_SPOTIFY or " - " not in t else t


def _spotify_web(title):
    """Spotify web player tab: 'Song • Artist - Google Chrome'."""
    t = re.sub(r" (?:-|—) (?:Google Chrome|Microsoft.? Edge|Mozilla Firefox|Brave|Opera|Vivaldi).*$", "", title)
    if "•" not in t:
        return None
    song, artist = (s.strip() for s in t.split("•", 1))
    return f"{artist} - {song}" if song and artist else None


def _rx(pattern):
    rx = re.compile(pattern)

    def parse(title):
        m = rx.search(title)
        return m.group(1).strip() if m else None
    return parse


# (label, process names, parser) in priority order for auto-detect
PLAYERS = [
    ("Spotify app", {"spotify.exe"}, _spotify),
    ("YouTube Music", BROWSERS, _rx(r"^(?:\(\d+\)\s*)?(.+?) - YouTube Music")),
    ("YouTube", BROWSERS, _rx(r"^(?:\(\d+\)\s*)?(.+?) - YouTube(?! Music)")),
    ("SoundCloud", BROWSERS, _rx(r"^(?:▶\s*)?(.+?) \| Listen online for free on SoundCloud")),
    ("Spotify Web", BROWSERS, lambda t: _spotify_web(t)),
    ("VLC", {"vlc.exe"}, _rx(r"^(.+?) - VLC media player$")),
    ("foobar2000", {"foobar2000.exe"}, _rx(r"^(.+?)\s+\[foobar2000\]")),
    ("Winamp", {"winamp.exe"}, _rx(r"^\d+\.\s+(.+?) - Winamp")),
    ("MusicBee", {"musicbee.exe"}, _rx(r"^(.+?) - MusicBee$")),
    ("AIMP", {"aimp.exe"}, lambda t: t if " - " in t else None),
    ("Tidal", {"tidal.exe"}, lambda t: t if " - " in t else None),
    ("Deezer", {"deezer.exe"}, lambda t: t if " - " in t else None),
    ("Apple Music", {"applemusic.exe"}, lambda t: t if " - " in t else None),
]


def _windows_titles():
    """[(process_name_lower, window_title)] for visible top-level windows (Windows only)."""
    import ctypes
    from ctypes import wintypes
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    out = []
    proc_cache = {}

    def proc_name(pid):
        if pid in proc_cache:
            return proc_cache[pid]
        name = ""
        h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                name = buf.value.rsplit("\\", 1)[-1].lower()
            kernel32.CloseHandle(h)
        proc_cache[pid] = name
        return name

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                out.append((proc_name(pid.value), buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return out


def _mac_spotify():
    script = ('if application "Spotify" is running then tell application "Spotify" to if player state is playing '
              'then return (artist of current track) & " - " & (name of current track)')
    try:
        res = tools.run(["osascript", "-e", script], timeout=5)
        return res.stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def detect(mode):
    """Current title for a TITLE_SOURCES mode ('Music app (auto-detect)', 'Spotify app', 'Browser ...')."""
    if sys.platform == "darwin":
        return _mac_spotify() if mode in ("Music app (auto-detect)", "Spotify app") else None
    if sys.platform != "win32":
        return None
    if mode == "Spotify app":
        players = [p for p in PLAYERS if p[0] == "Spotify app"]
    elif mode.startswith("Browser"):
        players = [p for p in PLAYERS if p[1] is BROWSERS]
    else:
        players = PLAYERS
    windows = _windows_titles()
    for _, procs, parse in players:
        for proc, title in windows:
            if proc in procs:
                found = parse(title)
                if found:
                    return found
    return None

"""Settings, per-user paths, server provider presets and Mixxx import."""

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from . import APP_ID

if sys.platform == "win32":
    DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_ID
    CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_ID / "cache"
    MIXXX_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Mixxx"
elif sys.platform == "darwin":
    DATA_DIR = Path.home() / "Library" / "Application Support" / APP_ID
    CACHE_DIR = Path.home() / "Library" / "Caches" / APP_ID
    MIXXX_DIR = Path.home() / "Library" / "Containers" / "org.mixxx.mixxx" / "Data" / "Library" / \
        "Application Support" / "Mixxx"
else:
    DATA_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / APP_ID
    CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / APP_ID
    MIXXX_DIR = Path.home() / ".mixxx"

SETTINGS_FILE = DATA_DIR / "settings.json"
BIN_DIR = DATA_DIR / "bin"          # user-updatable tools (yt-dlp)

SERVER_TYPES = ["Shoutcast v1", "Shoutcast v2", "Icecast 2"]
BITRATES = [64, 96, 128, 160, 192, 256, 320]
SAMPLERATES = [44100, 48000]

SOURCES = {"queue": "Playlist / queue", "loopback": "System audio (what this PC plays)",
           "device": "Audio input device"}
TITLE_SOURCES = ["Manual", "Music app (auto-detect)", "Spotify app", "Browser (YouTube / SoundCloud)",
                 "Last.fm user's now playing"]

DEFAULTS = {
    # server
    "provider": "Listen2MyRadio",
    "server_type": "Shoutcast v1",
    "host": "",
    "port": 8000,
    "password": "",
    "mount": "/stream",
    "username": "source",
    "sid": 1,
    # station
    "name": "My Radio",
    "genre": "Various",
    "url": "",
    "description": "",
    "public": False,
    # encoder
    "bitrate": 128,
    "samplerate": 44100,
    "channels": 2,
    "normalize": True,
    # source
    "source": "queue",
    "device": "",
    "loopback_device": "",
    "queue": [],
    "loop": True,
    # titles
    "title_source": "Music app (auto-detect)",
    "auto_metadata": True,
    # online media
    "ytdlp_cookies_browser": "(none)",
    "match_service": "YouTube",
    # last.fm
    "lastfm_api_key": "",
    "lastfm_api_secret": "",
    "lastfm_session": "",
    "lastfm_user": "",
    "lastfm_scrobble": False,
    "lastfm_watch_user": "",
    # connection
    "reconnect_delay": 5,
    "max_retries": 0,
    "wizard_done": False,
}

# Hints shown by the wizard / server tab. Field defaults are applied when picked.
PROVIDERS = {
    "Listen2MyRadio": {
        "fields": {"server_type": "Shoutcast v1"},
        "hint": "Control panel: copy Hostname (or IP Address), Port and Stream Password. "
                "Press 'Turn ON' in the panel first - the server refuses connections while OFF.",
    },
    "Zeno.FM": {
        "fields": {"server_type": "Icecast 2", "username": "source"},
        "hint": "Zeno dashboard > your station > Broadcast settings: Server, Port, Mount point "
                "and Password. Username is 'source'.",
    },
    "FreeSHOUTcast / FastCast4u": {
        "fields": {"server_type": "Shoutcast v2", "sid": 1},
        "hint": "Control panel > Quick links / Encoder settings: server, port, password, Stream ID 1. "
                "The free plan is limited to 96 kbps - set the bitrate to 96.",
    },
    "Caster.fm": {
        "fields": {"server_type": "Icecast 2", "username": "source"},
        "hint": "Dashboard > Broadcast settings. Note: the free plan does not give a direct "
                "stream URL, so a 3DXChat radio prop may not be able to play it.",
    },
    "Other Shoutcast v1": {"fields": {"server_type": "Shoutcast v1"},
                           "hint": "Source connects to port + 1 with the source password."},
    "Other Shoutcast v2 (DNAS 2)": {"fields": {"server_type": "Shoutcast v2"},
                                    "hint": "Uses the legacy source login (port + 1) with your Stream ID."},
    "Other Icecast 2 / AzuraCast": {"fields": {"server_type": "Icecast 2"},
                                    "hint": "Username is usually 'source'. Mount must start with '/'."},
}


def load_settings():
    cfg = dict(DEFAULTS)
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in saved.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return cfg


def save_settings(cfg):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_FILE)


MIXXX_DEFAULT_VALUES = {"Mixxx", "https://www.mixxx.org", "Live Mix",
                        "This stream is online for testing purposes!"}


def mixxx_profile_exists():
    return any((MIXXX_DIR / "broadcast_profiles").glob("*.bcp.xml"))


def import_mixxx_profile():
    """Read server settings from Mixxx's broadcast profile. Returns (dict | None, message)."""
    chosen = None
    for p in sorted((MIXXX_DIR / "broadcast_profiles").glob("*.bcp.xml")):
        try:
            root = ET.parse(p).getroot()
        except (OSError, ET.ParseError):
            continue
        enabled = (root.findtext("Enabled") or "").strip() == "1"
        if chosen is None or enabled:
            chosen = root
        if enabled:
            break
    if chosen is None:
        return None, "No Mixxx broadcast profile found."
    root = chosen

    def g(tag):
        return (root.findtext(tag) or "").strip()

    is_icecast = "icecast" in g("Servertype").lower()
    out = {
        "provider": "Other Icecast 2 / AzuraCast" if is_icecast else "Other Shoutcast v1",
        "server_type": "Icecast 2" if is_icecast else "Shoutcast v1",
        "host": g("Host"),
        "port": int(g("Port")) if g("Port").isdigit() else 8000,
        "password": g("Password"),
    }
    if "listen2myradio" in out["host"].lower():
        out["provider"] = "Listen2MyRadio"
    if is_icecast:
        out["username"] = g("Login") or "source"
        out["mount"] = g("Mountpoint") or "/stream"
    for tag, key in (("StreamName", "name"), ("StreamGenre", "genre"),
                     ("StreamWebsite", "url"), ("StreamDesc", "description")):
        val = g(tag)
        if val and val not in MIXXX_DEFAULT_VALUES:
            out[key] = val
    out["public"] = g("StreamPublic") == "1"
    if g("Bitrate").isdigit():
        out["bitrate"] = int(g("Bitrate"))
    if g("Channels") in ("1", "2"):
        out["channels"] = int(g("Channels"))

    try:
        sroot = ET.parse(MIXXX_DIR / "soundconfig.xml").getroot()
        for dev in sroot.iter("SoundDevice"):
            if dev.find("input") is not None:
                out["device"] = dev.get("name", "")
                break
    except (OSError, ET.ParseError):
        pass

    msg = f"Imported Mixxx profile '{g('ProfileName')}' ({out['host']}:{out['port']})"
    if g("SecureCredentialsStorage") == "1" or not out["password"]:
        out.pop("password", None)
        msg += " - the password is in Mixxx's secure storage, enter it manually"
    return out, msg

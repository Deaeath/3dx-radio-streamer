"""Locating / fetching ffmpeg and yt-dlp, and listing audio devices per platform."""

import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from .config import BIN_DIR

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
EXE = ".exe" if sys.platform == "win32" else ""
YTDLP_DOWNLOAD = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
FFMPEG_HELP_URL = "https://ffmpeg.org/download.html"


def bundle_dirs():
    """Directories that may hold bundled tools: PyInstaller bundle, next to the exe, source tree."""
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "bin")
        dirs.append(Path(sys.executable).parent / "bin")
    dirs.append(Path(__file__).resolve().parent.parent / "bin")
    return dirs


def find_tool(name, prefer_user=False):
    candidates = [d / (name + EXE) for d in bundle_dirs()]
    user = BIN_DIR / (name + EXE)
    candidates = [user] + candidates if prefer_user else candidates + [user]
    for c in candidates:
        if c.is_file():
            return str(c)
    return shutil.which(name)


def ffmpeg():
    return find_tool("ffmpeg")


def ytdlp():
    """yt-dlp breaks whenever YouTube changes, so prefer the user-updatable copy in BIN_DIR."""
    return find_tool("yt-dlp", prefer_user=True)


def run(cmd, timeout=30, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=CREATE_NO_WINDOW, **kw)


def popen(cmd, **kw):
    return subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW, **kw)


def ensure_user_ytdlp(log=print):
    """Make sure an updatable yt-dlp exists in BIN_DIR (copy the bundled one or download it)."""
    target = BIN_DIR / ("yt-dlp" + EXE)
    if target.is_file():
        return str(target)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    for d in bundle_dirs():
        src = d / ("yt-dlp" + EXE)
        if src.is_file():
            shutil.copy2(src, target)
            return str(target)
    if sys.platform == "win32":
        log("Downloading yt-dlp...")
        tmp = target.with_suffix(".part")
        urllib.request.urlretrieve(YTDLP_DOWNLOAD, tmp)
        os.replace(tmp, target)
        return str(target)
    return shutil.which("yt-dlp")


def update_ytdlp(log=print):
    exe = ensure_user_ytdlp(log)
    if not exe:
        return "yt-dlp not found - install it with: pip install -U yt-dlp"
    if not str(exe).startswith(str(BIN_DIR)):
        return f"yt-dlp at {exe} is managed by your system; update it with: pip install -U yt-dlp"
    res = run([exe, "-U"], timeout=180)
    return (res.stdout + res.stderr).strip().splitlines()[-1] if (res.stdout + res.stderr).strip() else "done"


def tool_version(exe):
    if not exe:
        return "not found"
    try:
        res = run([exe, "-version" if "ffmpeg" in Path(exe).name else "--version"], timeout=15)
        line = (res.stdout or res.stderr).strip().splitlines()[0]
        return line.replace("ffmpeg version ", "")[:60]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return "unknown"


# --------------------------------------------------------------------------- #
# Audio input devices (ffmpeg)
# --------------------------------------------------------------------------- #

def list_input_devices(ffmpeg_exe):
    if not ffmpeg_exe:
        return []
    try:
        if sys.platform == "win32":
            res = run([ffmpeg_exe, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"], 15)
            return re.findall(r'"([^"]+)"\s+\(audio\)', res.stderr)
        if sys.platform == "darwin":
            res = run([ffmpeg_exe, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""], 15)
            text = res.stderr.split("audio devices:", 1)[-1]
            return re.findall(r"\]\s*\[\d+\]\s*(.+)", text)
        res = run(["pactl", "list", "short", "sources"], 10)
        return [line.split("\t")[1] for line in res.stdout.splitlines() if "\t" in line]
    except (OSError, subprocess.TimeoutExpired):
        return []


def device_input_args(name):
    if sys.platform == "win32":
        return ["-f", "dshow", "-audio_buffer_size", "50", "-i", f"audio={name}"]
    if sys.platform == "darwin":
        return ["-f", "avfoundation", "-i", f":{name}"]
    return ["-f", "pulse", "-i", name or "default"]


def vb_cable_installed(devices):
    return any("CABLE Output" in d for d in devices)

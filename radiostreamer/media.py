"""Turning user input (files, folders, playlists, links, YouTube, Spotify, search text) into
queue items, and preparing a queue item for playback.

Queue item: {"kind": "file" | "stream" | "ytdl" | "ytlive", "src": str, "title": str}
  file   - local media file, decoded by ffmpeg
  stream - direct http(s) audio / internet radio / HLS, decoded by ffmpeg
  ytdl   - anything yt-dlp supports (YouTube, SoundCloud, Bandcamp, Mixcloud, "ytsearch1:...")
           downloaded to the cache shortly before it plays
  ytlive - a live video/stream resolved by yt-dlp at play time
"""

import html
import json
import os
import re
import subprocess
import uuid
import urllib.error
import urllib.parse
import urllib.request
import http.client
from pathlib import Path

from . import tools

MEDIA_EXTS = {
    ".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wma", ".aiff", ".aif",
    ".alac", ".ape", ".wv", ".mpc", ".ac3", ".dts", ".amr", ".mka", ".tta", ".caf", ".dsf", ".w64",
    ".au", ".mp2", ".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".flv", ".wmv", ".3gp", ".ts",
}
PLAYLIST_EXTS = {".m3u", ".m3u8", ".pls", ".xspf"}
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36")
SPOTIFY_RE = re.compile(r"open\.spotify\.com/(?:intl-[a-z-]+/)?(?:embed/)?(track|album|playlist|episode|show)/"
                        r"([A-Za-z0-9]+)")


class MediaError(Exception):
    pass


# Set from settings by configure(): extra yt-dlp args and the search service for song names
_ytdl_extra = []
_search_prefix = "ytsearch1:"
COOKIE_BROWSERS = ["(none)", "firefox", "chrome", "edge", "brave", "opera", "vivaldi", "chromium"]
MATCH_SERVICES = {"YouTube": "ytsearch1:", "SoundCloud": "scsearch1:"}


def configure(cfg):
    global _ytdl_extra, _search_prefix
    browser = cfg.get("ytdlp_cookies_browser", "")
    _ytdl_extra = ["--cookies-from-browser", browser] if browser and browser != "(none)" else []
    _search_prefix = MATCH_SERVICES.get(cfg.get("match_service"), "ytsearch1:")


def search_src(query):
    return _search_prefix + query


def _ytdl_error(stderr, default):
    msg = (stderr.strip().splitlines() or [default])[-1].replace("ERROR: ", "")
    if "not a bot" in msg or "Sign in to confirm" in msg:
        return ("YouTube blocked this connection ('confirm you're not a bot' - common on VPNs). "
                "Turn the VPN off, or set 'YouTube sign-in' to your browser on the Integrations tab, "
                "or match songs on SoundCloud instead.")
    if "cookies" in msg.lower() and ("could not" in msg.lower() or "failed" in msg.lower()):
        return f"Could not read browser cookies ({msg[:120]}). Close that browser and try again, or use Firefox."
    return msg[:200]


def item(kind, src, title):
    return {"kind": kind, "src": src, "title": title or src}


def _natural_key(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(p))]


def is_url(text):
    return bool(re.match(r"^(https?|rtmp|rtsp|mms)://", text, re.I))


# --------------------------------------------------------------------------- #
# Expanding input
# --------------------------------------------------------------------------- #

def expand(inputs, log=print, depth=0):
    """Expand a list of strings (paths, URLs, search text) into queue items."""
    out = []
    for raw in inputs:
        text = str(raw).strip().strip('"')
        if not text or text.startswith("#"):
            continue
        try:
            out.extend(_expand_one(text, log, depth))
        except MediaError as e:
            log(f"Skipped {text[:80]}: {e}")
    return out


def _expand_one(text, log, depth):
    path = Path(os.path.expandvars(os.path.expanduser(text)))
    if not is_url(text) and path.is_dir():
        files = sorted((p for p in path.rglob("*") if p.suffix.lower() in MEDIA_EXTS), key=_natural_key)
        if not files:
            raise MediaError("no media files in folder")
        log(f"Added {len(files)} files from {path.name}")
        return [item("file", str(p), p.stem) for p in files]
    if not is_url(text) and path.is_file():
        if path.suffix.lower() in PLAYLIST_EXTS:
            if depth > 3:
                raise MediaError("playlist nesting too deep")
            entries = parse_playlist(path.read_text(encoding="utf-8", errors="replace"), base=path.parent)
            return expand(entries, log, depth + 1)
        return [item("file", str(path), path.stem)]
    if is_url(text):
        m = SPOTIFY_RE.search(text)
        if m:
            return spotify_items(m.group(1), m.group(2), log)
        kind, info = sniff_url(text)
        if kind == "audio":
            return [item("stream", text, info or _url_name(text))]
        if kind == "playlist":
            if depth > 3:
                raise MediaError("playlist nesting too deep")
            return expand(parse_playlist(info), log, depth + 1)
        return ytdl_items(text, log)
    if text.lower().startswith(("ytsearch", "scsearch", "ytmsearch")):
        return [item("ytdl", text, text.split(":", 1)[-1])]
    if len(text) < 200 and not re.search(r"[\\/:*?<>|]", text.replace(" - ", "")):
        # plain text -> search YouTube for it ("Artist - Title")
        return [item("ytdl", search_src(text), text)]
    raise MediaError("file not found")


def _url_name(url):
    name = Path(urllib.parse.urlparse(url).path).stem
    return urllib.parse.unquote(name) or urllib.parse.urlparse(url).netloc


def parse_playlist(text, base=None):
    """M3U / PLS / XSPF -> list of entries (paths resolved against base)."""
    entries = []
    if "<playlist" in text[:500] and "xspf" in text[:500].lower():
        entries = [html.unescape(x) for x in re.findall(r"<location>(.*?)</location>", text, re.S)]
        entries = [urllib.parse.unquote(e[7:]) if e.startswith("file://") else e for e in entries]
    elif re.search(r"^\[playlist\]", text, re.I | re.M):
        entries = re.findall(r"^File\d+\s*=\s*(.+)$", text, re.I | re.M)
    else:
        entries = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    out = []
    for e in entries:
        e = e.strip()
        if base is not None and not is_url(e) and not os.path.isabs(e):
            e = str((base / e).resolve())
        out.append(e)
    return out


def sniff_url(url):
    """Classify a URL: ("audio", name) | ("playlist", text) | ("page", None)."""
    if re.search(r"(youtube\.com|youtu\.be|soundcloud\.com|bandcamp\.com|mixcloud\.com|vimeo\.com|"
                 r"twitch\.tv|tiktok\.com|dailymotion\.com|audiomack\.com)", url, re.I):
        return "page", None
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Icy-MetaData": "1"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            name = resp.headers.get("icy-name") or ""
            if ctype in ("audio/x-mpegurl", "audio/mpegurl", "audio/x-scpls", "application/pls+xml",
                         "application/xspf+xml") or (ctype in ("application/vnd.apple.mpegurl",
                                                               "application/x-mpegurl")):
                body = resp.read(256 * 1024).decode("utf-8", errors="replace")
                if "#EXT-X-" in body:          # HLS - ffmpeg plays it directly
                    return "audio", name or _url_name(url)
                return "playlist", body
            if ctype.startswith(("audio/", "video/")) or ctype in ("application/ogg", "application/octet-stream") \
                    or resp.headers.get("icy-br"):
                return "audio", name
            return "page", None
    except http.client.BadStatusLine as e:   # Shoutcast v1 answers "ICY 200 OK"
        if "ICY" in str(e):
            return "audio", None
        raise MediaError(f"bad response: {e}")
    except urllib.error.HTTPError as e:
        if Path(urllib.parse.urlparse(url).path).suffix.lower() in MEDIA_EXTS:
            raise MediaError(f"HTTP {e.code}")
        return "page", None
    except (OSError, ValueError) as e:
        if Path(urllib.parse.urlparse(url).path).suffix.lower() in MEDIA_EXTS:
            return "audio", None
        return "page", None


def ytdl_items(url, log):
    exe = tools.ytdlp()
    if not exe:
        raise MediaError("yt-dlp is not available (Tools > Update yt-dlp)")
    try:
        res = tools.run([exe, "--flat-playlist", "-J", "--no-warnings"] + _ytdl_extra + [url], timeout=120)
    except subprocess.TimeoutExpired:
        raise MediaError("timed out reading the link")
    if res.returncode != 0 or not res.stdout.strip():
        raise MediaError(_ytdl_error(res.stderr, "unsupported link"))
    data = json.loads(res.stdout)
    if data.get("_type") == "playlist":
        items = []
        for e in data.get("entries") or []:
            if not e:
                continue
            src = e.get("url") or e.get("webpage_url")
            if src and not is_url(src) and e.get("ie_key") == "Youtube":
                src = f"https://www.youtube.com/watch?v={src}"
            if not src:
                continue
            kind = "ytlive" if e.get("live_status") == "is_live" else "ytdl"
            items.append(item(kind, src, _ytdl_title(e)))
        if not items:
            raise MediaError("playlist is empty or private")
        log(f"Added {len(items)} tracks from '{data.get('title') or url}'")
        return items
    kind = "ytlive" if data.get("is_live") or data.get("live_status") == "is_live" else "ytdl"
    return [item(kind, data.get("webpage_url") or url, _ytdl_title(data))]


def _ytdl_title(info):
    artist = info.get("artist") or info.get("creator")
    track = info.get("track")
    if artist and track:
        return f"{artist} - {track}"
    return info.get("title") or info.get("url") or "Unknown"


def spotify_items(kind, sid, log):
    if kind in ("episode", "show"):
        raise MediaError("Spotify podcasts are not supported")
    req = urllib.request.Request(f"https://open.spotify.com/embed/{kind}/{sid}",
                                 headers={"User-Agent": BROWSER_UA, "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            page = resp.read().decode("utf-8", errors="replace")
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page, re.S)
        entity = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        raise MediaError(f"could not read Spotify {kind} ({e.__class__.__name__}) - is it public?")
    tracks = []
    if kind == "track":
        artists = ", ".join(a.get("name", "") for a in entity.get("artists", []))
        tracks.append((artists, entity.get("name") or entity.get("title", "")))
    else:
        for t in entity.get("trackList") or []:
            tracks.append((t.get("subtitle", ""), t.get("title", "")))
    tracks = [(a.replace(" ", " ").strip(), t.strip()) for a, t in tracks if t]
    if not tracks:
        raise MediaError(f"no tracks found in Spotify {kind}")
    if kind != "track":
        log(f"Added {len(tracks)} tracks from Spotify {kind} '{entity.get('name') or entity.get('title', '')}' "
            f"(Spotify audio is DRM-protected, so each track is matched on YouTube)")
    return [item("ytdl", search_src(f"{a} - {t}" if a else t), f"{a} - {t}" if a else t) for a, t in tracks]


# --------------------------------------------------------------------------- #
# Preparing an item for playback
# --------------------------------------------------------------------------- #

def probe_title(path):
    """'Artist - Title' from tags (read with ffmpeg's ffmetadata output), falling back to the file name."""
    exe = tools.ffmpeg()
    if exe:
        try:
            res = tools.run([exe, "-v", "quiet", "-i", str(path), "-f", "ffmetadata", "-"], 10)
            tags = {}
            for line in res.stdout.splitlines():
                if "=" in line and not line.startswith(";"):
                    k, val = line.split("=", 1)
                    tags.setdefault(k.strip().lower(), val.strip())
            artist, title = tags.get("artist", ""), tags.get("title", "")
            if artist and title:
                return f"{artist} - {title}"
            if title:
                return title
        except (OSError, subprocess.TimeoutExpired):
            pass
    return Path(path).stem


def stream_input_args(url):
    args = []
    if url.lower().startswith(("http://", "https://")):
        args += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10",
                 "-user_agent", BROWSER_UA]
    return args + ["-i", url]


def prepare(it, cache_dir, cancel=None):
    """Return (input_args, title, temp_file_or_None, is_live). Raises MediaError."""
    kind, src, title = it["kind"], it["src"], it.get("title") or it["src"]
    if kind == "file":
        if not os.path.isfile(src):
            raise MediaError("file not found")
        if title == Path(src).stem:
            title = probe_title(src)
        return ["-i", src], title, None, False
    if kind == "stream":
        return stream_input_args(src), title, None, True

    exe = tools.ytdlp()
    if not exe:
        raise MediaError("yt-dlp is not available")
    ffm = tools.ffmpeg()
    if kind == "ytlive":
        res = tools.run([exe, "-g", "-f", "bestaudio/best", "--no-warnings"] + _ytdl_extra + [src], timeout=60)
        url = res.stdout.strip().splitlines()[0] if res.returncode == 0 and res.stdout.strip() else ""
        if not url:
            raise MediaError(_ytdl_error(res.stderr, "could not open live stream"))
        return stream_input_args(url), title, None, True

    cache_dir.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-f", "bestaudio/best", "--no-playlist", "--no-part", "--no-progress", "--no-warnings",
           "--quiet", "--no-simulate", "--max-filesize", "400M",
           "--print", "after_move:filepath", "--print", "after_move:title",
           "-o", str(cache_dir / f"{uuid.uuid4().hex[:8]}-%(id)s.%(ext)s")]
    if ffm:
        cmd += ["--ffmpeg-location", str(Path(ffm).parent)]
    m = re.match(r"^(ytsearch|ytmsearch|scsearch)\d*:(.*)$", src, re.S)
    if m:   # try a few matches: the top hit can be DRM-locked, region-blocked or an hour-long mix
        cmd += ["--match-filter", "!is_live & duration < 1200", "--max-downloads", "1", "--ignore-errors"]
        src = f"{m.group(1)}5:{m.group(2)}"
    else:
        cmd += ["--match-filter", "!is_live"]
    proc = tools.popen(cmd + _ytdl_extra + [src], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       stdin=subprocess.DEVNULL)
    while True:
        try:
            out, err = proc.communicate(timeout=0.5)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                proc.kill()
                proc.communicate()
                raise MediaError("cancelled")
    lines = out.decode("utf-8", errors="replace").strip().splitlines()
    if proc.returncode not in (0, 101) or not lines or not os.path.isfile(lines[0]):
        raise MediaError(_ytdl_error(err.decode("utf-8", errors="replace"), "download failed"))
    if title == it["src"] and len(lines) > 1:
        title = lines[1]
    return ["-i", lines[0]], title, lines[0], False

"""Minimal Last.fm API client: desktop auth, now playing, scrobbling, reading a user's now playing.

API docs: https://www.last.fm/api  -  get a key at https://www.last.fm/api/account/create
"""

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .protocol import HTTP_UA

API_URL = "https://ws.audioscrobbler.com/2.0/"
CREATE_KEY_URL = "https://www.last.fm/api/account/create"

try:  # build-time defaults (written by build.ps1 when LASTFM_API_KEY is set)
    from ._keys import LASTFM_API_KEY as DEFAULT_KEY, LASTFM_API_SECRET as DEFAULT_SECRET
except ImportError:
    DEFAULT_KEY = DEFAULT_SECRET = ""


class LastFMError(Exception):
    pass


def split_title(title):
    """'Artist - Track' -> (artist, track) or None."""
    if " - " not in title:
        return None
    artist, track = (s.strip() for s in title.split(" - ", 1))
    return (artist, track) if artist and track else None


class LastFM:
    def __init__(self, api_key, api_secret="", session_key=""):
        self.key = (api_key or DEFAULT_KEY).strip()
        self.secret = (api_secret or (DEFAULT_SECRET if not api_key else "")).strip()
        self.session = session_key.strip()

    @property
    def configured(self):
        return bool(self.key)

    def _sign(self, params):
        raw = "".join(k + str(params[k]) for k in sorted(params) if k not in ("format", "callback"))
        return hashlib.md5((raw + self.secret).encode("utf-8")).hexdigest()

    def call(self, method, signed=False, post=False, **params):
        if not self.key:
            raise LastFMError("no Last.fm API key set")
        params = {k: str(v) for k, v in params.items() if v is not None}
        params.update(method=method, api_key=self.key)
        if signed:
            if not self.secret:
                raise LastFMError("this needs the API shared secret")
            params["api_sig"] = self._sign(params)
        params["format"] = "json"
        data = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(API_URL if post else API_URL + "?" + data.decode("ascii"),
                                     data=data if post else None, headers={"User-Agent": HTTP_UA})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except ValueError:
                raise LastFMError(f"HTTP {e.code}") from e
        except (OSError, ValueError) as e:
            raise LastFMError(str(e)) from e
        if "error" in body:
            raise LastFMError(body.get("message") or f"error {body['error']}")
        return body

    # -- desktop auth ------------------------------------------------------ #
    def get_token(self):
        return self.call("auth.getToken", signed=True)["token"]

    def auth_url(self, token):
        return f"https://www.last.fm/api/auth/?api_key={self.key}&token={token}"

    def get_session(self, token):
        s = self.call("auth.getSession", signed=True, token=token)["session"]
        self.session = s["key"]
        return s["key"], s["name"]

    # -- scrobbling -------------------------------------------------------- #
    def now_playing(self, artist, track):
        self.call("track.updateNowPlaying", signed=True, post=True, artist=artist, track=track, sk=self.session)

    def scrobble(self, artist, track, started):
        self.call("track.scrobble", signed=True, post=True, artist=artist, track=track,
                  timestamp=int(started), sk=self.session)

    # -- reading ----------------------------------------------------------- #
    def user_now_playing(self, user):
        tracks = self.call("user.getRecentTracks", user=user, limit=1)["recenttracks"].get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        for t in tracks:
            if t.get("@attr", {}).get("nowplaying") == "true":
                return f"{t['artist'].get('#text', '')} - {t.get('name', '')}"
        return None


class Scrobbler:
    """Feed it every title change; scrobbles the previous track when it played long enough."""

    MIN_PLAY = 30

    def __init__(self, client, log):
        self.client = client
        self.log = log
        self.current = None
        self.started = 0.0

    def title_changed(self, title):
        now = time.time()
        prev, started = self.current, self.started
        self.current, self.started = title, now
        if prev and now - started >= self.MIN_PLAY:
            parts = split_title(prev)
            if parts:
                try:
                    self.client.scrobble(*parts, started)
                except LastFMError as e:
                    self.log(f"Last.fm scrobble failed: {e}")
        parts = split_title(title) if title else None
        if parts:
            try:
                self.client.now_playing(*parts)
            except LastFMError as e:
                self.log(f"Last.fm now playing failed: {e}")

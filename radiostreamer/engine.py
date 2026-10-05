"""Broadcast engine.

    sources (ffmpeg decoders / device / loopback) --raw PCM--> mixer (real-time clock)
        --> one long-running ffmpeg MP3 encoder --> server socket

The encoder never restarts between tracks, so the stream is gapless and listeners never see
a format change. When a source has nothing to give (loading, network hiccup, end of queue)
the mixer sends silence so the server keeps the stream up.
"""

import collections
import os
import queue
import random
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

from . import capture, media, nowplaying, tools
from .config import CACHE_DIR
from .protocol import StreamError, open_source_connection

CHUNK_SEC = 0.05
PREBUFFER = 4          # chunks a source must hold before it starts playing (200 ms)
MAX_BACKLOG = 30       # live sources: drop audio beyond 1.5 s of backlog (clock drift)
EOF = object()
LEVEL_RE = re.compile(r"\bM:\s*(-?[\d.]+|-?inf|nan)")


# --------------------------------------------------------------------------- #
# Shared playlist (edited by the GUI while the engine plays it)
# --------------------------------------------------------------------------- #

class Playlist:
    def __init__(self, items=None, loop=True):
        self.lock = threading.RLock()
        self.items = list(items or [])
        self.loop = loop
        self.cursor = None          # item currently playing
        self.cursor_pos = -1        # its index (kept when the item is removed)
        self.forced_next = None
        self.failed = set()
        self.version = 0

    def _touch(self):
        self.version += 1

    def _cursor_index(self):
        if self.cursor is not None:
            for i, x in enumerate(self.items):
                if x is self.cursor:
                    return i
        return self.cursor_pos

    def index_of(self, it):
        with self.lock:
            for i, x in enumerate(self.items):
                if x is it:
                    return i
            return -1

    def peek(self):
        with self.lock:
            if self.forced_next is not None and self.index_of(self.forced_next) >= 0:
                return self.forced_next
            n = len(self.items)
            start = self._cursor_index() + 1
            for k in range(n):
                i = start + k
                if i >= n:
                    if not self.loop:
                        return None
                    i %= n
                if id(self.items[i]) not in self.failed:
                    return self.items[i]
            return None

    def advance(self, it):
        with self.lock:
            self.cursor = it
            self.cursor_pos = self.index_of(it)
            self.forced_next = None
            self._touch()

    def mark_failed(self, it):
        with self.lock:
            self.failed.add(id(it))
            if self.forced_next is it:
                self.forced_next = None
            self._touch()

    def is_failed(self, it):
        return id(it) in self.failed

    def reset(self):
        with self.lock:
            self.failed.clear()
            self.cursor, self.cursor_pos, self.forced_next = None, -1, None
            self._touch()

    def add(self, items):
        with self.lock:
            self.items.extend(items)
            self._touch()

    def remove(self, indices):
        with self.lock:
            idx = sorted(set(i for i in indices if 0 <= i < len(self.items)), reverse=True)
            cur = self._cursor_index()
            for i in idx:
                if self.items[i] is self.cursor:
                    self.cursor = None
                if i <= cur:
                    cur -= 1
                del self.items[i]
            self.cursor_pos = cur
            self._touch()

    def move(self, i, delta):
        with self.lock:
            j = i + delta
            if 0 <= i < len(self.items) and 0 <= j < len(self.items):
                self.items[i], self.items[j] = self.items[j], self.items[i]
                if self.cursor is None and self.cursor_pos in (i, j):
                    self.cursor_pos = j if self.cursor_pos == i else i
                self._touch()
                return j
            return i

    def shuffle_upcoming(self):
        with self.lock:
            cur = self._cursor_index()
            upcoming = self.items[cur + 1:]
            random.shuffle(upcoming)
            self.items[cur + 1:] = upcoming
            self._touch()

    def clear(self):
        with self.lock:
            self.items.clear()
            self.cursor, self.cursor_pos, self.forced_next = None, -1, None
            self._touch()

    def set_next(self, i):
        with self.lock:
            if 0 <= i < len(self.items):
                self.failed.discard(id(self.items[i]))
                self.forced_next = self.items[i]
                self._touch()

    def snapshot(self):
        with self.lock:
            return list(self.items), self.cursor


# --------------------------------------------------------------------------- #
# PCM sources
# --------------------------------------------------------------------------- #

class PCMSource:
    """An ffmpeg process writing raw PCM to stdout, chunked into a bounded queue by a reader thread."""

    def __init__(self, cmd, chunk_bytes, live, title="", item=None, temp_file=None, feeder=None):
        self.cmd = cmd
        self.chunk_bytes = chunk_bytes
        self.live = live
        self.title = title
        self.item = item
        self.temp_file = temp_file
        self.feeder = feeder            # LoopbackCapture feeding stdin
        self.q = queue.Queue(maxsize=MAX_BACKLOG + 10)
        self.proc = None
        self.tail = collections.deque(maxlen=8)
        self.bytes = 0
        self.started = False
        self.closed = False

    def start(self):
        if self.started:
            return
        self.started = True
        self.proc = tools.popen(self.cmd, stdin=subprocess.PIPE if self.feeder else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()
        if self.feeder:
            stdin = self.proc.stdin

            def feed(data):
                stdin.write(data)
                stdin.flush()
            self.feeder.start(feed)

    def _read(self):
        out = self.proc.stdout
        while not self.closed:
            data = out.read(self.chunk_bytes)
            if not data:
                break
            self.bytes += len(data)
            if self.live and self.q.full():
                try:
                    self.q.get_nowait()
                except queue.Empty:
                    pass
            while not self.closed:
                try:
                    self.q.put(data, timeout=0.25)
                    break
                except queue.Full:
                    continue
        while not self.closed:
            try:
                self.q.put(EOF, timeout=0.25)
                break
            except queue.Full:
                continue

    def _read_err(self):
        for raw in self.proc.stderr:
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                self.tail.append(line)

    def ready(self):
        return self.q.qsize() >= PREBUFFER or (self.started and self.proc.poll() is not None)

    def get(self):
        try:
            return self.q.get_nowait()
        except queue.Empty:
            return None

    def trim_backlog(self, keep):
        while self.q.qsize() > keep:
            try:
                if self.q.get_nowait() is EOF:
                    self.q.put(EOF)
                    return
            except queue.Empty:
                return

    def error(self):
        if self.proc is None or self.proc.poll() in (None, 0):
            return None
        return self.tail[-1] if self.tail else f"exit code {self.proc.returncode}"

    def close(self):
        self.closed = True
        if self.feeder:
            self.feeder.stop()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except OSError:
                pass
        if self.proc:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if self.temp_file:
            for _ in range(5):
                try:
                    os.remove(self.temp_file)
                    break
                except FileNotFoundError:
                    break
                except OSError:
                    time.sleep(0.2)


# --------------------------------------------------------------------------- #
# Broadcaster
# --------------------------------------------------------------------------- #

class Broadcaster:
    def __init__(self, cfg, playlist, emit):
        self.cfg = dict(cfg)
        self.playlist = playlist
        self.emit = emit                          # emit(kind, payload)
        self.ffmpeg = tools.ffmpeg()
        self.sr = int(cfg["samplerate"])
        self.ch = int(cfg["channels"])
        self.chunk_bytes = int(self.sr * CHUNK_SEC) * self.ch * 2
        self.stop_event = threading.Event()
        self.skip_event = threading.Event()
        self.sock = None
        self.sock_lock = threading.Lock()
        self.encoder = None
        self.bytes_sent = 0
        self.connected_since = None
        self.ever_connected = threading.Event()
        self.next_src = None
        self.next_lock = threading.Lock()
        self.current_title = ""

    # -- lifecycle ---------------------------------------------------------- #
    def start(self):
        if not self.ffmpeg:
            raise StreamError("ffmpeg was not found.")
        media.configure(self.cfg)
        if self.cfg["source"] == "queue":
            self.playlist.reset()
            shutil.rmtree(CACHE_DIR, ignore_errors=True)
        self._start_encoder()
        for target in (self._connection_loop, self._mixer):
            threading.Thread(target=self._guard, args=(target,), daemon=True).start()
        if self.cfg["source"] == "queue":
            threading.Thread(target=self._guard, args=(self._prefetcher,), daemon=True).start()
        elif self.cfg["title_source"] != "Manual":
            threading.Thread(target=self._guard, args=(self._title_watcher,), daemon=True).start()

    def stop(self):
        self.stop_event.set()
        self._drop_socket(None)
        enc = self.encoder
        if enc and enc.poll() is None:
            try:
                enc.kill()
            except OSError:
                pass
        with self.next_lock:
            if self.next_src:
                self.next_src.close()
                self.next_src = None

    def skip(self):
        self.skip_event.set()

    @property
    def live(self):
        return self.sock is not None

    def _guard(self, fn):
        try:
            fn()
        except Exception as e:  # a background thread must never die silently
            if not self.stop_event.is_set():
                self.emit("fatal", f"Internal error in {fn.__name__}: {e!r}")

    # -- encoder ------------------------------------------------------------ #
    def _start_encoder(self):
        cmd = [self.ffmpeg, "-hide_banner", "-nostdin", "-nostats",
               "-probesize", "32", "-analyzeduration", "0", "-fflags", "nobuffer",
               "-f", "s16le", "-ar", str(self.sr), "-ac", str(self.ch), "-i", "pipe:0",
               "-af", "ebur128=framelog=info",
               "-c:a", "libmp3lame", "-b:a", f"{int(self.cfg['bitrate'])}k",
               "-write_xing", "0", "-id3v2_version", "0", "-flush_packets", "1", "-f", "mp3", "pipe:1"]
        self.encoder = tools.popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.encoder_tail = collections.deque(maxlen=8)
        threading.Thread(target=self._encoder_out, daemon=True).start()
        threading.Thread(target=self._encoder_err, daemon=True).start()

    def _encoder_out(self):
        out = self.encoder.stdout
        while True:
            data = out.read1(16384)
            if not data:
                break
            self._send(data)

    def _encoder_err(self):
        for raw in self.encoder.stderr:
            line = raw.decode("utf-8", errors="replace").rstrip()
            m = LEVEL_RE.search(line)
            if m:
                try:
                    self.emit("level", float(m.group(1)))
                except ValueError:
                    self.emit("level", -120.0)
            elif line and "Parsed_ebur128" not in line:
                self.encoder_tail.append(line)

    # -- connection --------------------------------------------------------- #
    def _connection_loop(self):
        attempts = 0
        delay = max(1, int(self.cfg["reconnect_delay"]))
        max_retries = int(self.cfg["max_retries"])
        target = f"{self.cfg['host']}:{self.cfg['port']}"
        while not self.stop_event.is_set():
            if self.sock is None:
                self.emit("status", ("connecting", f"Connecting to {target}..."))
                try:
                    sock = open_source_connection(self.cfg)
                except StreamError as e:
                    attempts += 1
                    self.emit("log", f"Connect failed (attempt {attempts}): {e}")
                    if max_retries and attempts >= max_retries:
                        self.emit("fatal", f"Gave up after {attempts} attempts.")
                        return
                    self.emit("status", ("error", f"Not connected - retrying in {delay}s"))
                    self.stop_event.wait(delay)
                    continue
                if self.stop_event.is_set():
                    sock.close()
                    return
                sock.settimeout(15)
                with self.sock_lock:
                    self.sock = sock
                attempts = 0
                self.connected_since = time.time()
                self.ever_connected.set()
                self.emit("log", f"Connected to {target} ({self.cfg['server_type']})")
                self.emit("status", ("live", f"LIVE on {target}"))
                self.emit("connected", None)
            self.stop_event.wait(0.5)

    def _drop_socket(self, reason):
        sock, self.sock = self.sock, None
        self.connected_since = None
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()
        if reason and not self.stop_event.is_set():
            self.emit("log", reason)
            self.emit("status", ("error", "Connection lost - reconnecting..."))

    def _send(self, data):
        with self.sock_lock:
            sock = self.sock
            if sock is None:
                return
            try:
                sock.sendall(data)
                self.bytes_sent += len(data)
            except OSError as e:
                since = self.connected_since
                hint = ""
                if since and time.time() - since < 10:
                    hint = (" - the server dropped the stream right after login. This usually means the "
                            "bitrate is above your plan's limit (free plans are often 96 kbps).")
                self._drop_socket(f"Connection lost: {e}{hint}")

    # -- sources ------------------------------------------------------------ #
    def _decoder_cmd(self, input_args, live):
        cmd = [self.ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-loglevel", "error"] + input_args + ["-vn"]
        if self.cfg.get("normalize") and not live:
            cmd += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
        return cmd + ["-f", "s16le", "-ar", str(self.sr), "-ac", str(self.ch), "pipe:1"]

    def _live_source(self):
        if self.cfg["source"] in ("loopback", "app"):
            if self.cfg["source"] == "app":
                cap = capture.AppCapture(self.cfg.get("app_name", ""))
            else:
                cap = capture.LoopbackCapture(self.cfg.get("loopback_device", ""))
            cmd = [self.ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-loglevel", "error",
                   "-probesize", "32", "-analyzeduration", "0", "-fflags", "nobuffer",
                   "-f", "s16le", "-ar", str(cap.rate), "-ac", str(cap.channels), "-i", "pipe:0",
                   "-f", "s16le", "-ar", str(self.sr), "-ac", str(self.ch), "pipe:1"]
            src = PCMSource(cmd, self.chunk_bytes, True, title=cap.name, feeder=cap)
        else:
            device = self.cfg["device"]
            if not device and sys.platform == "win32":
                raise StreamError("No input device selected.")
            src = PCMSource(self._decoder_cmd(tools.device_input_args(device), True),
                            self.chunk_bytes, True, title=device)
        src.start()
        return src

    def _prefetcher(self):
        """Keep the next queue item downloaded/decoding so track changes are instant."""
        while not self.stop_event.is_set():
            it = self.playlist.peek()
            with self.next_lock:
                current_next = self.next_src
            if it is None or (current_next is not None and current_next.item is it):
                self.stop_event.wait(0.3)
                continue
            if current_next is not None:
                with self.next_lock:
                    self.next_src = None
                current_next.close()
            if it["kind"] == "ytdl":
                self.emit("log", f"Loading: {it.get('title') or it['src']}")
            try:
                args, title, tmp, live = media.prepare(it, CACHE_DIR, cancel=self.stop_event)
            except media.MediaError as e:
                if self.stop_event.is_set():
                    return
                self.emit("log", f"Skipped '{it.get('title') or it['src']}': {e}")
                self.playlist.mark_failed(it)
                self.emit("queue", None)
                continue
            src = PCMSource(self._decoder_cmd(args, live), self.chunk_bytes, live, title, it, tmp)
            if not live:
                src.start()            # decode ahead; live streams connect when they're due
            if self.playlist.peek() is not it or self.stop_event.is_set():
                src.close()
                continue
            with self.next_lock:
                self.next_src = src

    def _take_next(self):
        """Return the next PCMSource to play, or None (silence) if nothing is ready."""
        if self.cfg["source"] != "queue":
            return self._live_source()
        it = self.playlist.peek()
        with self.next_lock:
            src = self.next_src
            if src is None or src.item is not it:
                return None
            self.next_src = None
        src.start()
        self.playlist.advance(it)
        self.current_title = src.title
        self.emit("track", src.title)
        self.emit("queue", None)
        return src

    def _finish(self, src):
        err = src.error() if src.bytes == 0 else None
        src.close()
        if err and src.item is not None:
            self.emit("log", f"Could not play '{src.title}': {err}")
            self.playlist.mark_failed(src.item)
            self.emit("queue", None)

    # -- mixer -------------------------------------------------------------- #
    def _mixer(self):
        while not self.ever_connected.is_set():
            if self.stop_event.wait(0.2):
                return
        silence = bytes(self.chunk_bytes)
        cur, buffering = None, True
        retry_at, live_failures = 0.0, 0
        end_logged = False
        t_next = time.monotonic()
        stdin = self.encoder.stdin
        while not self.stop_event.is_set():
            if self.skip_event.is_set():
                self.skip_event.clear()
                if cur is not None:
                    cur.close()
                    cur = None

            if cur is None and time.monotonic() >= retry_at:
                try:
                    cur = self._take_next()
                except (OSError, StreamError) as e:
                    live_failures += 1
                    self.emit("log", f"Audio source error: {e}")
                    if live_failures >= 3:
                        self.emit("fatal", f"Cannot open the audio source: {e}")
                        return
                    retry_at = time.monotonic() + 3
                if cur is not None:
                    buffering, end_logged = True, False
                elif self.cfg["source"] == "queue" and self.playlist.peek() is None and not end_logged:
                    end_logged = True
                    items, _ = self.playlist.snapshot()
                    self.emit("log", "Queue finished - sending silence. Add tracks to keep playing."
                              if items else "Queue is empty - add tracks (sending silence).")
                    self.emit("track", "")

            data = None
            if cur is not None:
                if buffering and cur.ready():
                    buffering = False
                if not buffering:
                    data = cur.get()
                    if data is EOF:
                        if cur.live:
                            reason = cur.error() or "ended"
                            live_failures += 1 if cur.bytes == 0 else 0
                            if live_failures >= 3:
                                cur.close()
                                self.emit("fatal", f"Cannot open the audio source: {reason}")
                                return
                            self.emit("log", f"Audio source stopped ({reason}) - restarting")
                            retry_at = time.monotonic() + 3
                        self._finish(cur)
                        cur = None
                        continue          # take the next track in the same time slot
                    if data is None and cur.live:
                        buffering = True
                    elif cur.live:
                        live_failures = 0
                        cur.trim_backlog(MAX_BACKLOG)

            out = data if data else silence
            if len(out) < self.chunk_bytes:
                out += bytes(self.chunk_bytes - len(out))
            try:
                stdin.write(out)
                stdin.flush()
            except (OSError, ValueError):
                if not self.stop_event.is_set():
                    tail = self.encoder_tail[-1] if self.encoder_tail else "encoder exited"
                    self.emit("fatal", f"MP3 encoder stopped: {tail}")
                break

            t_next += CHUNK_SEC
            delay = t_next - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -1.0:
                t_next = time.monotonic()
        if cur is not None:
            cur.close()

    # -- titles for live sources -------------------------------------------- #
    def _title_watcher(self):
        from .lastfm import LastFM, LastFMError
        mode = self.cfg["title_source"]
        client = None
        if mode.startswith("Last.fm"):
            client = LastFM(self.cfg.get("lastfm_api_key", ""))
            user = self.cfg.get("lastfm_watch_user", "").strip()
            if not client.configured or not user:
                self.emit("log", "Last.fm title source needs an API key and a user name (Integrations tab).")
                return
        last = None
        while not self.stop_event.is_set():
            try:
                title = client.user_now_playing(user) if client else nowplaying.detect(mode)
            except (LastFMError, OSError) as e:
                title = last
                self.emit("log", f"Now playing lookup failed: {e}")
            if title and title != last:
                last = title
                self.current_title = title
                self.emit("track", title)
            self.stop_event.wait(15 if client else 2)

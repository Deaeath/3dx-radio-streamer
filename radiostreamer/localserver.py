"""Built-in stream server: listeners connect straight to this PC, no radio host account needed.

Speaks the same HTTP/ICY dialect as Shoutcast/Icecast, so any radio player (including a 3DXChat room
radio) can play it:
    /  /stream  /stream.mp3  /;     the MP3 stream (a browser asking for "/" gets a small player page)
    /status.json                   listeners, title, station
    /7.html                        Shoutcast-style status line
New listeners get the last couple of seconds straight away so playback starts quickly. Song titles
are sent as ICY metadata to players that ask for it.
"""

import collections
import html
import json
import socket
import threading
import time

METAINT = 16000                 # bytes of audio between ICY metadata blocks
BURST_SECONDS = 2.0             # audio sent immediately to a new listener
SLOW_LISTENER_SECONDS = 15      # a listener this far behind is disconnected


class _Listener:
    def __init__(self, conn, addr, metaint):
        self.conn, self.addr, self.metaint = conn, addr, metaint
        self.chunks = collections.deque()
        self.queued = 0
        self.cv = threading.Condition()
        self.closed = False
        self.until_meta = metaint
        self.sent_title = None


class LocalServer:
    def __init__(self, port, bind="0.0.0.0", name="", genre="", url="", bitrate=128, max_listeners=50, log=print):
        self.port, self.bind = int(port), bind
        self.name, self.genre, self.url, self.bitrate = name or "My Radio", genre or "", url or "", int(bitrate)
        self.max_listeners = int(max_listeners) or 50
        self.log = log
        self.title = ""
        self.peak = 0
        self.listeners = []
        self.lock = threading.Lock()
        self.burst = collections.deque()
        self.burst_bytes = 0
        self.burst_cap = int(self.bitrate * 1000 / 8 * BURST_SECONDS)
        self.slow_cap = int(self.bitrate * 1000 / 8 * SLOW_LISTENER_SECONDS)
        self.sock = None
        self.running = False

    # -- lifecycle ---------------------------------------------------------- #
    def start(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind((self.bind, self.port))
        except OSError as e:
            s.close()
            raise OSError(f"Port {self.port} is already in use or blocked ({e.strerror or e}). Pick another port.") from e
        s.listen(64)
        self.sock, self.running = s, True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except (OSError, AttributeError):
            pass
        with self.lock:
            for lst in self.listeners:
                self._drop(lst)
            self.listeners.clear()

    @property
    def count(self):
        return len(self.listeners)

    def set_title(self, title):
        self.title = title or ""

    # -- audio in ------------------------------------------------------------ #
    def broadcast(self, data):
        self.burst.append(data)
        self.burst_bytes += len(data)
        while self.burst_bytes > self.burst_cap and len(self.burst) > 1:
            self.burst_bytes -= len(self.burst.popleft())
        with self.lock:
            for lst in list(self.listeners):
                with lst.cv:
                    if lst.queued > self.slow_cap:            # can't keep up: let them reconnect fresh
                        self._drop(lst)
                        continue
                    lst.chunks.append(data)
                    lst.queued += len(data)
                    lst.cv.notify()

    # -- listeners ------------------------------------------------------------ #
    def _drop(self, lst):
        with lst.cv:
            lst.closed = True
            lst.cv.notify()
        try:
            lst.conn.close()
        except OSError:
            pass

    def _accept_loop(self):
        while self.running:
            try:
                conn, addr = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn, addr), daemon=True).start()

    def _handle(self, conn, addr):
        try:
            conn.settimeout(10)
            raw = b""
            while b"\r\n\r\n" not in raw and len(raw) < 16384:
                part = conn.recv(4096)
                if not part:
                    conn.close()
                    return
                raw += part
            head = raw.split(b"\r\n\r\n", 1)[0].decode("latin-1")
            lines = head.split("\r\n")
            parts = lines[0].split(" ")
            method, path = (parts[0], parts[1]) if len(parts) >= 2 else ("GET", "/")
            headers = {k.strip().lower(): v.strip() for k, _, v in (ln.partition(":") for ln in lines[1:]) if k}
        except (OSError, UnicodeError):
            conn.close()
            return
        path = path.split("?", 1)[0]
        ua, accept = headers.get("user-agent", "").lower(), headers.get("accept", "").lower()
        try:
            if path == "/status.json":
                return self._reply(conn, "200 OK", "application/json", json.dumps(self.status()).encode())
            if path == "/7.html":
                st = self.status()
                body = (f"<html><body>{st['listeners']},1,{self.peak},{self.max_listeners},{st['listeners']},"
                        f"{self.bitrate},{html.escape(self.title)}</body></html>").encode()
                return self._reply(conn, "200 OK", "text/html", body)
            if path == "/" and "text/html" in accept and "mozilla" in ua:
                return self._reply(conn, "200 OK", "text/html; charset=utf-8", self._page().encode("utf-8"))
            if method not in ("GET", "HEAD"):
                return self._reply(conn, "405 Method Not Allowed", "text/plain", b"Method not allowed")
            if self.count >= self.max_listeners:
                return self._reply(conn, "503 Service Unavailable", "text/plain", b"The station is full right now.")
            self._serve_audio(conn, addr, headers.get("icy-metadata") == "1", method == "HEAD")
        except OSError:
            try:
                conn.close()
            except OSError:
                pass

    def _reply(self, conn, status, ctype, body):
        conn.sendall((f"HTTP/1.0 {status}\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\n"
                      "Cache-Control: no-cache\r\nAccess-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n").encode() + body)
        conn.close()

    def _serve_audio(self, conn, addr, wants_meta, head_only):
        metaint = METAINT if wants_meta else 0
        hdr = ["HTTP/1.0 200 OK", "Content-Type: audio/mpeg", "Cache-Control: no-cache, no-store",
               "Access-Control-Allow-Origin: *", "Connection: close",
               f"icy-name: {self.name}", f"icy-genre: {self.genre}", f"icy-url: {self.url}",
               f"icy-br: {self.bitrate}", "icy-pub: 0"]
        if metaint:
            hdr.append(f"icy-metaint: {metaint}")
        conn.sendall(("\r\n".join(hdr) + "\r\n\r\n").encode("utf-8", "replace"))
        if head_only:
            conn.close()
            return
        conn.settimeout(30)
        lst = _Listener(conn, addr, metaint)
        lst.chunks.extend(self.burst)
        lst.queued = sum(len(c) for c in lst.chunks)
        with self.lock:
            self.listeners.append(lst)
            self.peak = max(self.peak, len(self.listeners))
        try:
            while self.running:
                with lst.cv:
                    while not lst.chunks and not lst.closed and self.running:
                        lst.cv.wait(1.0)
                    if lst.closed:
                        break
                    data = b"".join(lst.chunks)
                    lst.chunks.clear()
                    lst.queued = 0
                if data:
                    conn.sendall(self._with_meta(lst, data) if metaint else data)
        except OSError:
            pass
        finally:
            with self.lock:
                if lst in self.listeners:
                    self.listeners.remove(lst)
            try:
                conn.close()
            except OSError:
                pass

    def _with_meta(self, lst, data):
        out, pos = [], 0
        while pos < len(data):
            take = min(lst.until_meta, len(data) - pos)
            out.append(data[pos:pos + take])
            pos += take
            lst.until_meta -= take
            if lst.until_meta == 0:
                out.append(self._meta_block(lst))
                lst.until_meta = lst.metaint
        return b"".join(out)

    def _meta_block(self, lst):
        if self.title == lst.sent_title:
            return b"\x00"
        lst.sent_title = self.title
        text = "StreamTitle='" + self.title.replace("'", "’") + "';"
        raw = text.encode("utf-8")[:4064]
        n = (len(raw) + 15) // 16
        return bytes([n]) + raw.ljust(n * 16, b"\x00")

    # -- status --------------------------------------------------------------- #
    def status(self):
        return {"station": self.name, "title": self.title, "listeners": self.count, "peak": self.peak,
                "max_listeners": self.max_listeners, "bitrate": self.bitrate}

    def _page(self):
        n = html.escape(self.name)
        return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{n}</title><style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0e1018;color:#eef0f8;font:16px system-ui,sans-serif}}
main{{text-align:center;padding:24px}}h1{{margin:0 0 6px;font-size:28px}}p{{color:#9ba3c0;margin:6px 0 18px}}
audio{{width:min(420px,90vw)}}small{{display:block;margin-top:14px;color:#646c8c}}
</style></head><body><main><h1>{n}</h1><p id="t">{html.escape(self.title) or "Live now"}</p>
<audio controls autoplay src="stream.mp3"></audio><small id="l"></small></main>
<script>
async function tick(){{try{{const s=await (await fetch("status.json",{{cache:"no-store"}})).json();
document.getElementById("t").textContent=s.title||"Live now";
document.getElementById("l").textContent=s.listeners+" listening";}}catch(e){{}}}}
tick();setInterval(tick,10000);
</script></body></html>"""

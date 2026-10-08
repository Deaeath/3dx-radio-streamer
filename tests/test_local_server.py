"""Built-in server end to end: queue -> encoder -> built-in server -> listeners (ICY titles, plain, browser, status).

    python tests/test_local_server.py <music-folder> [easy]
With "easy", also opens a real Cloudflare quick tunnel and listens through the public link.
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from radiostreamer import config, media, tools
from radiostreamer.engine import Broadcaster, Playlist

music = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else "lan"
PORT = 18611
cfg = dict(config.DEFAULTS, server_type=config.BUILTIN, host_mode=mode, local_port=PORT, source="queue",
           name="Test Station", title_source="Manual", loop=True)
events = []
pl = Playlist(media.expand([music], log=lambda m: None), loop=True)
b = Broadcaster(cfg, pl, lambda k, p=None: events.append((k, p)))
b.start()
def keep_titles():                       # what the GUI does: pass each new track title to the server
    seen = 0
    while True:
        for k, p in events[seen:]:
            if k == "track" and p:
                b.set_title(p)
        seen = len(events)
        time.sleep(0.2)


threading.Thread(target=keep_titles, daemon=True).start()
time.sleep(3)


def listen(url, seconds, icy=False, ua="VLC/3.0.20 LibVLC/3.0.20"):
    req = urllib.request.Request(url, headers={"User-Agent": ua, **({"Icy-MetaData": "1"} if icy else {})})
    data, t0 = b"", time.time()
    with urllib.request.urlopen(req, timeout=20) as r:
        hdrs = dict(r.headers)
        while time.time() - t0 < seconds:
            chunk = r.read(4096)
            if not chunk:
                break
            data += chunk
    return hdrs, data


def strip_icy(data, metaint):
    audio, meta, pos = b"", [], 0
    while pos < len(data):
        audio += data[pos:pos + metaint]
        pos += metaint
        if pos >= len(data):
            break
        n = data[pos] * 16
        if n:
            meta.append(data[pos + 1:pos + 1 + n].rstrip(b"\x00").decode("utf-8", "replace"))
        pos += 1 + n
    return audio, meta


def level(mp3):
    open("_ls.mp3", "wb").write(mp3)
    r = subprocess.run([tools.ffmpeg(), "-hide_banner", "-i", "_ls.mp3", "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"mean_volume: (\S+) dB", r.stderr)
    d = re.search(r"Duration: (\S+),|time=(\S+)", r.stderr)
    return m.group(1) if m else "undecodable"


base = f"http://127.0.0.1:{PORT}"
h, d = listen(base + "/stream.mp3", 6, icy=True)
audio, meta = strip_icy(d, int(h.get("icy-metaint", 0)))
print(f"ICY listener: {len(d)} bytes in 6s, icy-name={h.get('icy-name')!r}, metaint={h.get('icy-metaint')}, "
      f"titles={meta[:2]}, audio level {level(audio)} dB")
h2, d2 = listen(base + "/", 3)
print(f"plain listener on '/': {h2.get('Content-Type')}, {len(d2)} bytes, level {level(d2)} dB")
page = urllib.request.urlopen(urllib.request.Request(base + "/", headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})).read().decode()
print("browser gets player page:", "<audio" in page and "Test Station" in page)
print("status.json:", json.loads(urllib.request.urlopen(base + "/status.json").read()))
if mode == "easy":
    t0 = time.time()
    while not b.listen_url and time.time() - t0 < 60:
        time.sleep(0.5)
    print("public link:", b.listen_url, f"(after {time.time() - t0:.0f}s)")
    if b.listen_url:
        time.sleep(3)
        h3, d3 = listen(b.listen_url, 8)
        print(f"through the public link: {h3.get('Content-Type')}, {len(d3)} bytes in 8s "
              f"(~{len(d3) * 8 / 8000:.0f} kbps), level {level(d3)} dB")
b.stop()
time.sleep(1)
print("fatal:", [p for k, p in events if k == "fatal"], "| link events:", [p for k, p in events if k == "listen_url"])

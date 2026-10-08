"""A free public link to the built-in server with a Cloudflare quick tunnel (no account, no port forwarding).

cloudflared makes an outgoing connection to Cloudflare and gets a random https://<words>.trycloudflare.com
address that forwards to this PC, so it works behind routers, CGNAT and VPNs. The address changes each
time the tunnel starts.
"""

import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from . import tools
from .config import BIN_DIR

CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_cloudflared():
    for d in [BIN_DIR] + tools.bundle_dirs():
        exe = Path(d) / ("cloudflared" + tools.EXE)
        if exe.is_file():
            return str(exe)
    import shutil
    return shutil.which("cloudflared")


def ensure_cloudflared(log=print):
    exe = find_cloudflared()
    if exe:
        return exe
    if sys.platform != "win32":
        raise OSError("Install cloudflared (https://github.com/cloudflare/cloudflared) to use Easy hosting.")
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    target = BIN_DIR / "cloudflared.exe"
    log("Downloading Cloudflare's free tunnel tool (one time, about 60 MB)...")
    tmp = target.with_suffix(".part")
    urllib.request.urlretrieve(CLOUDFLARED_URL, tmp)
    os.replace(tmp, target)
    return str(target)


class QuickTunnel:
    def __init__(self, port, on_url, log=print):
        self.port = port
        self.on_url = on_url
        self.log = log
        self.proc = None
        self.url = None
        self.stopped = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.stopped.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except OSError:
                pass

    def _announce_when_ready(self, url):
        """A brand-new trycloudflare.com name takes a few seconds to exist in DNS. Anyone who looks it up too
        early can cache "doesn't exist" for minutes, so only hand out the link once it really works. The DNS
        check uses DNS-over-HTTPS, which doesn't touch this PC's own DNS cache."""
        host = url.split("//", 1)[1]
        deadline = time.time() + 90
        resolved = False
        while time.time() < deadline and not self.stopped.is_set() and self.url == url:
            try:
                req = urllib.request.Request(f"https://cloudflare-dns.com/dns-query?name={host}&type=A",
                                             headers={"Accept": "application/dns-json"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    resolved = '"Answer"' in r.read().decode("utf-8", "replace")
            except OSError:
                resolved = False
            if resolved:
                break
            self.stopped.wait(2)
        if resolved:
            self.stopped.wait(3)                                  # let the name reach other resolvers too
            for _ in range(10):
                try:
                    with urllib.request.urlopen(f"{url}/status.json", timeout=10) as r:
                        if r.status == 200:
                            break
                except OSError:
                    if self.stopped.wait(2):
                        return
        if self.stopped.is_set() or self.url != url:
            return
        if not resolved:
            self.log("The public link is taking a while to come online; it may need a minute before it plays.")
        self.on_url(url)

    def _run(self):
        delay = 3
        while not self.stopped.is_set():
            try:
                exe = ensure_cloudflared(self.log)
            except OSError as e:
                self.log(f"Tunnel: {e}")
                return
            except Exception as e:  # download failed
                self.log(f"Tunnel: couldn't get cloudflared ({e}). Retrying in {delay}s.")
                if self.stopped.wait(delay):
                    return
                delay = min(delay * 2, 60)
                continue
            self.proc = tools.popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}"],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            started = time.time()
            for raw in self.proc.stdout:
                line = raw.decode("utf-8", "replace")
                m = URL_RE.search(line)
                if m and m.group(0) != self.url:
                    self.url = m.group(0)
                    threading.Thread(target=self._announce_when_ready, args=(self.url,), daemon=True).start()
                if "Registered tunnel connection" in line:
                    delay = 3
            self.proc.wait()
            if self.stopped.is_set():
                return
            self.url = None
            self.on_url(None)
            self.log(f"Tunnel closed (exit {self.proc.returncode}) - reopening in {delay}s. The link will change.")
            if time.time() - started > 120:
                delay = 3
            if self.stopped.wait(delay):
                return
            delay = min(delay * 2, 60)

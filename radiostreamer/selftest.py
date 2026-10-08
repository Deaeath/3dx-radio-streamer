"""`3DX Radio Streamer.exe --selftest [report.txt]` - checks tools, devices and the full broadcast
pipeline against a built-in local server. Writes a report and exits 0 (pass) or 1 (fail)."""

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import APP_NAME, VERSION, capture, config, tools
from .engine import Broadcaster, Playlist


class _LocalServer:
    """Accepts one Shoutcast v1 source on 127.0.0.1 and counts the bytes."""

    def __init__(self):
        self.received = 0
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1] - 1      # the app connects to port + 1
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.srv.accept()
        buf = b""
        while b"\r\n" not in buf:
            buf += conn.recv(1024)
        conn.sendall(b"OK2\r\nicy-caps:11\r\n\r\n")
        while True:
            d = conn.recv(65536)
            if not d:
                break
            self.received += len(d)


def run(report_path=None):
    lines, ok = [], True

    def check(name, passed, detail=""):
        nonlocal ok
        ok &= bool(passed)
        lines.append(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    lines.append(f"{APP_NAME} {VERSION} self-test - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"frozen={getattr(sys, 'frozen', False)} python={sys.version.split()[0]} platform={sys.platform}")
    try:
        import tkinter

        from . import gui, wizard  # noqa: F401  (catches packaging / syntax errors in the UI)
        root = tkinter.Tk()
        root.withdraw()
        root.destroy()
        check("user interface loads", True)
    except Exception as e:
        check("user interface loads", False, repr(e))
    ff = tools.ffmpeg()
    check("ffmpeg found", ff, ff or "missing")
    if ff:
        enc = tools.run([ff, "-hide_banner", "-encoders"], 20).stdout
        check("ffmpeg has MP3 encoder", "libmp3lame" in enc)
    yt = tools.ytdlp()
    check("yt-dlp found", yt, f"{yt} ({tools.tool_version(yt)})" if yt else "missing")
    devices = tools.list_input_devices(ff)
    lines.append(f"[INFO] input devices: {devices or 'none'}")
    if capture.available():
        loops = capture.list_loopback_devices()
        check("system audio capture available", loops, f"{len(loops)} output device(s)")
    if capture.app_capture_available():
        apps = capture.list_apps()
        lines.append(f"[INFO] one-app capture: {len(apps)} app(s) running: {', '.join(apps) or 'none'}")
    else:
        lines.append("[INFO] one-app capture: needs Windows 10 version 2004 or newer")
    lines.append(f"[INFO] settings: {config.SETTINGS_FILE}")

    if ff:
        tmp = Path(tempfile.mkdtemp(prefix="3dxrs-"))
        tone = tmp / "tone.wav"
        tools.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                   "-metadata", "artist=Self", "-metadata", "title=Test Tone", str(tone)], 30)
        srv = _LocalServer()
        cfg = dict(config.DEFAULTS, server_type="Shoutcast v1", host="127.0.0.1", port=srv.port, password="selftest", source="queue",
                   loop=False, normalize=True)
        events = []
        pl = Playlist([{"kind": "file", "src": str(tone), "title": "tone"}], loop=False)
        b = Broadcaster(cfg, pl, lambda k, p=None: events.append((k, p)))
        b.start()
        time.sleep(5)
        b.stop()
        time.sleep(0.5)
        levels = [p for k, p in events if k == "level"]
        tracks = [p for k, p in events if k == "track" and p]
        check("connects & streams to a local test server", srv.received > 40000,
              f"{srv.received} bytes in 5 s")
        check("reads track tags", tracks[:1] == ["Self - Test Tone"], str(tracks[:1]))
        check("level meter sees audio", levels and max(levels) > -40, f"max {max(levels or [-120]):.1f} LUFS")
        fatal = [p for k, p in events if k == "fatal"]
        check("no engine errors", not fatal, "; ".join(fatal))

        # built-in server: host on this PC and have a listener connect (local network mode, no internet needed)
        from .localserver import LocalServer
        import urllib.request
        probe = socket.socket(); probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]; probe.close()
        cfg2 = dict(config.DEFAULTS, server_type=config.BUILTIN, host_mode="lan", local_port=port, source="queue", loop=True)
        events2 = []
        b2 = Broadcaster(cfg2, Playlist([{"kind": "file", "src": str(tone), "title": "tone"}], loop=True),
                         lambda k, p=None: events2.append((k, p)))
        got = 0
        try:
            b2.start()
            time.sleep(2)
            with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/stream.mp3",
                                                               headers={"User-Agent": "selftest"}), timeout=10) as r:
                t0 = time.time()
                while time.time() - t0 < 2:
                    got += len(r.read(4096))
        except Exception as e:
            lines.append(f"[INFO] built-in server error: {e!r}")
        finally:
            b2.stop()
        check("built-in server serves listeners", got > 20000, f"{got} bytes in 2 s")
        try:
            tone.unlink()
            tmp.rmdir()
        except OSError:
            pass

    lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
    text = "\n".join(lines)
    report = Path(report_path or os.path.join(tempfile.gettempdir(), "3dx-radio-streamer-selftest.txt"))
    report.write_text(text + "\n", encoding="utf-8")
    try:
        print(text)
    except (OSError, AttributeError, ValueError):   # windowed exe has no console
        pass
    return 0 if ok else 1

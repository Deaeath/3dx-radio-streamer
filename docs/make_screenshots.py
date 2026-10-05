r"""Regenerate the README screenshots in docs/images with made-up demo data (Windows).

    set APPDATA=%TEMP%\rs-demo\appdata & set LOCALAPPDATA=%TEMP%\rs-demo\local
    python docs\make_screenshots.py <folder-with-demo-songs> docs\images

Uses a local stand-in server, so nothing goes on air and no real server details appear.
"""

import ctypes
import json
import os
import socket
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))

from PIL import ImageGrab  # noqa: E402

from mock_server import MockServer  # noqa: E402
from radiostreamer import config, engine, gui, media, protocol  # noqa: E402

music, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

DEMO = dict(config.DEFAULTS, provider="Listen2MyRadio", server_type="Shoutcast v1",
            host="my-radio.example.com", port=8000, password="sunshine123", name="Sunshine Radio",
            genre="Various", source="queue", wizard_done=True, title_source="Manual")
config.save_settings(DEMO)

# Point every connection at a local stand-in server instead of the made-up host
mock_port = 18500
srv = MockServer(mock_port)


def local_connect(cfg, timeout=10):
    return protocol.open_source_connection(dict(cfg, host="127.0.0.1", port=mock_port), timeout)


engine.open_source_connection = local_connect
gui.open_source_connection = local_connect
gui.update_metadata = lambda cfg, title: f"Stream title set: {title}"


def shot(win, name):
    win.lift()
    win.attributes("-topmost", True)
    for _ in range(3):
        win.update()
        time.sleep(0.15)
    hwnd = int(win.wm_frame(), 16)
    rect = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    img = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    img.save(out / f"{name}.png", optimize=True)
    win.attributes("-topmost", False)
    print("saved", name)


orig_init = gui.App.__init__


def init(app, root):
    orig_init(app, root)
    root.geometry("940x880+60+20")
    steps = []

    def after(ms, fn):
        steps.append((ms, fn))

    def run_steps(i=0):
        if i < len(steps):
            ms, fn = steps[i]
            root.after(ms, lambda: (fn(), run_steps(i + 1)))

    state = {}

    def open_wizard():
        app.open_wizard()
        state["wz"] = [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"][-1]
        state["wz"].geometry("+200+90")

    def wz_page(i, name):
        def f():
            state["wz"].show(i)
            if name:
                shot(state["wz"], name)
        return f

    after(800, open_wizard)
    after(500, wz_page(0, "wizard-1-welcome"))
    after(200, wz_page(1, None))
    after(100, lambda: state["wz"]._test())
    after(1500, lambda: shot(state["wz"], "wizard-2-server"))
    after(200, wz_page(2, "wizard-3-source"))
    after(200, wz_page(5, "wizard-4-done"))
    after(200, lambda: state["wz"].destroy())

    def fill_queue():
        app.playlist.clear()
        app.playlist.add(media.expand([str(music)], log=lambda m: None))
        for it in app.playlist.items:
            it["title"] = media.probe_title(it["src"])
        app.refresh_queue(force=True)
    after(300, fill_queue)

    def links():
        dlg = gui.LinkDialog(root, lambda lines: None)
        dlg.geometry("+200+120")
        dlg.text.delete("1.0", "end")
        dlg.text.insert("1.0", "https://www.youtube.com/watch?v=your-favourite-song\n"
                               "https://soundcloud.com/some-artist/a-cool-track\n"
                               "https://open.spotify.com/playlist/your-playlist\n"
                               "The Happy Hamsters - Sunny Day Song\n")
        state["dlg"] = dlg
    after(300, links)
    after(500, lambda: shot(state["dlg"], "add-links"))
    after(100, lambda: state["dlg"].destroy())

    after(300, lambda: (app.nb.select(0), app.start()))
    after(4500, lambda: shot(root, "main-live"))
    after(200, lambda: app.nb.select(1))
    after(400, lambda: shot(root, "server-tab"))
    after(200, lambda: (app.nb.select(0), app.stop()))
    after(300, root.destroy)
    run_steps()


gui.App.__init__ = init
gui.run()
print("server received", len(srv.data), "bytes")

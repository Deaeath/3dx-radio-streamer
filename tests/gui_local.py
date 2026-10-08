"""GUI check of 'Host it myself': Server tab, Check setup, GO LIVE with Easy mode, a listener joins, wizard page."""
import ctypes
import os
import sys
import threading
import time
import urllib.request
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import ImageGrab

from radiostreamer import config, gui, media

music, shot_dir = sys.argv[1], sys.argv[2]


def shot(win, name):
    win.update(); time.sleep(0.3); win.update()
    r = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(int(win.wm_frame(), 16), 9, ctypes.byref(r), ctypes.sizeof(r))
    ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True).save(os.path.join(shot_dir, name))


orig = gui.App.__init__


def init(app, root):
    orig(app, root)
    for w in root.winfo_children():
        if w.winfo_class() == "Toplevel":
            w.destroy()
    root.geometry("960x900+40+10")
    v = app.vars
    v["provider"].set("Host it myself (free, no account)"); app.on_provider_change(apply=True)
    v["local_port"].set("18624"); v["host_mode"].set("easy"); v["wizard_done"].set(True); v["name"].set("Sunshine Radio")
    v["source"].set("queue"); app.on_source_change()
    app.playlist.clear(); app.playlist.add(media.expand([music], log=lambda m: None))
    out = {}

    def step1():
        root.lift(); root.attributes("-topmost", True)
        app.nb.select(1); app.test_connection(); root.after(4000, step2)

    def step2():
        out["check"] = app.test_lbl.cget("text")
        shot(root, "local_server_tab.png")
        app.nb.select(0); app.start(); root.after(500, wait_link)

    def wait_link(tries=0):
        if app.room_url.get().startswith("https://") or tries > 60:
            out["link"] = app.room_url.get()
            threading.Thread(target=listener, daemon=True).start()
            root.after(6000, step3)
        else:
            root.after(500, wait_link, tries + 1)

    def listener():
        try:
            with urllib.request.urlopen(urllib.request.Request(out["link"], headers={"User-Agent": "VLC/3"}), timeout=20) as r:
                t0, n = time.time(), 0
                while time.time() - t0 < 9:
                    n += len(r.read(4096))
                out["listener_bytes"] = n
        except Exception as e:
            out["listener_error"] = repr(e)

    def step3():
        out["stats"] = app.stats_lbl.cget("text")
        out["status"] = app.status_lbl.cget("text")
        shot(root, "local_live.png")
        root.after(4000, step4)

    def step4():
        app.stop()
        app.open_wizard()
        wz = [w for w in root.winfo_children() if w.winfo_class() == "Toplevel"][-1]
        wz.show(1)
        root.after(600, lambda: (shot(wz, "local_wizard.png"), wz.destroy(), finish()))

    def finish():
        for k, val in out.items():
            print(f"{k}: {val}")
        root.after(300, root.destroy)
    root.after(1200, step1)


gui.App.__init__ = init
gui.run()

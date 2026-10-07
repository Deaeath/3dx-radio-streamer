"""GUI check of Server tab > Test connection: OK, refused, and pressed while live (local stand-in server only)."""
import ctypes
import os
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import ImageGrab

from mock_server import MockServer
from radiostreamer import gui

shot_dir = sys.argv[1]
srv = MockServer(19100)


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
    root.geometry("940x700+60+20")           # short window: the status bar must still show
    v = app.vars
    v["host"].set("127.0.0.1"); v["password"].set("pw"); v["wizard_done"].set(True); v["source"].set("queue")
    app.nb.select(1)
    out = []

    def step1():
        root.lift(); root.attributes("-topmost", True)
        v["port"].set("19100"); app.test_connection(); root.after(1500, step2)

    def step2():
        out.append(("ok", app.test_lbl.cget("text"), str(app.test_lbl.cget("style"))))
        shot(root, "test_ok.png")
        v["port"].set("19190"); app.test_connection(); root.after(2500, step3)

    def step3():
        out.append(("refused", app.test_lbl.cget("text"), str(app.test_lbl.cget("style"))))
        shot(root, "test_refused.png")
        v["port"].set("19100")
        srv.log.clear()
        app.start(); root.after(2500, step4)

    def step4():
        logins_before = len(srv.log)
        app.nb.select(1); app.test_connection()
        root.after(800, lambda: step5(logins_before))

    def step5(before):
        out.append(("while live", app.test_lbl.cget("text"), str(app.test_lbl.cget("style")),
                    f"extra logins during test: {len(srv.log) - before}"))
        out.append(("status bar visible", app.statusbar.winfo_ismapped(), app.statusbar.cget("text")[:60]))
        shot(root, "test_live.png")
        app.stop()
        for o in out:
            print(o)
        root.after(300, root.destroy)
    root.after(1200, step1)


gui.App.__init__ = init
gui.run()

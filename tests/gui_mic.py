"""GUI check of the Microphone section: go live with a queue, press MIC (a simulated mic, not a real one)."""
import ctypes
import os
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import ImageGrab

from mock_server import MockServer
from radiostreamer import engine, gui, media, tools

music, shot_path = sys.argv[1], sys.argv[2]
fake_mic = lambda name: ["-re", "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000"]
tools.device_input_args = fake_mic
engine.tools.device_input_args = fake_mic
srv = MockServer(18950)


def shot(win, path):
    win.update(); time.sleep(0.3); win.update()
    hwnd = int(win.wm_frame(), 16)
    r = wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r))
    ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom), all_screens=True).save(path)


orig = gui.App.__init__


def init(app, root):
    orig(app, root)
    for w in root.winfo_children():
        if w.winfo_class() == "Toplevel":
            w.destroy()
    root.geometry("900x860+60+20")
    v = app.vars
    v["host"].set("127.0.0.1"); v["port"].set("18950"); v["password"].set("pw"); v["wizard_done"].set(True)
    v["source"].set("queue"); app.on_source_change()
    app.playlist.clear(); app.playlist.add(media.expand([music], log=lambda m: None))

    def go():
        root.lift(); root.attributes("-topmost", True)
        app.start()
        root.after(3000, mic_on)

    def mic_on():
        app.toggle_mic()
        root.after(2500, snap)

    def snap():
        shot(root, shot_path)
        print("mic button:", app.mic_btn.cget("text"), "| mic list:", list(app.mic_cb.cget("values"))[:4])
        app.toggle_mic()
        root.after(800, finish)

    def finish():
        app.stop()
        print("log:\n" + "\n".join(l for l in app.log_box.get("1.0", "end").splitlines() if l.strip()))
        print("server bytes:", len(srv.data))
        root.after(300, root.destroy)
    root.after(1200, go)


gui.App.__init__ = init
gui.run()

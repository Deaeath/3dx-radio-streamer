"""Open the app, walk the wizard and screenshot each step (QA helper)."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import ImageGrab
import tkinter as tk
from radiostreamer import gui

out = sys.argv[1]
shots = []
def grab(win, name):
    win.update(); time.sleep(0.4); win.update()
    x, y, w, h = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()
    ImageGrab.grab(bbox=(x - 8, y - 32, x + w + 8, y + h + 8), all_screens=True).save(os.path.join(out, name + ".png"))
    shots.append(name)

orig_init = gui.App.__init__
def init(self, root):
    orig_init(self, root)
    def script():
        root.lift(); root.attributes("-topmost", True)
        wiz = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
        if not wiz:
            print("no wizard opened!"); root.destroy(); return
        wz = wiz[0]; wz.attributes("-topmost", True)
        for i, name in enumerate(wz.PAGES):
            if i == 2:
                wz.v["source"].set("loopback")
            wz.show(i); grab(wz, f"wizard_{i+1}_{name}")
        wz.v["source"].set("queue"); wz.destroy()
        self.playlist.add([{"kind": "file", "src": "a.mp3", "title": "Test Artist - Tone A"},
                           {"kind": "ytdl", "src": "ytsearch1:x", "title": "Daft Punk - One More Time"},
                           {"kind": "stream", "src": "http://x", "title": "Groove Salad [SomaFM]"}])
        for t in range(4):
            self.nb.select(t); root.update(); grab(root, f"main_{t}")
        print("log:", self.log_box.get("1.0", "end").strip()[:600])
        root.destroy()
    root.after(1500, script)
gui.App.__init__ = init
gui.run()
print("shots:", shots)

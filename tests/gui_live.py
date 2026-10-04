"""Drive the real GUI: queue two files, GO LIVE against a mock server, screenshot, stop."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import ImageGrab
from radiostreamer import gui
from mock_server import MockServer
S, out = sys.argv[1], sys.argv[2]
srv = MockServer(18400)
orig = gui.App.__init__
def init(self, root):
    orig(self, root)
    for w in root.winfo_children():
        if w.winfo_class() == "Toplevel": w.destroy()
    v = self.vars
    v["host"].set("127.0.0.1"); v["port"].set("18400"); v["password"].set("pw"); v["wizard_done"].set(True)
    self.playlist.clear()
    self._expand_async([os.path.join(S, "music")], "folder")
    def go():
        root.lift(); root.attributes("-topmost", True)
        self.start()
        root.after(4000, snap)
    def snap():
        root.update(); time.sleep(0.3)
        x, y, w, h = root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(os.path.join(out, "live.png"))
        print("status:", self.status_lbl.cget("text"), "|", self.stats_lbl.cget("text"), "| np:", self.np_var.get())
        self.stop()
        print("log:\n" + self.log_box.get("1.0", "end").strip())
        print("server got", len(srv.data), "bytes, login", srv.log)
        root.after(300, root.destroy)
    root.after(1500, go)
gui.App.__init__ = init
gui.run()

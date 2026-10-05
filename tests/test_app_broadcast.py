"""End to end: broadcast one app's sound through the real engine to a local stand-in server.

A child process plays a tone into the (inaudible) VB-CABLE Input; the engine airs it with
source="app" and the mock server must receive MP3 with a level well above silence.
"""
import os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from radiostreamer import capture, config  # noqa: E402
from radiostreamer.engine import Broadcaster, Playlist  # noqa: E402
from mock_server import MockServer  # noqa: E402

tone = subprocess.Popen([sys.executable, os.path.join(HERE, "test_app_capture.py"), "--tone", "440"])
try:
    time.sleep(1.5)
    capture.find_app = lambda name: tone.pid
    srv = MockServer(18300)
    cfg = dict(config.DEFAULTS, server_type="Shoutcast v1", host="127.0.0.1", port=18300, password="pw",
               source="app", app_name="tone.exe")
    events = []
    b = Broadcaster(cfg, Playlist([], loop=False), lambda k, p=None: events.append((k, p)))
    b.start()
    time.sleep(5)
    b.stop()
    time.sleep(0.5)
finally:
    tone.kill()

levels = [p for k, p in events if k == "level"]
fatal = [p for k, p in events if k == "fatal"]
print(f"server got {len(srv.data)} bytes; max level {max(levels or [-120]):.1f} LUFS; fatal={fatal}")
assert not fatal, fatal
assert len(srv.data) > 40000, "too little audio reached the server"
assert max(levels) > -40, "the app's tone did not reach the stream"
print("PASS")

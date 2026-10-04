import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from radiostreamer import media, config
from radiostreamer.engine import Broadcaster, Playlist
from mock_server import MockServer

S = sys.argv[1]
cfg = dict(config.DEFAULTS, server_type="Shoutcast v1", host="127.0.0.1", port=18200, password="pw",
           source="queue", match_service="SoundCloud", loop=False)
media.configure(cfg)
log = lambda m: print("   expand:", m)
items = media.expand([os.path.join(S, "music", "a.mp3"), os.path.join(S, "test.m3u"),
                      "https://soundcloud.com/forss/flickermood",
                      "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
                      "https://ice1.somafm.com/groovesalad-128-mp3"], log)
print("queue:", [(i["kind"], i["title"]) for i in items])
srv = MockServer(18200)
pl = Playlist(items, loop=False)
events = []
t0 = time.time()
def emit(k, p=None):
    events.append((round(time.time() - t0, 1), k, p))
    if k not in ("level", "status", "queue"): print(f"  {time.time()-t0:5.1f}s {k}: {p}")
b = Broadcaster(cfg, pl, emit); b.start()
def wait_track(n, timeout=90):
    end = time.time() + timeout
    while time.time() < end and sum(1 for e in events if e[1] == "track" and e[2]) < n: time.sleep(0.2)
wait_track(3); time.sleep(5); b.skip()        # soundcloud: play 5s then skip
wait_track(4); time.sleep(5); b.skip()        # spotify->soundcloud: 5s
wait_track(5); time.sleep(6)                  # live radio 6s
b.stop(); elapsed = time.time() - t0; time.sleep(1)
open(os.path.join(S, "engine_out.mp3"), "wb").write(srv.data)
lv = [p for _, k, p in events if k == "level"]
print(f"login={srv.log} bytes={len(srv.data)} wall={elapsed:.1f}s levels={len(lv)} max={max(lv):.1f}")

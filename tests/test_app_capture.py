"""Single-app capture: only the chosen process's sound is captured (Windows 10 2004+, VB-CABLE).

Two child processes play different tones into the (inaudible) VB-CABLE Input. Capturing one
of them must hear its tone and not the other's.
"""
import math, os, struct, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def play(freq, seconds):
    import pyaudiowpatch as pa
    p = pa.PyAudio()
    wasapi = p.get_host_api_info_by_type(pa.paWASAPI)["index"]
    dev = next(d for d in (p.get_device_info_by_index(i) for i in range(p.get_device_count()))
               if d["hostApi"] == wasapi and d["name"].startswith("CABLE Input")
               and d["maxOutputChannels"] > 0 and not d.get("isLoopbackDevice"))
    s = p.open(format=pa.paInt16, channels=2, rate=44100, output=True, output_device_index=dev["index"])
    period = 44100 // math.gcd(44100, freq)            # whole cycles, so the loop is seamless
    block = b"".join(struct.pack("<hh", v, v) for v in
                     (int(8000 * math.sin(2 * math.pi * freq * i / 44100)) for i in range(period)))
    end = time.time() + seconds
    while time.time() < end:
        s.write(block)
    s.close()


def power(samples, freq, rate):
    """Goertzel: relative power of one frequency."""
    k = 2 * math.cos(2 * math.pi * freq / rate)
    s1 = s2 = 0.0
    for x in samples:
        s1, s2 = x + k * s1 - s2, s1
    return s1 * s1 + s2 * s2 - k * s1 * s2


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--tone":
    play(int(sys.argv[2]), 8)
    sys.exit()

from radiostreamer import capture  # noqa: E402

assert capture.app_capture_available(), "needs Windows 10 2004+"
try:
    capture.AppCapture("no-such-app.exe")
    raise AssertionError("missing app should raise")
except OSError as e:
    print("missing app:", e)

kids = [subprocess.Popen([sys.executable, __file__, "--tone", str(f)]) for f in (440, 1000)]
try:
    time.sleep(1.5)
    capture.find_app = lambda name: kids[0].pid      # target the 440 Hz player by PID
    buf = bytearray()
    cap = capture.AppCapture("tone-440")
    cap.start(buf.extend)
    time.sleep(3)
    cap.stop()
finally:
    for k in kids:
        k.kill()

left = struct.unpack(f"<{len(buf) // 2}h", bytes(buf))[0::2]
print(f"captured {len(buf)} bytes = {len(left) / cap.rate:.2f} s at {cap.rate} Hz")
assert len(left) > cap.rate, "less than 1 s captured"
mid = left[len(left) // 4: len(left) // 4 + cap.rate // 2]
p440, p1000 = power(mid, 440, cap.rate), power(mid, 1000, cap.rate)
print(f"440 Hz power {p440:.3g}, 1000 Hz power {p1000:.3g}")
assert p440 > 100 * max(p1000, 1.0), "target tone missing or the other app leaked in"
print("PASS")

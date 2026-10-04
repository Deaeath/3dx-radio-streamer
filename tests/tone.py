"""Play a 440 Hz tone into the (inaudible) VB-CABLE Input device for capture tests."""
import math, struct, threading
import pyaudiowpatch as pa

def start_tone():
    p = pa.PyAudio()
    wasapi = p.get_host_api_info_by_type(pa.paWASAPI)["index"]
    dev = next(d for d in (p.get_device_info_by_index(i) for i in range(p.get_device_count()))
               if d["hostApi"] == wasapi and d["name"].startswith("CABLE Input")
               and d["maxOutputChannels"] > 0 and not d.get("isLoopbackDevice"))
    stop = threading.Event()
    block = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / 44100))) * 2 for i in range(44100))
    def play():
        s = p.open(format=pa.paInt16, channels=2, rate=44100, output=True, output_device_index=dev["index"])
        while not stop.is_set():
            s.write(block[:4096 * 4]); block_rot = None
        s.close()
    threading.Thread(target=play, daemon=True).start()
    return stop

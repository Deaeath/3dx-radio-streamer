"""System audio ("what you hear") capture on Windows via WASAPI loopback (PyAudioWPatch).

No virtual cable needed: whatever plays on the chosen speakers/headphones is captured.
"""

import sys
import threading

try:
    import pyaudiowpatch as pyaudio
except ImportError:  # optional dependency / non-Windows
    pyaudio = None


def _com_init():
    """WASAPI needs COM on the calling thread; PortAudio only initializes it on the first thread."""
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)   # COINIT_MULTITHREADED; harmless if already done
    except (OSError, AttributeError):
        pass


def available():
    return pyaudio is not None and sys.platform == "win32"


def list_loopback_devices():
    """Names of output devices that can be captured. '' means the current default output."""
    if not available():
        return []
    p = pyaudio.PyAudio()
    try:
        return [d["name"] for d in p.get_loopback_device_info_generator()]
    except (OSError, LookupError):
        return []
    finally:
        p.terminate()


def _resolve(p, name):
    loopbacks = list(p.get_loopback_device_info_generator())
    if not loopbacks:
        raise OSError("no loopback-capable output device found")
    if name:
        for d in loopbacks:
            if d["name"] == name:
                return d
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    for d in loopbacks:
        if default["name"] in d["name"]:
            return d
    return loopbacks[0]


class LoopbackCapture:
    """Delivers raw s16le PCM at the device's native rate/channels to write(bytes)."""

    def __init__(self, name=""):
        if not available():
            raise OSError("system audio capture is not available on this computer")
        _com_init()
        self._p = pyaudio.PyAudio()
        try:
            self.device = _resolve(self._p, name)
        except Exception:
            self._p.terminate()
            raise
        self.rate = int(self.device["defaultSampleRate"])
        self.channels = max(1, min(2, int(self.device["maxInputChannels"]) or 2))
        self._stream = None
        self._lock = threading.Lock()

    @property
    def name(self):
        return self.device["name"]

    def start(self, write):
        def callback(in_data, frame_count, time_info, status):
            try:
                write(in_data)
            except (OSError, ValueError):
                return None, pyaudio.paComplete
            return None, pyaudio.paContinue

        self._stream = self._p.open(format=pyaudio.paInt16, channels=self.channels, rate=self.rate,
                                    input=True, input_device_index=self.device["index"],
                                    frames_per_buffer=int(self.rate * 0.02), stream_callback=callback)
        self._stream.start_stream()

    def stop(self):
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except OSError:
                    pass
                self._stream = None
            if self._p is not None:
                self._p.terminate()
                self._p = None

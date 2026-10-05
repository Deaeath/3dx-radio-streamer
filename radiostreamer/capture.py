"""System audio ("what you hear") capture on Windows via WASAPI loopback (PyAudioWPatch),
and single-app capture via WASAPI process loopback (Windows 10 2004+, plain ctypes).

No virtual cable needed: whatever plays on the chosen speakers/headphones is captured, or only
the sound of one app (and its child processes) with everything else left off air.
"""

import ctypes
import sys
import threading
import time
import uuid
from ctypes import POINTER, Structure, byref, c_int, c_long, c_longlong, c_ubyte, c_uint32, c_ulong
from ctypes import c_ushort, c_void_p, c_wchar

FUNCTYPE = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)   # COM is stdcall; WINFUNCTYPE is Windows-only

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


# --------------------------------------------------------------------------- #
# One app only: WASAPI process loopback (Windows 10 2004+)
# --------------------------------------------------------------------------- #

APP_CAPTURE_MIN_BUILD = 19041      # Windows 10 version 2004

# Players often sit in the tray with no visible window, so list them whenever they run
MEDIA_APPS = {"spotify.exe", "vlc.exe", "foobar2000.exe", "winamp.exe", "musicbee.exe", "aimp.exe",
              "itunes.exe", "applemusic.exe", "tidal.exe", "deezer.exe", "amazon music.exe", "mixxx.exe",
              "virtualdj.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe",
              "vivaldi.exe"}
# Windowed parts of Windows itself, and this app (airing itself would feed back) - never worth airing
_NOT_APPS = {"explorer.exe", "applicationframehost.exe", "textinputhost.exe", "systemsettings.exe",
             "shellexperiencehost.exe", "startmenuexperiencehost.exe", "searchhost.exe", "lockapp.exe",
             "widgets.exe", "taskmgr.exe", "3dx radio streamer.exe"}

_IID_IUNKNOWN = "00000000-0000-0000-C000-000000000046"
_IID_IAGILEOBJECT = "94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90"
_IID_COMPLETION_HANDLER = "41D949AB-9862-444A-80F6-C261334DA5EB"
_IID_IAUDIOCLIENT = "1CB9AD4C-DBFA-4C32-B178-C2F568A703B2"
_IID_IAUDIOCAPTURECLIENT = "C8ADBD64-E71E-48A0-A4DE-185C395CD317"
_E_NOINTERFACE = 0x80004002 - (1 << 32)
_STREAMFLAGS = (0x00020000      # AUDCLNT_STREAMFLAGS_LOOPBACK
                | 0x00040000    # AUDCLNT_STREAMFLAGS_EVENTCALLBACK
                | 0x08000000    # AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY
                | 0x80000000)   # AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM


def app_capture_available():
    return sys.platform == "win32" and sys.getwindowsversion().build >= APP_CAPTURE_MIN_BUILD


class _GUID(Structure):
    _fields_ = [("Data1", c_ulong), ("Data2", c_ushort), ("Data3", c_ushort), ("Data4", c_ubyte * 8)]


def _guid(text):
    g = _GUID()
    ctypes.memmove(byref(g), uuid.UUID(text).bytes_le, 16)
    return g


class _ProcessEntry(Structure):            # PROCESSENTRY32W
    _fields_ = [("dwSize", c_ulong), ("cntUsage", c_ulong), ("th32ProcessID", c_ulong),
                ("th32DefaultHeapID", c_void_p), ("th32ModuleID", c_ulong), ("cntThreads", c_ulong),
                ("th32ParentProcessID", c_ulong), ("pcPriClassBase", c_long), ("dwFlags", c_ulong),
                ("szExeFile", c_wchar * 260)]


class _ActivationParams(Structure):        # AUDIOCLIENT_ACTIVATION_PARAMS, process-loopback variant
    _fields_ = [("ActivationType", c_int), ("TargetProcessId", c_ulong), ("ProcessLoopbackMode", c_int)]


class _Blob(Structure):
    _fields_ = [("cbSize", c_ulong), ("pBlobData", c_void_p)]


class _PropVariant(Structure):             # PROPVARIANT holding a VT_BLOB
    _fields_ = [("vt", c_ushort), ("wReserved1", c_ushort), ("wReserved2", c_ushort),
                ("wReserved3", c_ushort), ("blob", _Blob)]


class _WaveFormatEx(Structure):
    _pack_ = 1
    _fields_ = [("wFormatTag", c_ushort), ("nChannels", c_ushort), ("nSamplesPerSec", c_ulong),
                ("nAvgBytesPerSec", c_ulong), ("nBlockAlign", c_ushort), ("wBitsPerSample", c_ushort),
                ("cbSize", c_ushort)]


_libs = {}


def _lib(name):
    """Private WinDLL instances, so these signatures never clash with other ctypes users."""
    if name not in _libs:
        lib = ctypes.WinDLL(name)
        if name == "kernel32":
            sigs = (("CreateToolhelp32Snapshot", c_void_p, [c_ulong, c_ulong]),
                    ("Process32FirstW", c_int, [c_void_p, POINTER(_ProcessEntry)]),
                    ("Process32NextW", c_int, [c_void_p, POINTER(_ProcessEntry)]),
                    ("CreateEventW", c_void_p, [c_void_p, c_int, c_int, c_void_p]),
                    ("OpenProcess", c_void_p, [c_ulong, c_int, c_ulong]),
                    ("WaitForSingleObject", c_ulong, [c_void_p, c_ulong]),
                    ("CloseHandle", c_int, [c_void_p]),
                    ("GetCurrentProcessId", c_ulong, []))
        elif name == "user32":
            sigs = (("IsWindowVisible", c_int, [c_void_p]),
                    ("GetWindow", c_void_p, [c_void_p, c_uint32]),
                    ("GetWindowTextLengthW", c_int, [c_void_p]),
                    ("GetWindowThreadProcessId", c_ulong, [c_void_p, POINTER(c_ulong)]),
                    ("GetWindowLongW", c_long, [c_void_p, c_int]),
                    ("EnumWindows", c_int, [c_void_p, c_void_p]))
        elif name == "dwmapi":
            sigs = (("DwmGetWindowAttribute", c_long, [c_void_p, c_ulong, c_void_p, c_ulong]),)
        else:
            sigs = (("ActivateAudioInterfaceAsync", c_long,
                     [ctypes.c_wchar_p, POINTER(_GUID), POINTER(_PropVariant), c_void_p, POINTER(c_void_p)]),)
        for fn, res, args in sigs:
            getattr(lib, fn).restype, getattr(lib, fn).argtypes = res, args
        _libs[name] = lib
    return _libs[name]


def _processes():
    """[(pid, parent pid, exe name)] for every running process."""
    k32 = _lib("kernel32")
    snap = k32.CreateToolhelp32Snapshot(2, 0)          # TH32CS_SNAPPROCESS
    if not snap or snap == c_void_p(-1).value:
        return []
    out = []
    entry = _ProcessEntry()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        ok = k32.Process32FirstW(snap, byref(entry))
        while ok:
            out.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
            ok = k32.Process32NextW(snap, byref(entry))
    finally:
        k32.CloseHandle(snap)
    return out


def find_app(exe_name):
    """PID of the top-most running process called exe_name (its child processes are captured too)."""
    want = exe_name.strip().lower()
    match = {pid: ppid for pid, ppid, exe in _processes() if exe.lower() == want}
    roots = [pid for pid, ppid in match.items() if ppid not in match]
    return roots[0] if roots else None


def list_apps():
    """Exe names of running apps that could be captured: anything with a window, plus known players."""
    if not app_capture_available():
        return []
    user32, dwm = _lib("user32"), _lib("dwmapi")
    windowed = set()

    def in_alt_tab(hwnd):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4) or not user32.GetWindowTextLengthW(hwnd):
            return False                                        # hidden, owned (a dialog) or untitled
        if user32.GetWindowLongW(hwnd, -20) & 0x80:              # WS_EX_TOOLWINDOW: overlays, tray helpers
            return False
        cloaked = c_int()
        dwm.DwmGetWindowAttribute(hwnd, 14, byref(cloaked), ctypes.sizeof(cloaked))   # DWMWA_CLOAKED
        return not cloaked.value

    def on_window(hwnd, _):
        if in_alt_tab(hwnd):
            pid = c_ulong()
            user32.GetWindowThreadProcessId(hwnd, byref(pid))
            windowed.add(pid.value)
        return 1

    callback = FUNCTYPE(c_int, c_void_p, c_void_p)(on_window)
    user32.EnumWindows(ctypes.cast(callback, c_void_p), None)
    own = _lib("kernel32").GetCurrentProcessId()
    names = {}
    for pid, _, exe in _processes():
        low = exe.lower()
        if pid != own and low not in _NOT_APPS and (pid in windowed or low in MEDIA_APPS):
            names.setdefault(low, exe)
    return sorted(names.values(), key=str.lower)


def _method(obj, index, *argtypes):
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    return FUNCTYPE(c_long, c_void_p, *argtypes)(vtbl[index])


def _call(obj, index, argtypes, *args, what):
    hr = _method(obj, index, *argtypes)(obj, *args)
    if hr < 0:
        raise OSError(f"{what} failed (0x{hr & 0xFFFFFFFF:08X})")
    return hr


def _release(obj):
    if obj:
        _method(obj, 2)(obj)


_QI = FUNCTYPE(c_long, c_void_p, POINTER(_GUID), POINTER(c_void_p))
_REF = FUNCTYPE(c_ulong, c_void_p)
_DONE = FUNCTYPE(c_long, c_void_p, c_void_p)


class _HandlerVtbl(Structure):
    _fields_ = [("QueryInterface", _QI), ("AddRef", _REF), ("Release", _REF), ("ActivateCompleted", _DONE)]


class _HandlerObject(Structure):
    _fields_ = [("lpVtbl", POINTER(_HandlerVtbl))]


class _CompletionHandler:
    """A minimal agile IActivateAudioInterfaceCompletionHandler. Its owner keeps it alive."""

    def __init__(self):
        self.done = threading.Event()
        iids = {bytes(_guid(i)) for i in (_IID_IUNKNOWN, _IID_IAGILEOBJECT, _IID_COMPLETION_HANDLER)}

        def query(this, riid, ppv):
            if bytes(riid.contents) in iids:
                ppv[0] = this
                return 0
            ppv[0] = None
            return _E_NOINTERFACE

        def completed(this, operation):
            self.done.set()
            return 0

        self._fns = (_QI(query), _REF(lambda this: 1), _REF(lambda this: 1), _DONE(completed))
        self._vtbl = _HandlerVtbl(*self._fns)
        self.obj = _HandlerObject(ctypes.pointer(self._vtbl))


class _SinkClosed(Exception):
    """The consumer (ffmpeg's stdin) went away."""


class _LoopbackSession:
    """One activated process-loopback IAudioClient for one PID."""

    def __init__(self, pid, rate, channels):
        self.client = self.capture = self.event = self.process = None
        self.block = channels * 2
        try:
            self._activate(pid)
            fmt = _WaveFormatEx(1, channels, rate, rate * self.block, self.block, 16, 0)   # 16-bit PCM
            _call(self.client, 3, (c_int, c_ulong, c_longlong, c_longlong, POINTER(_WaveFormatEx), c_void_p),
                  0, _STREAMFLAGS, 2_000_000, 0, byref(fmt), None, what="Initialize")
            k32 = _lib("kernel32")
            self.event = k32.CreateEventW(None, 0, 0, None)
            _call(self.client, 13, (c_void_p,), self.event, what="SetEventHandle")
            cap = c_void_p()
            _call(self.client, 14, (POINTER(_GUID), POINTER(c_void_p)), byref(_guid(_IID_IAUDIOCAPTURECLIENT)),
                  byref(cap), what="GetService")
            self.capture = cap.value
            self.process = k32.OpenProcess(0x00100000, 0, pid)            # SYNCHRONIZE, to notice it quit
            _call(self.client, 10, (), what="Start")
        except Exception:
            self.close()
            raise

    def _activate(self, pid):
        params = _ActivationParams(1, pid, 0)       # PROCESS_LOOPBACK, INCLUDE_TARGET_PROCESS_TREE
        prop = _PropVariant()
        prop.vt = 65                                # VT_BLOB
        prop.blob.cbSize = ctypes.sizeof(params)
        prop.blob.pBlobData = ctypes.addressof(params)
        handler = _CompletionHandler()
        self._handler = handler                     # Windows may still hold it; keep the vtable alive
        op = c_void_p()
        hr = _lib("mmdevapi").ActivateAudioInterfaceAsync("VAD\\Process_Loopback", byref(_guid(_IID_IAUDIOCLIENT)),
                                                          byref(prop), ctypes.addressof(handler.obj), byref(op))
        if hr < 0:
            raise OSError(f"app capture request failed (0x{hr & 0xFFFFFFFF:08X})")
        try:
            if not handler.done.wait(5):
                raise OSError("Windows did not answer the app capture request")
            result, unknown = c_long(), c_void_p()
            _call(op.value, 3, (POINTER(c_long), POINTER(c_void_p)), byref(result), byref(unknown),
                  what="GetActivateResult")
            if result.value < 0:
                raise OSError(f"app capture was refused (0x{result.value & 0xFFFFFFFF:08X})")
            client = c_void_p()
            try:
                _call(unknown.value, 0, (POINTER(_GUID), POINTER(c_void_p)), byref(_guid(_IID_IAUDIOCLIENT)),
                      byref(client), what="QueryInterface")
            finally:
                _release(unknown.value)
            self.client = client.value
        finally:
            _release(op.value)

    def app_exited(self):
        return bool(self.process) and _lib("kernel32").WaitForSingleObject(self.process, 0) == 0

    def pump(self, write, stop):
        """Copy captured audio to write() until stop is set (True) or the app quits (False)."""
        k32 = _lib("kernel32")
        size, data = c_uint32(), c_void_p()
        frames, flags = c_uint32(), c_ulong()
        while not stop.is_set():
            if self.app_exited():
                return False
            k32.WaitForSingleObject(self.event, 100)
            while True:
                _call(self.capture, 5, (POINTER(c_uint32),), byref(size), what="GetNextPacketSize")
                if not size.value:
                    break
                _call(self.capture, 3, (POINTER(c_void_p), POINTER(c_uint32), POINTER(c_ulong), c_void_p, c_void_p),
                      byref(data), byref(frames), byref(flags), None, None, what="GetBuffer")
                n = frames.value * self.block
                silent = flags.value & 0x2 or not data.value                       # AUDCLNT_BUFFERFLAGS_SILENT
                chunk = bytes(n) if silent else ctypes.string_at(data.value, n)
                _call(self.capture, 4, (c_uint32,), frames.value, what="ReleaseBuffer")
                try:
                    write(chunk)
                except (OSError, ValueError) as e:
                    raise _SinkClosed() from e
        return True

    def close(self):
        if self.client:
            try:
                _method(self.client, 11)(self.client)        # Stop
            except OSError:
                pass
        _release(self.capture)
        _release(self.client)
        self.capture = self.client = None
        k32 = _lib("kernel32")
        for h in (self.event, self.process):
            if h:
                k32.CloseHandle(h)
        self.event = self.process = None


class AppCapture:
    """Delivers raw s16le PCM of one app's sound (and its child processes') to write(bytes).

    The app must be running when capture starts. If it quits mid-broadcast, capture waits and
    picks it up again when it restarts; listeners hear silence meanwhile.
    """

    rate = 48000
    channels = 2

    def __init__(self, exe_name):
        if not app_capture_available():
            raise OSError("capturing one app needs Windows 10 version 2004 or newer")
        self.exe = (exe_name or "").strip()
        if not self.exe:
            raise OSError("no app selected")
        _com_init()
        pid = find_app(self.exe)
        if pid is None:
            raise OSError(f"{self.exe} is not running - start it first")
        self._session = _LoopbackSession(pid, self.rate, self.channels)
        self._stop = threading.Event()
        self._thread = None

    @property
    def name(self):
        return self.exe

    def start(self, write):
        self._thread = threading.Thread(target=self._run, args=(write,), daemon=True)
        self._thread.start()

    def _run(self, write):
        _com_init()
        try:
            while not self._stop.is_set():
                if self._session is None:
                    pid = find_app(self.exe)
                    try:
                        self._session = _LoopbackSession(pid, self.rate, self.channels) if pid else None
                    except OSError:
                        self._session = None
                    if self._session is None:
                        self._stop.wait(2)
                        continue
                try:
                    if self._session.pump(write, self._stop):
                        break
                except OSError:                     # e.g. the output device changed - reconnect
                    time.sleep(1)
                self._session.close()
                self._session = None
        except _SinkClosed:
            pass
        finally:
            if self._session is not None:
                self._session.close()
                self._session = None

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2)
        elif self._session is not None:
            self._session.close()
            self._session = None

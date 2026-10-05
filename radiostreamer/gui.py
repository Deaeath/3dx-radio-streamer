"""Main window."""

import math
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, VERSION, capture, media, theme, tools
from .config import (BITRATES, CACHE_DIR, DATA_DIR, DEFAULTS, PROVIDERS, SAMPLERATES, SERVER_TYPES,
                     SETTINGS_FILE, SOURCES, TITLE_SOURCES, import_mixxx_profile, load_settings,
                     mixxx_profile_exists, save_settings)
from .engine import Broadcaster, Playlist
from .lastfm import CREATE_KEY_URL, LastFM, LastFMError, Scrobbler
from .protocol import StreamError, listener_url, open_source_connection, source_port, update_metadata

VB_CABLE_URL = "https://vb-audio.com/Cable/"
KIND_LABELS = {"file": "File", "stream": "Stream", "ytdl": "Online", "ytlive": "Live"}
MEDIA_FILETYPES = [("Media & playlists", " ".join("*" + e for e in sorted(media.MEDIA_EXTS | media.PLAYLIST_EXTS))),
                   ("All files", "*.*")]


class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()            # (kind, payload, source broadcaster or None)
        self.broadcaster = None
        self.scrobbler = None
        self.level = -120.0
        self.silent_since = None
        self.silence_warned = False
        self.last_bytes = (0, time.time())
        self.kbps = 0.0
        self.queue_version = -1
        self.saved_version = -1
        self.ffmpeg = tools.ffmpeg()

        first_run = not SETTINGS_FILE.exists()
        cfg = load_settings()
        self.playlist = Playlist(cfg["queue"], loop=cfg["loop"])
        self.saved_version = self.playlist.version

        self.vars = {}
        for key, default in DEFAULTS.items():
            if key == "queue":
                continue
            if isinstance(default, bool):
                self.vars[key] = tk.BooleanVar(value=bool(cfg[key]))
            else:
                self.vars[key] = tk.StringVar(value=str(cfg[key]))

        root.title(f"{APP_NAME} {VERSION}")
        root.geometry("940x880")
        root.minsize(820, 760)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        theme.dark_titlebar(root)

        self.logo = None
        icon = icon_path()
        if icon:
            try:
                self.logo = tk.PhotoImage(file=str(icon)).subsample(6)
            except tk.TclError:
                pass
        self.banner = theme.Banner(root, APP_NAME, f"Your own internet radio station  ·  v{VERSION}",
                                   self.logo, self._build_menu())
        self.banner.pack(fill="x")
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=0, pady=(0, 0))
        self._build_broadcast_tab()
        self._build_server_tab()
        self._build_integrations_tab()
        self._build_log_tab()
        self.statusbar = ttk.Label(root, anchor="w", style="Status.TLabel")
        self.statusbar.pack(fill="x")

        for key in ("server_type", "host", "port", "mount", "sid"):
            self.vars[key].trace_add("write", lambda *a: self.on_server_change())
        self.vars["provider"].trace_add("write", lambda *a: self.on_provider_change(apply=False))

        if not self.ffmpeg:
            self.log("ffmpeg was not found. Reinstall the app, or install ffmpeg and add it to PATH.")
        self.refresh_devices()
        self.on_source_change()
        self.on_server_change()
        self.on_provider_change(apply=False)
        self.refresh_lastfm_status()
        self.root.after(100, self.poll)
        if first_run or not cfg["wizard_done"]:
            self.root.after(300, self.open_wizard)

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _build_menu(self):
        """The File / Tools / Help menus, shown as links in the header banner."""
        f = tk.Menu(self.root, tearoff=False)
        f.add_command(label="Setup wizard...", command=self.open_wizard)
        f.add_command(label="Open settings folder", command=lambda: self.open_path(DATA_DIR))
        f.add_separator()
        f.add_command(label="Exit", command=self.on_close)
        t = tk.Menu(self.root, tearoff=False)
        t.add_command(label="Test server connection", command=self.test_connection)
        t.add_command(label="Import settings from Mixxx", command=self.import_mixxx)
        t.add_command(label="Update yt-dlp (fixes YouTube errors)", command=self.update_ytdlp)
        t.add_command(label="Clear download cache", command=self.clear_cache)
        h = tk.Menu(self.root, tearoff=False)
        h.add_command(label="Get VB-CABLE (virtual audio cable)", command=lambda: webbrowser.open(VB_CABLE_URL))
        h.add_command(label="Create a Last.fm API key", command=lambda: webbrowser.open(CREATE_KEY_URL))
        h.add_separator()
        h.add_command(label="About", command=self.about)
        for menu in (f, t, h):
            theme.style_menu(menu)
        return [("File", f), ("Tools", t), ("Help", h)]

    def _row(self, parent, r, label, widget, sticky="ew"):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=(0, 8), pady=3)
        widget.grid(row=r, column=1, sticky=sticky, pady=3)
        return widget

    def _build_broadcast_tab(self):
        v = self.vars
        tab = ttk.Frame(self.nb, padding=(16, 14))
        self.nb.add(tab, text="  Broadcast  ")
        tab.columnconfigure(0, weight=1)

        top = ttk.Frame(tab)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        self.go_btn = theme.PillButton(top, "GO LIVE", theme.GO_GRADIENT, self.toggle, width=190, height=60)
        self.go_btn.grid(row=0, column=0, rowspan=2, padx=(0, 20))
        self.status_lbl = tk.Label(top, text="OFF AIR", font=(theme.DISPLAY, 18, "bold"), fg=theme.FAINT,
                                   bg=theme.BG, anchor="w")
        self.status_lbl.grid(row=0, column=1, sticky="sew")
        self.stats_lbl = ttk.Label(top, text="Press GO LIVE when your music is ready.", style="Muted.TLabel",
                                   anchor="w")
        self.stats_lbl.grid(row=1, column=1, sticky="new", pady=(2, 0))

        meter = ttk.Frame(tab)
        meter.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        meter.columnconfigure(1, weight=1)
        ttk.Label(meter, text="LEVEL", style="Faint.TLabel", font=(theme.FONT, 8, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 12))
        self.meter = theme.LevelMeter(meter)
        self.meter.grid(row=0, column=1, sticky="ew")
        self.level_lbl = ttk.Label(meter, text="silent", width=11, anchor="e", style="Muted.TLabel")
        self.level_lbl.grid(row=0, column=2, padx=(10, 0))
        ttk.Label(meter, text="LISTEN", style="Faint.TLabel", font=(theme.FONT, 8, "bold")).grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=(12, 0))
        self.room_url = tk.StringVar()
        ttk.Entry(meter, textvariable=self.room_url, state="readonly", font=(theme.MONO, 10)).grid(
            row=1, column=1, sticky="ew", pady=(12, 0))
        ttk.Button(meter, text="Copy link", style="Accent.TButton", command=self.copy_room_url).grid(
            row=1, column=2, padx=(10, 0), pady=(12, 0), sticky="ew")

        src = ttk.LabelFrame(tab, text=" Audio source ", padding=(12, 8))
        src.grid(row=2, column=0, sticky="ew", pady=(10, 2))
        src.columnconfigure(1, weight=1)
        ttk.Radiobutton(src, text=SOURCES["queue"], value="queue", variable=v["source"],
                        command=self.on_source_change).grid(row=0, column=0, columnspan=3, sticky="w")
        self.loop_rb = ttk.Radiobutton(src, text=SOURCES["loopback"], value="loopback", variable=v["source"],
                                       command=self.on_source_change)
        self.loop_rb.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.loopback_cb = ttk.Combobox(src, textvariable=v["loopback_device"], state="readonly")
        self.loopback_cb.grid(row=1, column=1, sticky="ew", padx=6, pady=(4, 0))
        self.app_rb = ttk.Radiobutton(src, text=SOURCES["app"], value="app", variable=v["source"],
                                      command=self.on_source_change)
        self.app_rb.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.app_cb = ttk.Combobox(src, textvariable=v["app_name"])
        self.app_cb.grid(row=2, column=1, sticky="ew", padx=6, pady=(4, 0))
        ttk.Radiobutton(src, text=SOURCES["device"], value="device", variable=v["source"],
                        command=self.on_source_change).grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.device_cb = ttk.Combobox(src, textvariable=v["device"], state="readonly")
        self.device_cb.grid(row=3, column=1, sticky="ew", padx=6, pady=(4, 0))
        ttk.Button(src, text="Refresh", command=self.refresh_devices).grid(row=1, column=2, rowspan=3)
        if not capture.available():
            self.loop_rb.config(state="disabled", text=SOURCES["loopback"] + " - Windows only")
        if not capture.app_capture_available():
            self.app_rb.config(state="disabled", text=SOURCES["app"] + " - Windows 10 2004+")

        np_ = ttk.LabelFrame(tab, text=" Now playing (stream title) ", padding=(12, 8))
        np_.grid(row=3, column=0, sticky="ew", pady=4)
        np_.columnconfigure(0, weight=1)
        self.np_var = tk.StringVar()
        np_entry = ttk.Entry(np_, textvariable=self.np_var)
        np_entry.grid(row=0, column=0, sticky="ew")
        np_entry.bind("<Return>", lambda e: self.push_metadata())
        ttk.Button(np_, text="Update", command=self.push_metadata).grid(row=0, column=1, padx=(6, 0))
        opts = ttk.Frame(np_)
        opts.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Checkbutton(opts, text="Send titles automatically", variable=v["auto_metadata"]).pack(side="left")
        ttk.Label(opts, text="   Live source titles from:").pack(side="left")
        self.title_src_cb = ttk.Combobox(opts, textvariable=v["title_source"], values=TITLE_SOURCES,
                                         state="readonly", width=30)
        self.title_src_cb.pack(side="left", padx=4)

        qf = ttk.LabelFrame(tab, text=" Queue ", padding=(12, 8))
        qf.grid(row=4, column=0, sticky="nsew", pady=4)
        tab.rowconfigure(4, weight=1)
        qf.columnconfigure(0, weight=1)
        qf.rowconfigure(1, weight=1)
        bar = ttk.Frame(qf)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        # Loop is packed first so it keeps its place when the window is narrow
        ttk.Checkbutton(bar, text="Loop", variable=v["loop"],
                        command=lambda: setattr(self.playlist, "loop", self.vars["loop"].get())).pack(side="right")
        for text, cmd in (("+ Files", self.add_files), ("+ Folder", self.add_folder),
                          ("+ Links / search", self.add_links)):
            ttk.Button(bar, text=text, style="Tool.Accent.TButton" if text == "+ Links / search" else "Tool.TButton",
                       command=cmd).pack(side="left", padx=(0, 4))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        for text, cmd in (("Play next", self.play_next), ("Skip", self.skip), ("▲", lambda: self.move(-1)),
                          ("▼", lambda: self.move(1)), ("Shuffle", self.shuffle),
                          ("Remove", self.remove_selected), ("Clear", self.clear_queue)):
            ttk.Button(bar, text=text, style="Tool.TButton", command=cmd).pack(side="left", padx=(0, 4))

        self.tree = ttk.Treeview(qf, columns=("n", "title", "kind"), show="headings", selectmode="extended")
        self.tree.heading("n", text="#")
        self.tree.heading("title", text="Title")
        self.tree.heading("kind", text="Source")
        self.tree.column("n", width=46, stretch=False, anchor="e")
        self.tree.column("kind", width=80, stretch=False)
        self.tree.column("title", width=500)
        self.tree.tag_configure("odd", background=theme.mix(theme.SURFACE, "#ffffff", 0.025))
        self.tree.tag_configure("current", background=theme.mix(theme.PINK, theme.SURFACE, 0.78),
                                foreground=theme.lighten(theme.PINK, 0.55), font=(theme.FONT, 10, "bold"))
        self.tree.tag_configure("failed", foreground=theme.RED)
        self.tree.grid(row=1, column=0, sticky="nsew")
        sb = ttk.Scrollbar(qf, orient="vertical", command=self.tree.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", lambda e: self.play_now())
        self.tree.bind("<Delete>", lambda e: self.remove_selected())
        self.queue_info = ttk.Label(qf, style="Muted.TLabel")
        self.queue_info.grid(row=2, column=0, sticky="w", pady=(4, 0))

    def _build_server_tab(self):
        v = self.vars
        tab = ttk.Frame(self.nb, padding=(16, 14))
        self.nb.add(tab, text="  Server  ")
        tab.columnconfigure(0, weight=1)

        srv = ttk.LabelFrame(tab, text=" Stream server ", padding=(12, 8))
        srv.grid(row=0, column=0, sticky="ew")
        srv.columnconfigure(1, weight=1)
        cb = self._row(srv, 0, "Provider", ttk.Combobox(srv, textvariable=v["provider"], values=list(PROVIDERS),
                                                        state="readonly", width=30), sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self.on_provider_change(apply=True))
        self.provider_hint = ttk.Label(srv, style="Muted.TLabel", wraplength=640, justify="left")
        self.provider_hint.grid(row=1, column=1, sticky="w")
        self._row(srv, 2, "Server type", ttk.Combobox(srv, textvariable=v["server_type"], values=SERVER_TYPES,
                                                      state="readonly", width=16), sticky="w")
        self._row(srv, 3, "Host / IP", ttk.Entry(srv, textvariable=v["host"]))
        self._row(srv, 4, "Port", ttk.Entry(srv, textvariable=v["port"], width=8), sticky="w")
        pw = ttk.Frame(srv)
        pw.columnconfigure(0, weight=1)
        self.pw_entry = ttk.Entry(pw, textvariable=v["password"], show="•")
        self.pw_entry.grid(row=0, column=0, sticky="ew")
        self.show_pw = tk.BooleanVar(value=False)
        ttk.Checkbutton(pw, text="Show", variable=self.show_pw,
                        command=lambda: self.pw_entry.config(show="" if self.show_pw.get() else "•")
                        ).grid(row=0, column=1, padx=(6, 0))
        self._row(srv, 5, "Source password", pw)
        self.user_entry = self._row(srv, 6, "Username (Icecast)", ttk.Entry(srv, textvariable=v["username"]))
        self.mount_entry = self._row(srv, 7, "Mount (Icecast)", ttk.Entry(srv, textvariable=v["mount"]))
        self.sid_entry = self._row(srv, 8, "Stream ID (Shoutcast v2)",
                                   ttk.Entry(srv, textvariable=v["sid"], width=6), sticky="w")
        self.port_hint = ttk.Label(srv, style="Muted.TLabel")
        self.port_hint.grid(row=9, column=1, sticky="w")
        btns = ttk.Frame(srv)
        btns.grid(row=10, column=1, sticky="w", pady=(6, 0))
        ttk.Button(btns, text="Test connection", style="Accent.TButton", command=self.test_connection).pack(side="left")
        if mixxx_profile_exists():
            ttk.Button(btns, text="Import from Mixxx", command=self.import_mixxx).pack(side="left", padx=6)

        cards = ttk.Frame(tab)                    # Station and Audio quality side by side
        cards.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        cards.columnconfigure((0, 1), weight=1, uniform="cards")
        info = ttk.LabelFrame(cards, text=" Station ", padding=(12, 8))
        info.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        info.columnconfigure(1, weight=1)
        self._row(info, 0, "Station name", ttk.Entry(info, textvariable=v["name"]))
        self._row(info, 1, "Genre", ttk.Entry(info, textvariable=v["genre"]))
        self._row(info, 2, "Website", ttk.Entry(info, textvariable=v["url"]))
        self._row(info, 3, "Description", ttk.Entry(info, textvariable=v["description"]))
        self._row(info, 4, "", ttk.Checkbutton(info, text="List in the public station directory",
                                               variable=v["public"]), sticky="w")

        enc = ttk.LabelFrame(cards, text=" Audio quality & connection ", padding=(12, 8))
        enc.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        enc.columnconfigure(1, weight=1)
        self._row(enc, 0, "Bitrate (kbps)", ttk.Combobox(enc, textvariable=v["bitrate"], width=8, values=BITRATES,
                                                        state="readonly"), sticky="w")
        self._row(enc, 1, "Sample rate", ttk.Combobox(enc, textvariable=v["samplerate"], width=8,
                                                     values=SAMPLERATES, state="readonly"), sticky="w")
        self._row(enc, 2, "Channels", ttk.Combobox(enc, textvariable=v["channels"], width=8, values=[2, 1],
                                                  state="readonly"), sticky="w")
        self._row(enc, 3, "", ttk.Checkbutton(enc, text="Even out loudness between tracks",
                                              variable=v["normalize"]), sticky="w")
        self._row(enc, 4, "Reconnect delay (s)", ttk.Entry(enc, textvariable=v["reconnect_delay"], width=8),
                  sticky="w")
        self._row(enc, 5, "Max retries (0 = forever)", ttk.Entry(enc, textvariable=v["max_retries"], width=8),
                  sticky="w")

    def _build_integrations_tab(self):
        v = self.vars
        tab = ttk.Frame(self.nb, padding=(16, 14))
        self.nb.add(tab, text="  Integrations  ")
        tab.columnconfigure(0, weight=1)

        om = ttk.LabelFrame(tab, text=" YouTube, SoundCloud, Spotify & other links ", padding=(12, 8))
        om.grid(row=0, column=0, sticky="ew")
        om.columnconfigure(1, weight=1)
        self._row(om, 0, "Find songs & Spotify tracks on", ttk.Combobox(
            om, textvariable=v["match_service"], values=list(media.MATCH_SERVICES), state="readonly", width=14),
            sticky="w")
        self._row(om, 1, "YouTube sign-in (cookies from)", ttk.Combobox(
            om, textvariable=v["ytdlp_cookies_browser"], values=media.COOKIE_BROWSERS, state="readonly", width=14),
            sticky="w")
        ttk.Label(om, style="Muted.TLabel", wraplength=620, justify="left", text=(
            "If YouTube says 'confirm you're not a bot' (common on VPNs), pick the browser you're signed in to "
            "YouTube with. Firefox works best; close Chrome/Edge first if they're chosen. Spotify audio is "
            "DRM-protected, so Spotify links are matched track by track on the service above. To air your "
            "own Spotify app directly, use 'One app only' as the source.")).grid(row=2, column=1, sticky="w")
        tl = ttk.Frame(om)
        tl.grid(row=3, column=1, sticky="w", pady=(6, 0))
        self.ytdlp_lbl = ttk.Label(tl, text="yt-dlp: ...")
        self.ytdlp_lbl.pack(side="left")
        ttk.Button(tl, text="Update yt-dlp", command=self.update_ytdlp).pack(side="left", padx=8)
        self.ffmpeg_lbl = ttk.Label(om, style="Muted.TLabel")
        self.ffmpeg_lbl.grid(row=4, column=1, sticky="w")
        threading.Thread(target=self._load_tool_versions, daemon=True).start()

        lf = ttk.LabelFrame(tab, text=" Last.fm ", padding=(12, 8))
        lf.grid(row=1, column=0, sticky="ew", pady=8)
        lf.columnconfigure(1, weight=1)
        self._row(lf, 0, "API key", ttk.Entry(lf, textvariable=v["lastfm_api_key"]))
        self._row(lf, 1, "Shared secret", ttk.Entry(lf, textvariable=v["lastfm_api_secret"], show="•"))
        link = ttk.Label(lf, text="Get a free API key at last.fm/api/account/create", style="Link.TLabel",
                         cursor="hand2")
        link.grid(row=2, column=1, sticky="w")
        link.bind("<Button-1>", lambda e: webbrowser.open(CREATE_KEY_URL))
        acct = ttk.Frame(lf)
        acct.grid(row=3, column=1, sticky="w", pady=(6, 0))
        ttk.Button(acct, text="Connect Last.fm account...", command=self.lastfm_connect).pack(side="left")
        ttk.Button(acct, text="Disconnect", command=self.lastfm_disconnect).pack(side="left", padx=6)
        self.lastfm_status = ttk.Label(acct, style="Muted.TLabel")
        self.lastfm_status.pack(side="left", padx=6)
        self._row(lf, 4, "", ttk.Checkbutton(lf, text="Scrobble everything the station plays to my account",
                                             variable=v["lastfm_scrobble"]), sticky="w")
        self._row(lf, 5, "Follow user's now playing", ttk.Entry(lf, textvariable=v["lastfm_watch_user"], width=24),
                  sticky="w")
        ttk.Label(lf, style="Muted.TLabel", wraplength=620, justify="left", text=(
            "With 'Live source titles from: Last.fm user's now playing', the stream title follows whatever that "
            "Last.fm user is scrobbling - handy when you play music in another app that scrobbles.")
                  ).grid(row=6, column=1, sticky="w")

    def _build_log_tab(self):
        tab = ttk.Frame(self.nb, padding=(16, 14))
        self.nb.add(tab, text="  Log  ")
        self.log_box = tk.Text(tab, state="disabled", wrap="word")       # ttk scrollbar: the classic one can't be themed
        theme.style_text(self.log_box, mono=True)
        sb = ttk.Scrollbar(tab, orient="vertical", command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #
    def collect(self):
        cfg = {}
        for key, default in DEFAULTS.items():
            if key == "queue":
                cfg[key] = self.playlist.snapshot()[0]
                continue
            raw = self.vars[key].get()
            if isinstance(default, bool):
                cfg[key] = bool(raw)
            elif isinstance(default, int):
                try:
                    cfg[key] = int(str(raw).strip())
                except ValueError:
                    raise ValueError(f"'{key.replace('_', ' ')}' must be a number (got '{raw}')") from None
            else:
                cfg[key] = str(raw) if key in ("password", "lastfm_api_secret") else str(raw).strip()
        return cfg

    def save(self, quiet=True):
        try:
            save_settings(self.collect())
            self.saved_version = self.playlist.version
            return True
        except (ValueError, OSError) as e:
            if not quiet:
                messagebox.showerror(APP_NAME, f"Could not save settings: {e}")
            self.log(f"Could not save settings: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", time.strftime("%H:%M:%S  ") + msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        self.statusbar.config(text=msg if len(msg) < 160 else msg[:157] + "...")

    def post(self, kind, payload=None):
        self.events.put((kind, payload, None))

    def in_background(self, fn, *args):
        threading.Thread(target=fn, args=args, daemon=True).start()

    def open_path(self, path):
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])

    def about(self):
        messagebox.showinfo(APP_NAME, f"{APP_NAME} {VERSION}\n\nBroadcast to Shoutcast / Icecast from files, "
                                      f"links, YouTube, SoundCloud, Spotify playlists and live audio.\n\n"
                                      f"Uses FFmpeg (ffmpeg.org) and yt-dlp (github.com/yt-dlp/yt-dlp).\n"
                                      f"Settings: {SETTINGS_FILE}\n\nOnly broadcast music you have the rights "
                                      f"to stream.\n\nMIT License - github.com/Deaeath/3dx-radio-streamer")

    def _load_tool_versions(self):
        self.post("tools", (tools.tool_version(tools.ytdlp()), tools.tool_version(self.ffmpeg)))

    # ------------------------------------------------------------------ #
    # Server / source UI
    # ------------------------------------------------------------------ #
    def server_fields(self):
        return {k: self.vars[k].get() for k in ("server_type", "host", "port", "mount", "sid")}

    def on_server_change(self):
        stype = self.vars["server_type"].get()
        ice = stype == "Icecast 2"
        self.user_entry.config(state="normal" if ice else "disabled")
        self.mount_entry.config(state="normal" if ice else "disabled")
        self.sid_entry.config(state="normal" if stype == "Shoutcast v2" else "disabled")
        fields = self.server_fields()
        try:
            int(fields["port"])
        except ValueError:
            self.room_url.set("")
            self.port_hint.config(text="")
            return
        url = listener_url(fields)
        self.room_url.set(url)
        extra = "" if ice else f"   (source connects on port {source_port(fields)})"
        self.port_hint.config(text=f"Listener URL: {url}{extra}")

    def on_provider_change(self, apply):
        info = PROVIDERS.get(self.vars["provider"].get())
        if not info:
            return
        if apply:
            for k, val in info["fields"].items():
                self.vars[k].set(str(val))
        self.provider_hint.config(text=info["hint"])

    def on_source_change(self):
        src = self.vars["source"].get()
        self.device_cb.config(state="readonly" if src == "device" else "disabled")
        self.loopback_cb.config(state="readonly" if src == "loopback" else "disabled")
        self.app_cb.config(state="normal" if src == "app" else "disabled")
        self.title_src_cb.config(state="disabled" if src == "queue" else "readonly")

    def refresh_devices(self):
        devices = tools.list_input_devices(self.ffmpeg)
        self.device_cb.config(values=devices)
        cur = self.vars["device"].get()
        if devices and cur not in devices:
            cable = [d for d in devices if "CABLE Output" in d]
            self.vars["device"].set(cable[0] if cable else devices[0])
        loops = capture.list_loopback_devices()
        self.loopback_cb.config(values=["Default speakers"] + loops)
        if self.vars["loopback_device"].get() not in loops:
            self.vars["loopback_device"].set("Default speakers")
        apps = capture.list_apps()
        self.app_cb.config(values=apps)
        if not self.vars["app_name"].get():
            players = [a for a in apps if a.lower() == "spotify.exe"]
            if players:
                self.vars["app_name"].set(players[0])
        return devices, loops, apps

    def copy_room_url(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.room_url.get())
        self.log(f"Copied {self.room_url.get()} - share it so people can listen.")

    def import_mixxx(self):
        imported, msg = import_mixxx_profile()
        if imported:
            for k, val in imported.items():
                self.vars[k].set(val if isinstance(val, bool) else str(val))
            self.refresh_devices()
        self.log(msg)
        return imported

    def test_connection(self, callback=None):
        try:
            cfg = self.collect()
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        self.log(f"Testing login at {cfg['host']}:{cfg['port']} ({cfg['server_type']})...")

        def work():
            try:
                open_source_connection(cfg).close()
                ok, msg = True, "Connection OK - the server accepted the login."
            except StreamError as e:
                ok, msg = False, f"Connection failed: {e}"
            self.post("log", msg)
            if callback:
                self.post("call", lambda: callback(ok, msg))
        self.in_background(work)

    # ------------------------------------------------------------------ #
    # Queue
    # ------------------------------------------------------------------ #
    def _expand_async(self, inputs, what):
        cfg = {"match_service": self.vars["match_service"].get(),
               "ytdlp_cookies_browser": self.vars["ytdlp_cookies_browser"].get()}
        self.log(f"Adding {what}...")

        def work():
            media.configure(cfg)
            items = media.expand(inputs, log=lambda m: self.post("log", m))
            self.post("add_items", items)
        self.in_background(work)

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Add media files", filetypes=MEDIA_FILETYPES)
        if paths:
            self._expand_async(list(paths), f"{len(paths)} file(s)")

    def add_folder(self):
        path = filedialog.askdirectory(title="Add a music folder")
        if path:
            self._expand_async([path], "folder")

    def add_links(self):
        LinkDialog(self.root, lambda lines: self._expand_async(lines, f"{len(lines)} link(s)"))

    def selected_indices(self):
        return sorted(int(i) for i in self.tree.selection())

    def remove_selected(self):
        self.playlist.remove(self.selected_indices())

    def move(self, delta):
        sel = self.selected_indices()
        if len(sel) == 1:
            j = self.playlist.move(sel[0], delta)
            self.refresh_queue(force=True)
            self.tree.selection_set(str(j))
            self.tree.see(str(j))

    def shuffle(self):
        self.playlist.shuffle_upcoming()

    def clear_queue(self):
        if self.playlist.items and messagebox.askyesno(APP_NAME, "Remove everything from the queue?"):
            self.playlist.clear()

    def play_next(self):
        sel = self.selected_indices()
        if sel:
            self.playlist.set_next(sel[0])
            self.log("Will play next: " + self.playlist.items[sel[0]]["title"])

    def play_now(self):
        sel = self.selected_indices()
        if sel:
            self.playlist.set_next(sel[0])
            if self.broadcaster and self.vars["source"].get() == "queue":
                self.log("Loading " + self.playlist.items[sel[0]]["title"] + "...")
                self.root.after(300, self._skip_when_ready, self.playlist.items[sel[0]], 0)

    def _skip_when_ready(self, it, tries):
        b = self.broadcaster
        if not b:
            return
        nxt = b.next_src
        if (nxt is not None and nxt.item is it) or tries > 120:
            b.skip()
        else:
            self.root.after(250, self._skip_when_ready, it, tries + 1)

    def skip(self):
        if self.broadcaster:
            self.broadcaster.skip()

    def refresh_queue(self, force=False):
        if not force and self.playlist.version == self.queue_version:
            return
        self.queue_version = self.playlist.version
        items, cursor = self.playlist.snapshot()
        sel = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        current_idx = None
        for i, it in enumerate(items):
            tags = ("odd",) if i % 2 else ()
            mark = ""
            if it is cursor and self.broadcaster:
                tags, mark, current_idx = ("current",), "▶ ", i
            elif self.playlist.is_failed(it):
                tags, mark = ("failed",), "✖ "
            self.tree.insert("", "end", iid=str(i), values=(i + 1, mark + it.get("title", it["src"]),
                                                            KIND_LABELS.get(it["kind"], it["kind"])), tags=tags)
        keep = [s for s in sel if self.tree.exists(s)]
        if keep:
            self.tree.selection_set(keep)
        if current_idx is not None:
            self.tree.see(str(current_idx))
        online = sum(1 for it in items if it["kind"] in ("ytdl", "ytlive"))
        self.queue_info.config(text=f"{len(items)} items" + (f" ({online} online - downloaded just before they play)"
                                                             if online else "") +
                               "   |   Double-click: play now   Del: remove")

    # ------------------------------------------------------------------ #
    # Broadcasting
    # ------------------------------------------------------------------ #
    def toggle(self):
        if self.broadcaster:
            self.stop()
        else:
            self.start()

    def start(self):
        try:
            cfg = self.collect()
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        if not cfg["host"] or not cfg["password"]:
            messagebox.showwarning(APP_NAME, "Enter your server's host and source password first "
                                             "(Server tab, or File > Setup wizard).")
            self.nb.select(1)
            return
        if cfg["loopback_device"] == "Default speakers":
            cfg["loopback_device"] = ""
        if cfg["source"] == "app" and not cfg["app_name"].strip():
            messagebox.showwarning(APP_NAME, "Pick the app to air (start it first, then press Refresh).")
            return
        if cfg["source"] == "queue" and not self.playlist.items:
            if not messagebox.askyesno(APP_NAME, "The queue is empty. Go live anyway (silence until you add "
                                                 "tracks)?"):
                return
        self.save()
        self.playlist.loop = cfg["loop"]
        b = Broadcaster(cfg, self.playlist, None)
        b.emit = lambda kind, payload=None: self.events.put((kind, payload, b))
        try:
            b.start()
        except StreamError as e:
            messagebox.showerror(APP_NAME, str(e))
            return
        self.broadcaster = b
        self.scrobbler = None
        if cfg["lastfm_scrobble"] and cfg["lastfm_session"]:
            self.scrobbler = Scrobbler(LastFM(cfg["lastfm_api_key"], cfg["lastfm_api_secret"],
                                              cfg["lastfm_session"]), lambda m: self.post("log", m))
        self.silent_since, self.silence_warned = None, False
        self.last_bytes, self.kbps = (0, time.time()), 0.0
        self.go_btn.configure_button("STOP", theme.STOP_GRADIENT)
        self.log(f"Starting broadcast ({SOURCES[cfg['source']]})")

    def stop(self, reason="Broadcast stopped."):
        if self.broadcaster:
            self.broadcaster.stop()
            self.broadcaster = None
            self.log(reason)
        if self.scrobbler:
            s = self.scrobbler
            self.in_background(s.title_changed, None)
            self.scrobbler = None
        self.go_btn.configure_button("GO LIVE", theme.GO_GRADIENT)
        self.set_status("off", "OFF AIR")
        self.stats_lbl.config(text="Press GO LIVE when your music is ready.")
        self.level = -120.0
        self.refresh_queue(force=True)

    def set_status(self, state, text):
        colors = {"live": theme.RED, "connecting": theme.AMBER, "error": theme.AMBER, "off": theme.FAINT}
        self.status_state = state
        self.status_lbl.config(text=("● " if state == "live" else "") + text, fg=colors.get(state, theme.FAINT))

    def push_metadata(self, title=None):
        title = (title if title is not None else self.np_var.get()).strip()
        b = self.broadcaster
        if not title or not (b and b.live):
            return
        cfg = b.cfg
        self.in_background(lambda: self.post("log", update_metadata(cfg, title)))

    def on_track(self, title):
        self.np_var.set(title)
        if title:
            self.log(f"Now playing: {title}")
            if self.vars["auto_metadata"].get():
                self.push_metadata(title)
        if self.scrobbler:
            self.in_background(self.scrobbler.title_changed, title or None)

    # ------------------------------------------------------------------ #
    # Tools / Last.fm
    # ------------------------------------------------------------------ #
    def update_ytdlp(self):
        self.log("Updating yt-dlp...")

        def work():
            try:
                msg = tools.update_ytdlp(lambda m: self.post("log", m))
            except Exception as e:
                msg = f"yt-dlp update failed: {e}"
            self.post("log", f"yt-dlp: {msg}")
            self._load_tool_versions()
        self.in_background(work)

    def clear_cache(self):
        import shutil
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
        self.log("Download cache cleared.")

    def refresh_lastfm_status(self):
        user = self.vars["lastfm_user"].get()
        self.lastfm_status.config(text=f"Connected as {user}" if self.vars["lastfm_session"].get() and user
                                  else "Not connected")

    def lastfm_connect(self):
        client = LastFM(self.vars["lastfm_api_key"].get(), self.vars["lastfm_api_secret"].get())
        if not client.key or not client.secret:
            messagebox.showinfo(APP_NAME, "Enter your Last.fm API key and shared secret first.\n\n"
                                          "Create them for free at last.fm/api/account/create (any app name, "
                                          "leave the callback URL empty).")
            webbrowser.open(CREATE_KEY_URL)
            return
        try:
            token = client.get_token()
        except LastFMError as e:
            messagebox.showerror(APP_NAME, f"Last.fm: {e}")
            return
        webbrowser.open(client.auth_url(token))
        if not messagebox.askokcancel(APP_NAME, "Your browser opened Last.fm.\n\nClick 'Yes, allow access' there, "
                                                "then press OK here."):
            return
        try:
            sk, name = client.get_session(token)
        except LastFMError as e:
            messagebox.showerror(APP_NAME, f"Last.fm did not confirm access: {e}")
            return
        self.vars["lastfm_session"].set(sk)
        self.vars["lastfm_user"].set(name)
        if not self.vars["lastfm_watch_user"].get():
            self.vars["lastfm_watch_user"].set(name)
        self.refresh_lastfm_status()
        self.save()
        self.log(f"Last.fm connected as {name}")

    def lastfm_disconnect(self):
        self.vars["lastfm_session"].set("")
        self.vars["lastfm_user"].set("")
        self.vars["lastfm_scrobble"].set(False)
        self.refresh_lastfm_status()
        self.save()

    def open_wizard(self):
        from .wizard import SetupWizard
        SetupWizard(self)

    def on_close(self):
        self.save()
        if self.broadcaster:
            self.broadcaster.stop()
        self.root.destroy()

    # ------------------------------------------------------------------ #
    # Event pump
    # ------------------------------------------------------------------ #
    def poll(self):
        try:
            while True:
                kind, payload, src = self.events.get_nowait()
                if src is not None and src is not self.broadcaster:
                    if kind == "log":
                        self.log(payload)
                    continue                      # late event from a stopped broadcast
                if kind == "log":
                    self.log(payload)
                elif kind == "status":
                    self.set_status(*payload)
                elif kind == "level":
                    self.level = payload
                elif kind == "track":
                    self.on_track(payload)
                elif kind == "queue":
                    self.refresh_queue(force=True)
                elif kind == "connected":
                    if self.np_var.get():
                        self.push_metadata()
                elif kind == "fatal":
                    self.log(payload)
                    self.stop("Broadcast stopped.")
                    self.set_status("error", "OFF AIR - " + payload[:80])
                elif kind == "add_items":
                    if payload:
                        self.playlist.add(payload)
                        self.log(f"Queue: +{len(payload)} item(s)")
                elif kind == "tools":
                    self.ytdlp_lbl.config(text=f"yt-dlp: {payload[0]}")
                    self.ffmpeg_lbl.config(text=f"ffmpeg: {payload[1]}")
                elif kind == "call":
                    payload()
        except queue.Empty:
            pass
        self.refresh_queue()
        if self.playlist.version != self.saved_version and not self.broadcaster:
            self.save()
        self.update_meter()
        self.update_stats()
        self.root.after(100, self.poll)

    def update_meter(self):
        lvl = self.level
        self.meter.draw(min(1.0, max(0.0, (lvl + 60) / 60)))
        if getattr(self, "status_state", "") == "live":           # a slow on-air pulse
            pulse = (math.sin(time.time() * 3.2) + 1) / 2
            self.status_lbl.config(fg=theme.mix(theme.RED, theme.PINK, pulse * 0.7))
        self.level_lbl.config(text="silent" if lvl <= -70 else f"{lvl:.1f} LUFS")
        b = self.broadcaster
        if b and b.live and b.cfg["source"] != "queue":
            if lvl <= -70:
                self.silent_since = self.silent_since or time.time()
                if not self.silence_warned and time.time() - self.silent_since > 15:
                    self.silence_warned = True
                    self.log("Warning: no audio for 15s - listeners hear silence. Is music playing on the "
                             "selected source?")
            else:
                self.silent_since, self.silence_warned = None, False

    def update_stats(self):
        b = self.broadcaster
        if not (b and b.connected_since):
            return
        now = time.time()
        last_b, last_t = self.last_bytes
        if now - last_t >= 1:
            self.kbps = (b.bytes_sent - last_b) * 8 / 1000 / (now - last_t)
            self.last_bytes = (b.bytes_sent, now)
        up = int(now - b.connected_since)
        self.stats_lbl.config(text=f"On air {up // 3600:d}:{up // 60 % 60:02d}:{up % 60:02d}   "
                                   f"Sent {b.bytes_sent / 1e6:.1f} MB   {self.kbps:.0f} kbps")


def icon_path():
    return next((d.parent / "assets" / "icon.png" for d in tools.bundle_dirs()
                 if (d.parent / "assets" / "icon.png").is_file()), None)


class LinkDialog(tk.Toplevel):
    def __init__(self, parent, on_add):
        super().__init__(parent)
        self.on_add = on_add
        self.title("Add links / search")
        self.geometry("680x460")
        self.configure(bg=theme.BG)
        self.transient(parent)
        theme.dark_titlebar(self)
        frm = ttk.Frame(self, padding=(18, 14))
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, justify="left", wraplength=610, text=(
            "One per line. Supported:\n"
            "• YouTube videos & playlists, YouTube Music, SoundCloud, Bandcamp, Mixcloud, Vimeo, Twitch "
            "(and 1000+ sites via yt-dlp)\n"
            "• Spotify track / album / playlist links (each track is matched and played from YouTube or "
            "SoundCloud)\n"
            "• Internet radio & direct audio links (.mp3, .aac, .m3u, .pls, HLS)\n"
            "• A song name like 'Daft Punk - One More Time' (searched online)")).pack(anchor="w")
        self.text = tk.Text(frm, height=10, wrap="none")
        theme.style_text(self.text, mono=True)
        self.text.pack(fill="both", expand=True, pady=8)
        try:
            clip = self.clipboard_get()
            if clip.strip().startswith(("http://", "https://")):
                self.text.insert("1.0", clip.strip() + "\n")
        except tk.TclError:
            pass
        btns = ttk.Frame(frm)
        btns.pack(fill="x")
        ttk.Button(btns, text="Add to queue", style="Accent.TButton", command=self.add).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=6)
        self.text.focus_set()
        self.grab_set()

    def add(self):
        lines = [ln.strip() for ln in self.text.get("1.0", "end").splitlines() if ln.strip()]
        self.destroy()
        if lines:
            self.on_add(lines)


def run():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("3DXRadioStreamer")
        except (OSError, AttributeError):
            pass
    root = tk.Tk()
    theme.apply(root)
    icon = icon_path()
    if icon:
        try:
            root.iconphoto(True, tk.PhotoImage(file=str(icon)))
        except tk.TclError:
            pass
    App(root)
    root.mainloop()

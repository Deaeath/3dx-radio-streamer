"""First-run setup wizard. Edits the main window's variables directly."""

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import APP_NAME, capture, media, theme
from .config import BITRATES, PROVIDERS, TITLE_SOURCES, mixxx_profile_exists
from .gui import VB_CABLE_URL
from .lastfm import CREATE_KEY_URL
from .protocol import listener_url


class SetupWizard(tk.Toplevel):
    PAGES = ["welcome", "server", "source", "station", "extras", "done"]

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.v = app.vars
        self.title(f"{APP_NAME} - Setup")
        self.geometry("880x620")
        self.minsize(820, 580)
        self.configure(bg=theme.BG)
        self.transient(app.root)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        theme.dark_titlebar(self)
        self.test_ok = None

        self.sidebar = tk.Canvas(self, width=220, highlightthickness=0, bd=0, bg=theme.BG)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.bind("<Configure>", lambda e: self.draw_sidebar())
        main = ttk.Frame(self)
        main.pack(side="left", fill="both", expand=True)
        self.step_lbl = ttk.Label(main, style="Faint.TLabel", font=(theme.FONT, 9, "bold"), padding=(30, 26, 30, 0))
        self.step_lbl.pack(fill="x")
        self.header = ttk.Label(main, style="Heading.TLabel", padding=(30, 2, 30, 8))
        self.header.pack(fill="x")
        self.progress = ttk.Progressbar(main, style="Accent.Horizontal.TProgressbar", maximum=len(self.PAGES))
        self.progress.pack(fill="x", padx=30)
        self.body = ttk.Frame(main, padding=(30, 18))
        self.body.pack(fill="both", expand=True)
        ttk.Separator(main).pack(fill="x")
        nav = ttk.Frame(main, padding=(30, 14))
        nav.pack(fill="x")
        self.next_btn = ttk.Button(nav, text="Next  →", style="Accent.TButton", command=self.next)
        self.next_btn.pack(side="right")
        self.back_btn = ttk.Button(nav, text="←  Back", command=self.back)
        self.back_btn.pack(side="right", padx=8)
        ttk.Button(nav, text="Cancel", command=self.cancel).pack(side="left")

        self.go_live = tk.BooleanVar(value=False)
        self.page = 0
        self.show(0)
        self.grab_set()
        self.focus_set()

    # -- navigation --------------------------------------------------------- #
    def show(self, i):
        self.page = i
        for w in self.body.winfo_children():
            w.destroy()
        name = self.PAGES[i]
        getattr(self, f"page_{name}")()
        self.step_lbl.config(text=f"STEP {i + 1} OF {len(self.PAGES)}")
        self.progress.config(value=i + 1)
        self.back_btn.config(state="normal" if i > 0 else "disabled")
        self.next_btn.config(text="Finish  ✓" if name == "done" else "Next  →")
        self.draw_sidebar()

    STEP_NAMES = {"welcome": "Welcome", "server": "Your server", "source": "What to play",
                  "station": "Your station", "extras": "Extras", "done": "All set"}

    def draw_sidebar(self):
        c = self.sidebar
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10:
            return
        c.delete("all")
        theme.gradient_lines(c, w, h, theme.darken(theme.PINK, 0.1), theme.darken(theme.VIOLET, 0.35),
                             horizontal=False)
        logo = getattr(self.app, "logo", None)
        y = 34
        if logo is not None:
            c.create_image(24, y, image=logo, anchor="w")
        c.create_text(24 + (logo.width() + 10 if logo is not None else 0), y, text="Setup", anchor="w",
                      fill="white", font=(theme.DISPLAY, 16, "bold"))
        y = 104
        for i, name in enumerate(self.PAGES):
            done, cur = i < self.page, i == self.page
            r = 13
            if cur:
                c.create_oval(24, y - r, 24 + 2 * r, y + r, fill="white", outline="")
                c.create_text(24 + r, y, text=str(i + 1), fill=theme.PINK, font=(theme.FONT, 10, "bold"))
            elif done:
                c.create_oval(24, y - r, 24 + 2 * r, y + r, fill=theme.lighten(theme.VIOLET, 0.25), outline="")
                c.create_text(24 + r, y, text="✓", fill="white", font=(theme.FONT, 10, "bold"))
            else:
                c.create_oval(24, y - r, 24 + 2 * r, y + r, outline=theme.lighten(theme.VIOLET, 0.45), width=2)
                c.create_text(24 + r, y, text=str(i + 1), fill=theme.lighten(theme.VIOLET, 0.6),
                              font=(theme.FONT, 10, "bold"))
            if i < len(self.PAGES) - 1:
                c.create_line(24 + r, y + r + 4, 24 + r, y + 44 - r - 4, width=2,
                              fill=theme.lighten(theme.VIOLET, 0.5 if done else 0.2))
            c.create_text(64, y, text=self.STEP_NAMES[name], anchor="w",
                          fill="white" if (cur or done) else theme.lighten(theme.VIOLET, 0.55),
                          font=(theme.FONT, 11, "bold" if cur else "normal"))
            y += 44

    def next(self):
        name = self.PAGES[self.page]
        check = getattr(self, f"check_{name}", None)
        if check and not check():
            return
        if name == "done":
            self.finish()
        else:
            self.show(self.page + 1)

    def back(self):
        if self.page > 0:
            self.show(self.page - 1)

    def cancel(self):
        self.app.save()
        self.destroy()

    def finish(self):
        self.v["wizard_done"].set(True)
        self.app.save()
        self.app.refresh_lastfm_status()
        self.app.on_source_change()
        self.destroy()
        if self.go_live.get():
            self.app.start()

    # -- helpers ------------------------------------------------------------ #
    def text(self, parent, s, **kw):
        lbl = ttk.Label(parent, text=s, wraplength=560, justify="left", **kw)
        lbl.pack(anchor="w", pady=(0, 8))
        return lbl

    def form(self):
        f = ttk.Frame(self.body)
        f.pack(fill="x")
        f.columnconfigure(1, weight=1)
        return f

    def row(self, f, r, label, widget, sticky="ew"):
        ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=4)
        widget.grid(row=r, column=1, sticky=sticky, pady=4)
        return widget

    # -- pages -------------------------------------------------------------- #
    def page_welcome(self):
        self.header.config(text="Welcome")
        self.text(self.body, f"{APP_NAME} sends music to your internet radio server (Shoutcast or Icecast), "
                             "so anyone with your station link can listen - in a music app, a browser, or a game's radio.")
        self.text(self.body, "You can play:\n"
                             "  •  Music files and folders on this PC\n"
                             "  •  YouTube, SoundCloud, Bandcamp and other links\n"
                             "  •  Spotify tracks, albums and playlists (matched online)\n"
                             "  •  Internet radio streams\n"
                             "  •  Live: everything this PC plays, just one app (Spotify, a browser...), "
                             "or a mic / mixer")
        self.text(self.body, "This takes about two minutes. You'll need your stream server details "
                             "(host, port and source password) from your radio host's control panel.")
        signup = PROVIDERS["Listen2MyRadio"]["links"]["Sign up free"]
        box = ttk.Frame(self.body)
        box.pack(fill="x", pady=(0, 8))
        ttk.Label(box, text="No server yet? We recommend Listen2MyRadio - it's free.").pack(side="left")
        ttk.Button(box, text="Get a free server", style="Accent.TButton", command=lambda: webbrowser.open(signup)).pack(side="left", padx=8)
        if mixxx_profile_exists():
            box = ttk.LabelFrame(self.body, text="Mixxx detected", padding=10)
            box.pack(fill="x", pady=8)
            ttk.Button(box, text="Import from Mixxx", command=self._import_mixxx).pack(side="right", ipadx=6)
            ttk.Label(box, text="Copy the server settings from your Mixxx broadcast profile?").pack(side="left")

    def _import_mixxx(self):
        if self.app.import_mixxx():
            messagebox.showinfo(APP_NAME, "Imported. Check the details on the next page.", parent=self)
            self.show(1)

    def page_server(self):
        self.header.config(text="Your stream server")
        f = self.form()
        cb = self.row(f, 0, "Radio host", ttk.Combobox(f, textvariable=self.v["provider"], values=list(PROVIDERS),
                                                       state="readonly", width=32), sticky="w")
        hint = ttk.Label(f, style="Muted.TLabel", wraplength=470, justify="left")
        hint.grid(row=1, column=1, sticky="w")
        links = ttk.Frame(f)
        links.grid(row=2, column=1, sticky="w")

        def on_provider(apply):
            info = PROVIDERS.get(self.v["provider"].get(), {})
            if apply:
                for k, val in info.get("fields", {}).items():
                    self.v[k].set(str(val))
            hint.config(text=info.get("hint", ""))
            for w in links.winfo_children():
                w.destroy()
            for label, url in info.get("links", {}).items():
                ttk.Button(links, text=label, command=lambda u=url: webbrowser.open(u)).pack(side="left",
                                                                                         padx=(0, 6), pady=(4, 0))
            refresh_fields()
        cb.bind("<<ComboboxSelected>>", lambda e: on_provider(True))

        self.row(f, 3, "Host / IP", ttk.Entry(f, textvariable=self.v["host"]))
        self.row(f, 4, "Port", ttk.Entry(f, textvariable=self.v["port"], width=8), sticky="w")
        self.row(f, 5, "Source password", ttk.Entry(f, textvariable=self.v["password"], show="•"))
        user_l = ttk.Label(f, text="Username")
        user_e = ttk.Entry(f, textvariable=self.v["username"])
        mount_l = ttk.Label(f, text="Mount point")
        mount_e = ttk.Entry(f, textvariable=self.v["mount"])
        sid_l = ttk.Label(f, text="Stream ID")
        sid_e = ttk.Entry(f, textvariable=self.v["sid"], width=6)

        def refresh_fields():
            stype = self.v["server_type"].get()
            for w in (user_l, user_e, mount_l, mount_e, sid_l, sid_e):
                w.grid_remove()
            if stype == "Icecast 2":
                user_l.grid(row=6, column=0, sticky="w", pady=4)
                user_e.grid(row=6, column=1, sticky="ew", pady=4)
                mount_l.grid(row=7, column=0, sticky="w", pady=4)
                mount_e.grid(row=7, column=1, sticky="ew", pady=4)
            elif stype == "Shoutcast v2":
                sid_l.grid(row=6, column=0, sticky="w", pady=4)
                sid_e.grid(row=6, column=1, sticky="w", pady=4)

        test = ttk.Frame(self.body)
        test.pack(fill="x", pady=(14, 0))
        self.test_lbl = tk.Label(test, text="", anchor="w", justify="left", wraplength=420, bg=theme.BG)
        ttk.Button(test, text="Test connection", style="Accent.TButton", command=self._test).pack(side="left")
        self.test_lbl.pack(side="left", padx=10, fill="x")
        self.text(self.body, "\nThe test logs in to your server and disconnects right away - nothing goes on "
                             "air yet.", style="Muted.TLabel")
        on_provider(False)

    def _test(self):
        self.test_lbl.config(text="Testing...", fg=theme.MUTED)

        def done(ok, msg):
            self.test_ok = ok
            if self.winfo_exists() and self.page == 1:
                self.test_lbl.config(text=msg, fg=theme.GREEN if ok else theme.RED)
        self.app.test_connection(callback=done)

    def check_server(self):
        if not self.v["host"].get().strip():
            messagebox.showwarning(APP_NAME, "Enter the server host or IP address.", parent=self)
            return False
        try:
            int(self.v["port"].get())
        except ValueError:
            messagebox.showwarning(APP_NAME, "The port must be a number.", parent=self)
            return False
        if not self.v["password"].get():
            messagebox.showwarning(APP_NAME, "Enter the source password.", parent=self)
            return False
        if self.test_ok is not True:
            return messagebox.askyesno(APP_NAME, "The connection hasn't been tested successfully yet. "
                                                 "Continue anyway?", parent=self)
        return True

    def page_source(self):
        self.header.config(text="What do you want to play?")
        devices, loops, apps = self.app.refresh_devices()
        v = self.v["source"]
        opts = ttk.Frame(self.body)
        opts.pack(fill="x")

        def option(value, title, desc, state="normal"):
            ttk.Radiobutton(opts, text=title, value=value, variable=v, state=state, style="Choice.TRadiobutton",
                            command=lambda: self.show(self.page)).pack(anchor="w", pady=(6, 0))
            ttk.Label(opts, text=desc, style="Muted.TLabel", wraplength=540, justify="left").pack(anchor="w",
                                                                                              padx=(22, 0))
        option("queue", "A playlist I build in the app",
               "Files, folders, YouTube / SoundCloud / Spotify links and radio streams, played back to back.")
        option("loopback", "Everything this PC plays (system audio)",
               "Air whatever you hear. No extra software needed. Game, chat and notification sounds "
               "are included too - pick 'Just one app' to leave them out.",
               "normal" if capture.available() else "disabled")
        option("app", "Just one app (Spotify, a browser...)",
               "Air only that app's sound, so game, chat and notification sounds stay off air. No extra "
               "software needed (Windows 10 version 2004 or newer).",
               "normal" if capture.app_capture_available() else "disabled")
        option("device", "An audio input (VB-CABLE, mixer, microphone)",
               "For DJ software or a virtual cable: send your player's output to 'CABLE Input' and pick "
               "'CABLE Output' here.")

        detail = ttk.Frame(self.body)
        detail.pack(fill="x", pady=(14, 0))
        src = v.get()
        if src == "queue":
            n = len(self.app.playlist.items)
            ttk.Label(detail, text=f"Queue: {n} item(s). Add some now or later on the Broadcast tab:").pack(anchor="w")
            b = ttk.Frame(detail)
            b.pack(anchor="w", pady=6)
            ttk.Button(b, text="Add files...", command=self.app.add_files).pack(side="left")
            ttk.Button(b, text="Add folder...", command=self.app.add_folder).pack(side="left", padx=6)
            ttk.Button(b, text="Add links / search...", command=self.app.add_links).pack(side="left")
        elif src == "loopback":
            ttk.Label(detail, text="Capture from:").pack(side="left")
            ttk.Combobox(detail, textvariable=self.v["loopback_device"], values=["Default speakers"] + loops,
                         state="readonly", width=50).pack(side="left", padx=6)
        elif src == "app":
            ttk.Label(detail, text="App:").pack(side="left")
            ttk.Combobox(detail, textvariable=self.v["app_name"], values=apps, width=40).pack(side="left", padx=6)
            ttk.Button(detail, text="Refresh", command=lambda: self.show(self.page)).pack(side="left")
            ttk.Label(self.body, text="Start the app first so it shows up in the list. Browsers are listed by "
                                      "name (opera.exe, chrome.exe...) and air every tab.",
                      style="Muted.TLabel", wraplength=540, justify="left").pack(anchor="w", pady=(8, 0))
        else:
            ttk.Label(detail, text="Input device:").pack(side="left")
            ttk.Combobox(detail, textvariable=self.v["device"], values=devices, state="readonly",
                         width=50).pack(side="left", padx=6)
            if not any("CABLE Output" in d for d in devices):
                warn = ttk.Frame(self.body)
                warn.pack(fill="x", pady=8)
                ttk.Label(warn, text="VB-CABLE is not installed.", style="Danger.TLabel").pack(side="left")
                ttk.Button(warn, text="Get VB-CABLE (free)", command=lambda: webbrowser.open(VB_CABLE_URL)
                           ).pack(side="left", padx=8)
                ttk.Label(warn, text="Restart the PC after installing, then press Refresh.",
                          style="Muted.TLabel").pack(side="left")

    def check_source(self):
        if self.v["source"].get() == "device" and not self.v["device"].get():
            messagebox.showwarning(APP_NAME, "Pick an input device.", parent=self)
            return False
        if self.v["source"].get() == "app" and not self.v["app_name"].get().strip():
            messagebox.showwarning(APP_NAME, "Pick the app to air.", parent=self)
            return False
        return True

    def page_station(self):
        self.header.config(text="Your station")
        f = self.form()
        self.row(f, 0, "Station name", ttk.Entry(f, textvariable=self.v["name"]))
        self.row(f, 1, "Genre", ttk.Entry(f, textvariable=self.v["genre"]))
        self.row(f, 2, "Website (optional)", ttk.Entry(f, textvariable=self.v["url"]))
        self.row(f, 3, "Bitrate (kbps)", ttk.Combobox(f, textvariable=self.v["bitrate"], values=BITRATES,
                                                     state="readonly", width=8), sticky="w")
        ttk.Label(f, text="128 is standard. Free plans often cap at 96 - use your plan's limit or the server "
                          "will drop the stream.", style="Muted.TLabel", wraplength=460, justify="left"
                  ).grid(row=4, column=1, sticky="w")
        if self.v["source"].get() != "queue":
            self.row(f, 5, "Song titles from", ttk.Combobox(f, textvariable=self.v["title_source"],
                                                           values=TITLE_SOURCES, state="readonly", width=32),
                     sticky="w")
            ttk.Label(f, text="Detects what's playing in Spotify, YouTube in your browser, VLC, foobar2000, "
                              "Winamp, MusicBee... and shows it as the stream title.", style="Muted.TLabel",
                      wraplength=460, justify="left").grid(row=6, column=1, sticky="w")

    def page_extras(self):
        self.header.config(text="Online music & Last.fm (optional)")
        f = self.form()
        self.row(f, 0, "Find songs & Spotify tracks on", ttk.Combobox(
            f, textvariable=self.v["match_service"], values=list(media.MATCH_SERVICES), state="readonly",
            width=14), sticky="w")
        self.row(f, 1, "YouTube sign-in from", ttk.Combobox(
            f, textvariable=self.v["ytdlp_cookies_browser"], values=media.COOKIE_BROWSERS, state="readonly",
            width=14), sticky="w")
        ttk.Label(f, text="Leave empty unless YouTube asks you to 'confirm you're not a bot' (often on VPNs).",
                  style="Muted.TLabel", wraplength=420, justify="left").grid(row=2, column=1, sticky="w")

        lf = ttk.LabelFrame(self.body, text="Last.fm scrobbling", padding=10)
        lf.pack(fill="x", pady=14)
        lf.columnconfigure(1, weight=1)
        self.row(lf, 0, "API key", ttk.Entry(lf, textvariable=self.v["lastfm_api_key"]))
        self.row(lf, 1, "Shared secret", ttk.Entry(lf, textvariable=self.v["lastfm_api_secret"], show="•"))
        b = ttk.Frame(lf)
        b.grid(row=2, column=1, sticky="w", pady=4)
        ttk.Button(b, text="Get a free key", command=lambda: webbrowser.open(CREATE_KEY_URL)).pack(side="left")
        ttk.Button(b, text="Connect account...", command=self._lastfm).pack(side="left", padx=6)
        self.lf_status = ttk.Label(b, style="Muted.TLabel")
        self.lf_status.pack(side="left", padx=6)
        ttk.Checkbutton(lf, text="Scrobble what the station plays", variable=self.v["lastfm_scrobble"]
                        ).grid(row=3, column=1, sticky="w")
        self._lf_refresh()

    def _lastfm(self):
        self.app.lastfm_connect()
        self._lf_refresh()

    def _lf_refresh(self):
        user = self.v["lastfm_user"].get()
        self.lf_status.config(text=f"Connected as {user}" if user and self.v["lastfm_session"].get()
                              else "Not connected (you can skip this)")

    def page_done(self):
        self.header.config(text="All set")
        url = listener_url({k: self.v[k].get() for k in ("server_type", "host", "port", "mount", "sid")})
        self.text(self.body, "Your station's listening link:")
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(0, 10))
        e = ttk.Entry(row, font=(theme.MONO, 11))
        e.insert(0, url)
        e.config(state="readonly")
        e.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Copy", command=lambda: (self.clipboard_clear(), self.clipboard_append(url))
                   ).pack(side="left", padx=6)
        self.text(self.body, "Share it with friends, or paste it into any radio player. Some hosts (e.g. "
                             "Listen2MyRadio) give you their own station link instead - use that if the direct "
                             "link doesn't play.", style="Muted.TLabel")
        self.text(self.body, "Press GO LIVE on the Broadcast tab whenever you're ready. You can re-run this "
                             "wizard from File > Setup wizard.")
        ttk.Checkbutton(self.body, text="Go live now", variable=self.go_live).pack(anchor="w", pady=8)

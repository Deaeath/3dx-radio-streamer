"""The app's look: a dark palette with a pink-to-violet accent, ttk styles for every widget,
and a few drawn widgets (gradient banner, glowing pill button, LED level meter).

Pure tkinter - gradients are canvas lines or PhotoImages built row by row, so there is
nothing extra to install or bundle.
"""

import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

# -- palette ------------------------------------------------------------------ #
BG = "#0e1018"          # window
SURFACE = "#161a28"     # lists, log, text areas
RAISED = "#1f2436"      # inputs, secondary buttons
HOVER = "#2a3150"
BORDER = "#2c3350"
TEXT = "#eef0f8"
MUTED = "#9ba3c0"
FAINT = "#646c8c"
PINK = "#ff3d8b"
VIOLET = "#8b5cf6"
CYAN = "#22d3ee"
GREEN = "#22c55e"
TEAL = "#14b8a6"
AMBER = "#f59e0b"
RED = "#ef4444"

ACCENT = PINK
GRADIENT = (PINK, VIOLET)
GO_GRADIENT = (GREEN, TEAL)
STOP_GRADIENT = (RED, PINK)

FONT = "Segoe UI"
DISPLAY = "Segoe UI"
MONO = "Consolas"


def _pick_fonts(root):
    global FONT, DISPLAY, MONO
    fams = set(tkfont.families(root))
    FONT = next((f for f in ("Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", "DejaVu Sans") if f in fams),
                "TkDefaultFont")
    DISPLAY = next((f for f in ("Segoe UI Variable Display", "Segoe UI Semibold", FONT) if f in fams), FONT)
    MONO = next((f for f in ("Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono") if f in fams), "TkFixedFont")


# -- colour helpers ------------------------------------------------------------- #
def _rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def mix(a, b, t):
    """Colour t of the way from a to b."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * t for x, y in zip(ra, rb)))


def lighten(c, t=0.15):
    return mix(c, "#ffffff", t)


def darken(c, t=0.2):
    return mix(c, "#000000", t)


# -- ttk theme ------------------------------------------------------------------ #
def apply(root):
    """Style the whole app. Call once, right after creating the Tk root."""
    _pick_fonts(root)
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)

    base = (FONT, 10)
    bold = (FONT, 10, "bold")
    # Named fonts, not the option database: a "*Font" option would override every ttk style's font
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        tkfont.nametofont(name, root).configure(family=FONT, size=10)
    tkfont.nametofont("TkFixedFont", root).configure(family=MONO, size=10)
    for opt, val in (("*Background", BG), ("*Foreground", TEXT),
                     ("*selectBackground", PINK), ("*selectForeground", "white"),
                     ("*insertBackground", TEXT), ("*highlightThickness", 0),
                     ("*TCombobox*Listbox.background", RAISED), ("*TCombobox*Listbox.foreground", TEXT),
                     ("*TCombobox*Listbox.selectBackground", PINK), ("*TCombobox*Listbox.selectForeground", "white"),
                     ("*TCombobox*Listbox.font", base), ("*TCombobox*Listbox.borderWidth", 0)):
        root.option_add(opt, val)

    style.configure(".", background=BG, foreground=TEXT, fieldbackground=RAISED, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, troughcolor=RAISED, focuscolor=PINK,
                    selectbackground=PINK, selectforeground="white", insertcolor=TEXT, arrowcolor=MUTED,
                    font=base)
    style.map(".", foreground=[("disabled", FAINT)])

    style.configure("TFrame", background=BG)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Faint.TLabel", foreground=FAINT)
    style.configure("Danger.TLabel", foreground=RED)
    style.configure("Success.TLabel", foreground=GREEN)
    style.configure("Link.TLabel", foreground=CYAN, font=(FONT, 10, "underline"))
    style.configure("Heading.TLabel", font=(DISPLAY, 20, "bold"))
    style.configure("Subheading.TLabel", font=(DISPLAY, 11), foreground=MUTED)
    style.configure("Status.TLabel", background=SURFACE, foreground=MUTED, padding=(14, 5))

    style.configure("TLabelframe", background=BG, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=BG, foreground=PINK, font=(DISPLAY, 10, "bold"))

    # buttons: quiet secondary by default, a filled pink accent for primary actions
    style.configure("TButton", background=RAISED, foreground=TEXT, bordercolor=BORDER, lightcolor=RAISED,
                    darkcolor=RAISED, relief="flat", padding=(12, 5), focuscolor=RAISED, font=base)
    style.map("TButton",
              background=[("disabled", BG), ("pressed", darken(HOVER, 0.15)), ("active", HOVER)],
              bordercolor=[("active", VIOLET), ("focus", VIOLET)],
              lightcolor=[("pressed", darken(HOVER, 0.15)), ("active", HOVER)],
              darkcolor=[("pressed", darken(HOVER, 0.15)), ("active", HOVER)],
              foreground=[("disabled", FAINT)])
    style.configure("Accent.TButton", background=PINK, foreground="white", bordercolor=PINK, lightcolor=PINK,
                    darkcolor=PINK, focuscolor=PINK, font=bold, padding=(16, 6))
    style.map("Accent.TButton",
              background=[("disabled", RAISED), ("pressed", darken(PINK)), ("active", lighten(PINK))],
              bordercolor=[("active", lighten(PINK)), ("focus", lighten(PINK))],
              lightcolor=[("pressed", darken(PINK)), ("active", lighten(PINK))],
              darkcolor=[("pressed", darken(PINK)), ("active", lighten(PINK))])
    style.configure("Tool.TButton", padding=(10, 4), width=0)      # width 0: no 11-character minimum
    style.configure("Tool.Accent.TButton", padding=(10, 4), width=0)   # inherits the accent colours

    for kind in ("TRadiobutton", "TCheckbutton"):
        style.configure(kind, background=BG, foreground=TEXT, indicatorbackground=RAISED,
                        indicatorforeground="white", indicatormargin=(0, 0, 8, 0), upperbordercolor=BORDER,
                        lowerbordercolor=BORDER, focuscolor=BG, padding=(0, 2))
        style.map(kind,
                  indicatorbackground=[("disabled", BG), ("selected", PINK), ("active", HOVER)],
                  upperbordercolor=[("selected", PINK), ("active", VIOLET)],
                  lowerbordercolor=[("selected", PINK), ("active", VIOLET)],
                  foreground=[("disabled", FAINT), ("active", lighten(TEXT))],
                  background=[("active", BG)])
    style.configure("Choice.TRadiobutton", font=(FONT, 11, "bold"))

    for kind in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(kind, fieldbackground=RAISED, foreground=TEXT, bordercolor=BORDER, lightcolor=RAISED,
                        darkcolor=RAISED, insertcolor=TEXT, padding=(8, 3), arrowsize=14)
        style.map(kind,
                  fieldbackground=[("disabled", BG), ("readonly", RAISED)],
                  foreground=[("disabled", FAINT)],
                  bordercolor=[("focus", PINK), ("hover", VIOLET)],
                  lightcolor=[("focus", RAISED)],
                  selectbackground=[("readonly", RAISED), ("!focus", RAISED)],
                  selectforeground=[("readonly", TEXT), ("!focus", TEXT)],
                  background=[("active", HOVER), ("pressed", HOVER)],
                  arrowcolor=[("disabled", FAINT), ("active", PINK)])
    style.configure("TCombobox", background=RAISED, arrowcolor=MUTED)
    style.map("TCombobox",
              background=[("disabled", BG), ("pressed", HOVER), ("active", HOVER), ("!disabled", RAISED)],
              lightcolor=[("disabled", BG), ("focus", RAISED)], darkcolor=[("disabled", BG)])

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(14, 10, 14, 0))
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED, bordercolor=BG, lightcolor=BG,
                    darkcolor=BG, padding=(18, 8), font=(FONT, 10, "bold"), focuscolor=BG)
    style.map("TNotebook.Tab",
              background=[("selected", RAISED), ("active", SURFACE)],
              foreground=[("selected", PINK), ("active", TEXT)],
              lightcolor=[("selected", RAISED)], darkcolor=[("selected", RAISED)],
              bordercolor=[("selected", BORDER)],
              expand=[("selected", (0, 0, 0, 0))])

    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, bordercolor=BORDER,
                    lightcolor=SURFACE, darkcolor=SURFACE, rowheight=30, font=base, borderwidth=0)
    style.map("Treeview", background=[("selected", VIOLET)], foreground=[("selected", "white")])
    style.configure("Treeview.Heading", background=RAISED, foreground=MUTED, bordercolor=BORDER,
                    lightcolor=RAISED, darkcolor=RAISED, relief="flat", font=(FONT, 9, "bold"), padding=(8, 6))
    style.map("Treeview.Heading", background=[("active", HOVER)], foreground=[("active", TEXT)])

    # slim, arrowless scrollbars
    for orient, sticky in (("Vertical", "ns"), ("Horizontal", "ew")):
        style.layout(f"{orient}.TScrollbar", [(f"{orient}.Scrollbar.trough", {"sticky": sticky, "children": [
            (f"{orient}.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        style.configure(f"{orient}.TScrollbar", troughcolor=SURFACE, background=BORDER, bordercolor=SURFACE,
                        lightcolor=BORDER, darkcolor=BORDER, arrowsize=10, gripcount=0)
        style.map(f"{orient}.TScrollbar", background=[("active", VIOLET), ("pressed", PINK)],
                  lightcolor=[("active", VIOLET)], darkcolor=[("active", VIOLET)])

    style.configure("TSeparator", background=BORDER)
    style.configure("Accent.Horizontal.TProgressbar", troughcolor=RAISED, background=PINK, bordercolor=RAISED,
                    lightcolor=PINK, darkcolor=PINK, thickness=6)
    style.configure("TMenubutton", background=BG, foreground=TEXT)
    return style


def style_text(widget, mono=False):
    """Colour a classic tk Text / ScrolledText / Listbox to match."""
    widget.configure(bg=SURFACE, fg=TEXT, insertbackground=PINK, selectbackground=VIOLET,
                     selectforeground="white", relief="flat", borderwidth=0, highlightthickness=1,
                     highlightbackground=BORDER, highlightcolor=PINK,
                     font=(MONO, 10) if mono else (FONT, 10))
    try:
        widget.configure(padx=10, pady=8)
    except tk.TclError:
        pass


def style_menu(menu):
    """Popup menus (Windows may still draw them natively)."""
    menu.configure(bg=RAISED, fg=TEXT, activebackground=PINK, activeforeground="white", relief="flat",
                   borderwidth=0, font=(FONT, 10))


def dark_titlebar(win):
    """Dark Windows 11 title bar in the window colour. Harmless elsewhere."""
    if sys.platform != "win32":
        return

    def go():
        try:
            if not win.winfo_ismapped():            # before mapping, wm_frame() is not the real frame yet
                win.after(30, go)
                return
            import ctypes
            hwnd = int(win.wm_frame(), 16)
            dwm = ctypes.windll.dwmapi
            on = ctypes.c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), 4)            # immersive dark mode
            for attr, colour in ((35, BG), (34, BORDER), (36, TEXT)):            # caption, border, text
                r, g, b = _rgb(colour)
                ref = ctypes.c_int(r | (g << 8) | (b << 16))
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ref), 4)
        except (OSError, ValueError, AttributeError, tk.TclError):
            pass
    win.after(10, go)


# -- drawn widgets ---------------------------------------------------------------- #
def gradient_lines(canvas, w, h, c1, c2, horizontal=True, tag="grad"):
    """Fill a canvas with a two-colour gradient (one line per pixel column/row)."""
    canvas.delete(tag)
    steps = max(1, w if horizontal else h)
    for i in range(steps):
        colour = mix(c1, c2, i / max(1, steps - 1))
        if horizontal:
            canvas.create_line(i, 0, i, h, fill=colour, tags=tag)
        else:
            canvas.create_line(0, i, w, i, fill=colour, tags=tag)
    canvas.tag_lower(tag)


def rounded_gradient(w, h, c1, c2, radius, bg):
    """A PhotoImage pill/rounded rectangle with a diagonal gradient, corners blended into bg."""
    img = tk.PhotoImage(width=w, height=h)
    a, b, back = _rgb(c1), _rgb(c2), _rgb(bg)
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            t = (x / max(1, w - 1)) * 0.8 + (y / max(1, h - 1)) * 0.2
            col = [p + (q - p) * t for p, q in zip(a, b)]
            if y < h * 0.45:                                    # soft top sheen
                col = [v + (255 - v) * 0.10 * (1 - y / (h * 0.45)) for v in col]
            cx = radius if x < radius else w - 1 - radius if x > w - 1 - radius else x
            cy = radius if y < radius else h - 1 - radius if y > h - 1 - radius else y
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            cover = max(0.0, min(1.0, radius + 0.5 - d)) if (cx != x or cy != y) else 1.0
            row.append(_hex([bv + (cv - bv) * cover for cv, bv in zip(col, back)]))
        rows.append("{" + " ".join(row) + "}")
    img.put(" ".join(rows), to=(0, 0))
    return img


class PillButton(tk.Canvas):
    """A big rounded gradient button with hover and pressed states."""

    def __init__(self, parent, text, colors, command, width=180, height=64, font_size=15, bg=BG):
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.w, self.h, self.bg_colour = width, height, bg
        self.command = command
        self.font = (DISPLAY, font_size, "bold")
        self._images = {}
        self._state = "normal"
        self.configure_button(text, colors)
        self.bind("<Enter>", lambda e: self._show("hover"))
        self.bind("<Leave>", lambda e: self._show("normal"))
        self.bind("<ButtonPress-1>", lambda e: self._show("pressed"))
        self.bind("<ButtonRelease-1>", self._release)

    def configure_button(self, text, colors):
        self.text = text
        key = tuple(colors)
        if key not in self._images:
            c1, c2 = colors
            r = self.h // 2
            self._images[key] = {
                "normal": rounded_gradient(self.w, self.h, c1, c2, r, self.bg_colour),
                "hover": rounded_gradient(self.w, self.h, lighten(c1, 0.12), lighten(c2, 0.12), r, self.bg_colour),
                "pressed": rounded_gradient(self.w, self.h, darken(c1, 0.15), darken(c2, 0.15), r, self.bg_colour),
            }
        self.colors = key
        self._show(self._state)

    def _show(self, state):
        self._state = state
        self.delete("all")
        self.create_image(0, 0, image=self._images[self.colors][state], anchor="nw")
        dy = 1 if state == "pressed" else 0
        self.create_text(self.w // 2 + 1, self.h // 2 + 2 + dy, text=self.text, font=self.font,
                         fill=darken(self.colors[1], 0.45))                    # drop shadow
        self.create_text(self.w // 2, self.h // 2 + dy, text=self.text, font=self.font, fill="white")

    def _release(self, event):
        inside = 0 <= event.x < self.w and 0 <= event.y < self.h
        self._show("hover" if inside else "normal")
        if inside and self.command:
            self.command()


class LevelMeter(tk.Canvas):
    """Segmented LED meter: green -> amber -> red, unlit segments dimmed, with a falling peak hold."""

    SEGMENTS = 48

    def __init__(self, parent, height=18):
        super().__init__(parent, height=height, bg=BG, highlightthickness=0, bd=0)
        self.peak = 0.0

    @staticmethod
    def _colour(frac):
        if frac < 0.6:
            return mix(GREEN, TEAL, frac / 0.6 * 0.4)
        if frac < 0.85:
            return mix(AMBER, "#fbbf24", (frac - 0.6) / 0.25)
        return RED

    def draw(self, frac):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10:
            return
        self.delete("all")
        self.peak = max(frac, self.peak - 0.012)
        n, gap = self.SEGMENTS, 3
        seg = (w - gap * (n - 1)) / n
        lit = int(round(frac * n))
        peak_i = min(n - 1, int(self.peak * n))
        for i in range(n):
            x0 = i * (seg + gap)
            on = i < lit
            col = self._colour(i / n)
            fill = col if on else mix(col, BG, 0.82)
            if i == peak_i and self.peak > 0.02 and not on:
                fill = mix(col, BG, 0.25)
            self.create_rectangle(x0, 0, x0 + seg, h, fill=fill, width=0)


class Banner(tk.Canvas):
    """The gradient header strip with logo, title and clickable menu labels."""

    def __init__(self, parent, title, subtitle="", logo=None, menus=(), height=64):
        super().__init__(parent, height=height, highlightthickness=0, bd=0, bg=BG)
        self.title, self.subtitle, self.logo, self.menus = title, subtitle, logo, list(menus)
        self._after = None
        self.bind("<Configure>", lambda e: self._schedule())

    def _schedule(self):
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(30, self.redraw)

    def redraw(self):
        self._after = None
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        c1, c2 = darken(PINK, 0.05), darken(VIOLET, 0.1)
        gradient_lines(self, w, h, c1, c2)
        # a faint glossy diagonal band
        self.create_polygon(w * 0.55, 0, w * 0.68, 0, w * 0.58, h, w * 0.45, h,
                            fill=lighten(mix(c1, c2, 0.56), 0.07), outline="")
        self.create_line(0, h - 1, w, h - 1, fill=darken(VIOLET, 0.4))
        x = 16
        if self.logo is not None:
            self.create_image(x, h // 2, image=self.logo, anchor="w")
            x += self.logo.width() + 12
        self.create_text(x, h // 2 - (8 if self.subtitle else 0), text=self.title, anchor="w", fill="white",
                         font=(DISPLAY, 17, "bold"))
        if self.subtitle:
            self.create_text(x + 1, h // 2 + 13, text=self.subtitle, anchor="w", fill=lighten(PINK, 0.75),
                             font=(FONT, 9))
        right = w - 16
        for label, menu in reversed(self.menus):
            tid = self.create_text(right, h // 2, text=label, anchor="e", fill="white", font=(FONT, 10, "bold"))
            x0, y0, x1, y1 = self.bbox(tid)
            pad = self.create_rectangle(x0 - 10, y0 - 6, x1 + 10, y1 + 6, outline="", fill="")
            self.tag_lower(pad, tid)
            for item in (tid, pad):
                self.tag_bind(item, "<Enter>", lambda e, p=pad: (self.itemconfigure(p, fill=lighten(VIOLET, 0.25)),
                                                                 self.configure(cursor="hand2")))
                self.tag_bind(item, "<Leave>", lambda e, p=pad: (self.itemconfigure(p, fill=""),
                                                                 self.configure(cursor="")))
                self.tag_bind(item, "<Button-1>", lambda e, m=menu, b=(x0 - 10, y1 + 8): self._post(m, b))
            right = x0 - 24

    def _post(self, menu, at):
        menu.tk_popup(self.winfo_rootx() + int(at[0]), self.winfo_rooty() + int(at[1]))

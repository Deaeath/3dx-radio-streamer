# Changelog

## 1.3.0 - 2026-10-08

### Host it yourself - no radio host account
- New **Host it myself (free, no account)** option, now the default for new installs: the app is the
  stream server, so there's nothing to sign up for or copy. Press GO LIVE and share the link it shows.
- **Easy** (recommended) gives you a free public `https://...trycloudflare.com` link through a Cloudflare
  tunnel. It works behind any router, CGNAT or VPN, with no port forwarding. The tool is downloaded the
  first time you use it, and the link only appears once it really works. It changes each time you go live.
- **Direct** asks your router to open the port (UPnP) and gives a fixed `http://your-ip:port/` link, and
  warns if your connection can't take incoming listeners (VPN, CGNAT). **Local network only** is for testing.
- Song titles reach players that support them, a browser opening the link gets a small player page,
  and the Broadcast tab shows how many people are listening.

### Better live audio (from 1.2.0)
- Fixed occasional pops and dropouts with live sources (system audio, one app, input devices): the stream
  now follows the sound card's own clock instead of drifting against it.
- A limiter before the encoder stops loud tracks crackling; tracks fade in for 30 ms so they don't click.

### Microphone
- New **Microphone** section: pick a mic, press **MIC** (or F9) to talk over the music. The music fades
  down while the mic is on (adjustable), with no clicks. The mic always starts off.

### Fixes
- **Test connection** shows its result under the button, and while you're live it only confirms you're on
  air instead of logging in a second time (which could knock the live stream off).
- The status bar always stays visible.

## 1.1.0 - 2026-10-04

- A new look: a dark theme with a pink-to-violet gradient header, a glowing GO LIVE / STOP
  button, an LED-style level meter with peak hold, a pulsing on-air label, a step-by-step
  sidebar in the setup wizard, and dark title bars on Windows 11. It's still pure tkinter,
  so nothing new to install.
- New live source, **One app only**: air just Spotify, a browser or any other app, with game,
  chat and notification sounds left out. It uses Windows' per-app capture (Windows 10 version
  2004 or newer), so no virtual cable or driver is needed.
- Listen2MyRadio is the recommended free host. The setup wizard links to its sign-up page and
  control panel, and the README walks through its Stream Details.
- README wording is now for new and advanced users rather than kids and grown-ups.
- Works with [3DXModKit](https://github.com/Deaeath/3DXModKit) 1.1.0: its Mods tab installs and
  starts the streamer, and its `radio-streamer` mod prints the exact link to paste into a room radio.

## 1.0.0 - 2026-10-04

The first public release.

### Play anything
- A gapless queue of local files and folders (any format FFmpeg reads, including video files)
  and `.m3u` / `.pls` / `.xspf` playlists.
- YouTube, SoundCloud, Bandcamp, Mixcloud, Vimeo, Twitch and over 1000 other sites via yt-dlp.
- Spotify track / album / playlist links, matched track by track on YouTube or SoundCloud.
- Internet radio streams, direct audio links, HLS, and song-name search.
- Live sources: Windows system audio (no virtual cable needed), or any input device
  (VB-CABLE, mixer, microphone).
- Loudness evening between tracks.

### Broadcast
- Shoutcast v1, Shoutcast v2 (DNAS 2) and Icecast 2 / AzuraCast, with MP3 from 64 to 320 kbps.
- Automatic reconnect, a level meter, a silence warning, and a one-click copy of the listener
  ("Room") URL.
- Stream titles: sent from track tags, or detected from the Spotify app, a browser
  (YouTube / SoundCloud / Spotify Web), VLC, foobar2000, Winamp, MusicBee, AIMP, or a Last.fm
  user's now playing.
- Last.fm scrobbling.

### Setup
- First-run wizard with provider presets (Listen2MyRadio, Zeno.FM, FreeSHOUTcast, Caster.fm and
  generic servers), a connection test, and settings import from Mixxx.
- Self-contained Windows builds (installer, portable zip, single-file exe) with FFmpeg and yt-dlp
  bundled. **Tools → Update yt-dlp** keeps YouTube working.
- `--selftest` checks tools, devices and the whole broadcast pipeline.

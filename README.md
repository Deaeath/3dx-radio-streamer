# 3DX Radio Streamer

[![Latest release](https://img.shields.io/github/v/release/Deaeath/3dx-radio-streamer)](https://github.com/Deaeath/3dx-radio-streamer/releases/latest) [![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Run your own internet radio station from your PC. 3DX Radio Streamer sends music to a
**Shoutcast** or **Icecast** server, so anyone with your station link can listen, including
a radio in a 3DXChat room.

## What you can play

| Source | How |
|---|---|
| Music files & folders | MP3, FLAC, WAV, OGG, Opus, M4A/AAC, WMA, AIFF, APE, video files (audio track) and more |
| Playlists | `.m3u`, `.m3u8`, `.pls`, `.xspf` |
| YouTube, SoundCloud, Bandcamp, Mixcloud, Vimeo, Twitch… | Paste a video, track, set or playlist link (powered by yt-dlp, 1000+ sites) |
| Spotify | Paste a track, album or playlist link. Spotify audio is DRM-protected, so each track is matched and played from YouTube or SoundCloud |
| Internet radio & direct links | `.mp3`/`.aac` URLs, Shoutcast/Icecast streams, HLS |
| A song name | Type `Artist - Title` and it is found online |
| **Live: system audio** | Everything the PC plays: the Spotify app, a browser tab, any player. No extra software (Windows) |
| **Live: an input device** | VB-CABLE, a mixer or a microphone, for DJ software |

The queue plays back to back without gaps and evens out loudness between tracks.
Online tracks download just before they play.

### Also included
- **Setup wizard** on first launch, with presets for Listen2MyRadio, Zeno.FM, FreeSHOUTcast,
  Caster.fm and any Shoutcast v1/v2 or Icecast 2 / AzuraCast server. It can also copy your
  settings from Mixxx.
- **Stream titles**: sent automatically from track tags. For live sources, titles are detected from
  the Spotify app, YouTube / SoundCloud / Spotify Web in your browser, VLC, foobar2000, Winamp,
  MusicBee, AIMP, or a Last.fm user's now playing.
- **Last.fm**: scrobbles everything the station plays.
- **Reliability**: reconnects automatically, has a level meter, and warns you if listeners are
  hearing silence.
- **Room URL**: a one-click copy of the listener link to paste into your 3DX room radio.

## Install

**Windows:** download from the [latest release](https://github.com/Deaeath/3dx-radio-streamer/releases/latest).
FFmpeg and yt-dlp are included in every download.

| Download | Best for |
|---|---|
| `3DX-Radio-Streamer-<version>-setup.exe` | **Most people.** Installs with Start menu and desktop shortcuts. No admin rights needed. |
| `3DX-Radio-Streamer-<version>-win64-portable.zip` | Running from a USB stick or any folder: extract it and run `3DX Radio Streamer.exe`. |
| `3DX-Radio-Streamer-<version>-win64-standalone.exe` | A single file you can run anywhere. It starts a few seconds slower because it unpacks itself each time. |

`SHA256SUMS.txt` lists checksums so you can verify the downloads.

> Windows SmartScreen may warn about an unrecognized app because the build isn't code-signed.
> Click **More info → Run anyway**.

**From source (Windows / macOS / Linux):** Python 3.9+ with tkinter, and FFmpeg on PATH.
```
pip install -r requirements.txt
python RadioStreamer.py
```
On macOS and Linux, live capture uses an input device (on macOS, BlackHole works as a virtual
cable; on Linux, choose a PulseAudio `.monitor` source). System-audio capture is Windows-only.

## Quick start
1. Get a stream server from a radio host. Free options include Listen2MyRadio and FreeSHOUTcast.
   Turn the server **on** in the host's control panel.
2. Start the app. The wizard asks for the host, port and source password, and tests the login.
3. Choose what to play, then press **GO LIVE**.
4. Copy the **Room URL** and paste it into your radio. Some hosts give you their own station
   link to share instead.

## Troubleshooting

| Message | Fix |
|---|---|
| *refused the connection* | The stream server is off. Turn it on in your host's panel, or check the host and port. Shoutcast sources connect on **port + 1**. |
| *Server rejected the login* | Wrong source password (Icecast: also check the username and mount). |
| *server dropped the stream right after login* | The bitrate is above your plan's limit. Free plans are often 96 kbps. |
| *YouTube … confirm you're not a bot* | Common on VPNs. Turn the VPN off, or on **Integrations** set *YouTube sign-in* to the browser you use YouTube in (Firefox works best), or match songs on SoundCloud. |
| YouTube links suddenly fail | **Tools → Update yt-dlp**. |
| Listeners hear silence | Check the level meter. For system audio, make sure music plays on the device being captured. |

Settings are stored in `%APPDATA%\3DXRadioStreamer\settings.json`. The source password is
stored there in plain text, as Mixxx does.

## Building a release (Windows)
```
powershell -ExecutionPolicy Bypass -File build\build.ps1
```
This creates `.venv`, downloads an LGPL FFmpeg build and yt-dlp into `bin\`, runs PyInstaller and
writes `dist\3DX Radio Streamer\` plus a portable zip. If [Inno Setup 6](https://jrsoftware.org/isinfo.php)
is installed, it also builds a `-setup.exe` installer. To ship a default Last.fm API key, set
`LASTFM_API_KEY` and `LASTFM_API_SECRET` before building.

Tests: `python tests\test_engine.py <folder-with-music\ and-test.m3u>` runs the whole pipeline
against a local mock server.

## Legal
Only broadcast audio you have the right to stream. Public internet radio usually needs
performance licences, and downloading from YouTube or other sites may break their terms of
service. You are responsible for what you broadcast. See `THIRD-PARTY-NOTICES.md` for the
bundled components.

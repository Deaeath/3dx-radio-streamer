# Changelog

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

# Third-party components

3DX Radio Streamer bundles or uses the following software. Each one keeps its own licence.

| Component | Use | Licence | Source |
|---|---|---|---|
| FFmpeg (BtbN LGPL build) | Decoding, capture, MP3 encoding, loudness | LGPL v3 (this build includes no GPL parts); bundled unmodified as `ffmpeg.exe` | https://ffmpeg.org · https://github.com/BtbN/FFmpeg-Builds |
| LAME (inside FFmpeg) | MP3 encoder | LGPL v2 | https://lame.sourceforge.io |
| yt-dlp | Reading YouTube / SoundCloud / other links | Unlicense | https://github.com/yt-dlp/yt-dlp |
| PyAudioWPatch / PortAudio | Windows system-audio (WASAPI loopback) capture | MIT | https://github.com/s0d3s/PyAudioWPatch |
| Python & Tcl/Tk | Runtime and user interface | PSF License / Tcl/Tk License | https://python.org |
| PyInstaller bootloader | Windows executable | GPL v2 with bootloader exception | https://pyinstaller.org |

FFmpeg is shipped as a separate, unmodified executable and called as a subprocess. To comply with
the LGPL, its licence text is included (`FFMPEG-LICENSE.txt`) and its source is available at the
links above. You may replace `_internal\bin\ffmpeg.exe` with any compatible FFmpeg build.

FFmpeg is a trademark of Fabrice Bellard. Spotify, YouTube, SoundCloud, Last.fm, Shoutcast and
Icecast are trademarks of their respective owners. This project is not affiliated with them or
with 3DXChat.

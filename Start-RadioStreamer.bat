@echo off
rem 3DX Radio Streamer - prefers the built app, falls back to running from source
cd /d "%~dp0"
if exist "dist\3DX Radio Streamer\3DX Radio Streamer.exe" (
    start "" "dist\3DX Radio Streamer\3DX Radio Streamer.exe"
) else (
    where pythonw >nul 2>&1 && (start "" pythonw "%~dp0RadioStreamer.py") || (python "%~dp0RadioStreamer.py" & pause)
)

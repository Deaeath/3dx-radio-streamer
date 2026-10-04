<#
.SYNOPSIS
    Build 3DX Radio Streamer for Windows: a portable folder + zip, and an installer if Inno Setup 6 is installed.
.DESCRIPTION
    - creates .venv and installs build requirements
    - downloads an LGPL FFmpeg build (BtbN) and yt-dlp into bin\ (skipped if already present)
    - optionally embeds a Last.fm API key from $env:LASTFM_API_KEY / $env:LASTFM_API_SECRET
    - runs PyInstaller (one-folder, windowed) and zips the result into dist\
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File build\build.ps1
#>
param(
    [string]$FfmpegAsset = "ffmpeg-n8.1-latest-win64-lgpl-8.1.zip",
    [switch]$NoZip,
    [switch]$NoStandalone
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = ([regex]::Match((Get-Content radiostreamer\__init__.py -Raw), 'VERSION = "([^"]+)"')).Groups[1].Value
$appName = "3DX Radio Streamer"
Write-Host "Building $appName $version" -ForegroundColor Cyan

# --- Python environment ------------------------------------------------------
if (-not (Test-Path .venv\Scripts\python.exe)) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { & py -3 -m venv .venv } else { & python -m venv .venv }
}
$python = Join-Path $root ".venv\Scripts\python.exe"
& $python -m pip install --quiet --disable-pip-version-check -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# --- Bundled tools -----------------------------------------------------------
New-Item -ItemType Directory -Force bin, build\cache | Out-Null
if (-not (Test-Path bin\ffmpeg.exe)) {
    $zip = "build\cache\$FfmpegAsset"
    if (-not (Test-Path $zip)) {
        Write-Host "Downloading FFmpeg ($FfmpegAsset)..."
        Invoke-WebRequest "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/$FfmpegAsset" -OutFile $zip
    }
    Expand-Archive $zip -DestinationPath build\cache\ffmpeg -Force
    $ffdir = Get-ChildItem build\cache\ffmpeg -Directory | Select-Object -First 1
    Copy-Item (Join-Path $ffdir.FullName "bin\ffmpeg.exe") bin\
    Copy-Item (Join-Path $ffdir.FullName "LICENSE.txt") bin\FFMPEG-LICENSE.txt -ErrorAction SilentlyContinue
}
if (-not (Test-Path bin\yt-dlp.exe)) {
    Write-Host "Downloading yt-dlp..."
    Invoke-WebRequest "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile bin\yt-dlp.exe
}
& bin\ffmpeg.exe -hide_banner -encoders 2>$null | Select-String libmp3lame | Out-Null
if (-not $?) { throw "bin\ffmpeg.exe has no libmp3lame encoder" }

# --- Optional embedded Last.fm key ------------------------------------------
if ($env:LASTFM_API_KEY) {
    "LASTFM_API_KEY = `"$($env:LASTFM_API_KEY)`"`nLASTFM_API_SECRET = `"$($env:LASTFM_API_SECRET)`"`n" |
        Set-Content -Encoding utf8 radiostreamer\_keys.py
    Write-Host "Embedded Last.fm API key"
}

# --- Icon & version resource ---------------------------------------------------
& $python build\make_icon.py assets
$v = ($version.Split(".") + @("0", "0", "0", "0"))[0..3] -join ", "
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($v), prodvers=($v), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', '$appName'),
    StringStruct('ProductName', '$appName'),
    StringStruct('FileVersion', '$version'),
    StringStruct('ProductVersion', '$version'),
    StringStruct('OriginalFilename', '$appName.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"@ | Set-Content -Encoding utf8 build\version_info.txt

# --- PyInstaller ---------------------------------------------------------------
$distDir = Join-Path $root "dist\$appName"
if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }
Get-ChildItem dist -File -ErrorAction SilentlyContinue | Remove-Item -Force
$pyiArgs = @("--noconfirm", "--clean", "--windowed", "--name", $appName,
    "--icon", "$root\assets\icon.ico", "--version-file", "$root\build\version_info.txt",
    "--add-data", "$root\assets;assets",
    "--add-binary", "$root\bin\ffmpeg.exe;bin", "--add-binary", "$root\bin\yt-dlp.exe;bin",
    "--exclude-module", "numpy", "--exclude-module", "PIL")

& $python -m compileall -q radiostreamer RadioStreamer.py
if ($LASTEXITCODE -ne 0) { throw "source does not compile" }

function Test-Build([string]$exe, [string]$name) {
    $report = Join-Path $root "build\selftest-$name.txt"
    $p = Start-Process -FilePath $exe -ArgumentList "--selftest", "`"$report`"" -Wait -PassThru
    if ($p.ExitCode -ne 0) { Get-Content $report -ErrorAction SilentlyContinue; throw "$name build failed its self-test" }
    Write-Host "Self-test passed ($name)" -ForegroundColor Green
}

# one-folder build (used by the installer and the portable zip)
& $python -m PyInstaller @pyiArgs --distpath "$root\dist" --workpath "$root\build\work" `
    --specpath "$root\build\work" RadioStreamer.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller (one-folder) failed" }
Copy-Item README.md, CHANGELOG.md, LICENSE, THIRD-PARTY-NOTICES.md $distDir
if (Test-Path bin\FFMPEG-LICENSE.txt) { Copy-Item bin\FFMPEG-LICENSE.txt $distDir }
Test-Build (Join-Path $distDir "$appName.exe") "one-folder"

# standalone single-file exe (unpacks to %TEMP% on each launch, so it starts a few seconds slower)
if (-not $NoStandalone) {
    & $python -m PyInstaller @pyiArgs --onefile --distpath "$root\build\onefile" `
        --workpath "$root\build\work-onefile" --specpath "$root\build\work-onefile" RadioStreamer.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller (standalone) failed" }
    Move-Item -Force "$root\build\onefile\$appName.exe" "$root\dist\3DX-Radio-Streamer-$version-win64-standalone.exe"
    Test-Build "$root\dist\3DX-Radio-Streamer-$version-win64-standalone.exe" "standalone"
    Write-Host "Standalone exe: dist\3DX-Radio-Streamer-$version-win64-standalone.exe" -ForegroundColor Green
}

# --- Package -----------------------------------------------------------------
if (-not $NoZip) {
    $zipOut = Join-Path $root "dist\3DX-Radio-Streamer-$version-win64-portable.zip"
    if (Test-Path $zipOut) { Remove-Item $zipOut }
    Write-Host "Zipping..."
    # Python's zipfile writes standard '/' paths (PowerShell 5's Compress-Archive writes '\', which
    # breaks some unzip tools)
    & $python -c "import shutil,sys; shutil.make_archive(sys.argv[1][:-4], 'zip', sys.argv[2], sys.argv[3])" `
        $zipOut (Join-Path $root "dist") $appName
    if ($LASTEXITCODE -ne 0) { throw "zip failed" }
    Write-Host "Portable zip: $zipOut" -ForegroundColor Green
}
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc /Q "/DAppVersion=$version" "/DSourceDir=$distDir" "/O$root\dist" build\installer.iss
    if ($LASTEXITCODE -eq 0) { Write-Host "Installer built in dist\" -ForegroundColor Green }
} else {
    Write-Host "Inno Setup 6 not found - skipped the installer." -ForegroundColor Yellow
}

# --- Checksums -----------------------------------------------------------------
$sums = Get-ChildItem dist -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" } | ForEach-Object {
    "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
}
# LF line endings so `sha256sum -c SHA256SUMS.txt` works everywhere
[IO.File]::WriteAllText((Join-Path $root "dist\SHA256SUMS.txt"), (($sums -join "`n") + "`n"))
Write-Host "Done:" -ForegroundColor Green
Get-ChildItem dist -File | ForEach-Object { "  {0,-55} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB) }

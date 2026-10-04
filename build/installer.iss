; Inno Setup 6 script - built by build.ps1 (pass /DAppVersion=x.y.z /DSourceDir=<dist folder>)
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\3DX Radio Streamer"
#endif

[Setup]
AppId={{6F1C2B7A-3D58-4E8B-9A57-2C41E7A0B3D9}
AppName=3DX Radio Streamer
AppVersion={#AppVersion}
AppPublisher=3DX Radio Streamer
DefaultDirName={autopf}\3DX Radio Streamer
DefaultGroupName=3DX Radio Streamer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputBaseFilename=3DX-Radio-Streamer-{#AppVersion}-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\3DX Radio Streamer.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\3DX Radio Streamer"; Filename: "{app}\3DX Radio Streamer.exe"
Name: "{autodesktop}\3DX Radio Streamer"; Filename: "{app}\3DX Radio Streamer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\3DX Radio Streamer.exe"; Description: "{cm:LaunchProgram,3DX Radio Streamer}"; Flags: nowait postinstall skipifsilent

; Inno Setup script. The release workflow passes /DAppVersion=x.y.z.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId=ZunimiLabs.ClipStudio
AppName=Clip Studio
AppVersion={#AppVersion}
AppVerName=Clip Studio {#AppVersion}
AppPublisher=ZUNIMILABS
DefaultDirName={autopf}\Clip Studio
DefaultGroupName=Clip Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=ClipStudio-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\ClipStudio.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Files]
Source: "dist\ClipStudio\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "NOTICE.txt"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; Old program files must not mix with new ones. Streams, clips and settings live elsewhere and are safe.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Clip Studio"; Filename: "{app}\ClipStudio.exe"
Name: "{autodesktop}\Clip Studio"; Filename: "{app}\ClipStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ClipStudio.exe"; Description: "Start Clip Studio"; Flags: nowait postinstall skipifsilent

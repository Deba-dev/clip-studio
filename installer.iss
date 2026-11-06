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
Filename: "{app}\ClipStudio.exe"; Flags: nowait; Check: WizardSilent

[Code]
// Waits for the running app to close before any file is touched. A file still in use would leave half an update behind.
function AppIsRunning(Args: String): Boolean;
var
  Code: Integer;
begin
  Result := False;
  if Exec(ExpandConstant('{sys}\taskkill.exe'), Args, '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Result := Code <> 128;      // 128 = no such program running
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  I: Integer;
begin
  Result := '';
  for I := 1 to 20 do begin
    if not AppIsRunning('/IM ClipStudio.exe') then begin
      Sleep(500);               // Windows needs a moment to let go of the files
      exit;
    end;
    Sleep(500);
  end;
  AppIsRunning('/F /T /IM ClipStudio.exe');
  Sleep(1500);
end;

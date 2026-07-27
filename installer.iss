; Inno Setup script for elAPI_Plugins.
; Compile from the repo root after building the .exe with build_windows.ps1:
;   ISCC installer.iss                     (defaults: version 1.2.0, x64)
;   ISCC /DAppVer=1.2.0 /DArch=x64 installer.iss   (override version/arch)

#ifndef AppVer
  #define AppVer "1.2.0"
#endif
#ifndef Arch
  #define Arch "x64"
#endif
#define AppExe "elAPI_Plugins_" + Arch + ".exe"

[Setup]
SourceDir={#SourcePath}
AppName=elAPI_Plugins
AppVersion={#AppVer}
AppPublisher=SFB-1638
AppPublisherURL=https://www.sfb1638.de/
DefaultDirName={autopf}\elAPI_Plugins
DefaultGroupName=elAPI_Plugins
OutputDir=dist\installer
OutputBaseFilename=elAPI_Plugins_{#Arch}_{#AppVer}_installer
Compression=zip
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
DisableProgramGroupPage=no
AllowNoIcons=yes
SetupIconFile=gui\assets\app.ico
UninstallDisplayIcon={app}\app.ico

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "gui\assets\app.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\elAPI_Plugins"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\app.ico"; IconIndex: 0
Name: "{userdesktop}\elAPI_Plugins"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\app.ico"; IconIndex: 0; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch elAPI_Plugins"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{userappdata}\elAPI_Plugins\*"

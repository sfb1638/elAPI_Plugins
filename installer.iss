[Setup]
SourceDir={#SourcePath}
AppName=elAPI_Plugins
AppVersion=1.0-beta
AppPublisher=SFB-1638
AppPublisherURL=https://www.sfb1638.de/
DefaultDirName={autopf}\elAPI_Plugins
DefaultGroupName=elAPI_Plugins
OutputDir=dist\installer
OutputBaseFilename=elAPI_Plugins_installer
Compression=zip
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
DisableProgramGroupPage=no
AllowNoIcons=yes
SetupIconFile=gui\assets\app.ico
UninstallDisplayIcon={app}\app.ico

[Files]
Source: "dist\elAPI_Plugins_x64.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "gui\assets\app.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\elAPI_Plugins"; Filename: "{app}\elAPI_Plugins_x64.exe"; WorkingDir: "{app}"; IconFilename: "{app}\app.ico"; IconIndex: 0
Name: "{userdesktop}\elAPI_Plugins"; Filename: "{app}\elAPI_Plugins_x64.exe"; WorkingDir: "{app}"; IconFilename: "{app}\app.ico"; IconIndex: 0; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Run]
Filename: "{app}\elAPI_Plugins_x64.exe"; Description: "Launch elAPI_Plugins"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{userappdata}\elAPI_Plugins\*"

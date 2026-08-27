#define MyAppName "MORICE"
#ifndef MyAppVersion
  #define MyAppVersion "0.8.0"
#endif
#define MyAppPublisher "EONASH2722"
#define MyAppExeName "MORICE.exe"
#define MyAppSourceDir "..\dist\MORICE"

[Setup]
AppId={{6DD56E2B-7D4C-4D69-B8A8-204BA7B22D72}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\MORICE
DefaultGroupName=MORICE
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=MORICE-Setup-v{#MyAppVersion}-Windows-x64
SetupIconFile=..\morice\assets\morice_logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/fast
SolidCompression=yes
DiskSpanning=yes
DiskSliceSize=2100000000
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AppMutex=MORICE.Desktop.Platform
VersionInfoVersion=0.8.0.0
VersionInfoDescription=MORICE desktop AI platform
VersionInfoProductName=MORICE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\MORICE"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\MORICE"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MORICE Wake Listener"; ValueData: """{app}\{#MyAppExeName}"" --morice-wake-listener"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--morice-wake-listener"; Description: "Start MORICE background wake listener"; Flags: nowait postinstall skipifsilent runhidden
Filename: "{app}\{#MyAppExeName}"; Description: "Launch MORICE"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

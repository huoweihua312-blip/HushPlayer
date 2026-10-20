; HushPlayer installer (Inno Setup 6).
; Per-user by default: installs into %LOCALAPPDATA%\Programs\HushPlayer and
; needs no administrator rights. User data lives in a separate directory and is
; intentionally left in place when uninstalling.

#define AppName "HushPlayer"
#define AppVersion "1.1.1"
#define AppExe "HushPlayer.exe"
#define AppId "{{6F1C2B7E-3A4D-4E5B-9C8A-2D1E0B7F4A21}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=HushPlayer
VersionInfoVersion={#AppVersion}
VersionInfoDescription=HushPlayer installer
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=F:\HushPlayerBuild\out
OutputBaseFilename=HushPlayer-{#AppVersion}-setup
SetupIconFile=..\assets\hushplayer.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes
DisableWelcomePage=no

[Languages]
; Inno ships no Simplified Chinese translation; keep the wizard in English so
; the installer never depends on an unofficial .isl file.
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start HushPlayer when I sign in to Windows"; GroupDescription: "启动选项"; Flags: unchecked

[Files]
Source: "F:\HushPlayerBuild\out\HushPlayer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: autostart

[Registry]
Root: HKCU; Subkey: "Software\HushPlayer"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\HushPlayer"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only the program directory; %LOCALAPPDATA%\HushPlayerReimagined (library,
; playlists, settings, cache) is kept so re-installing keeps the user's data.
Type: filesandordirs; Name: "{app}\Data"

; HushPlayer installer (Inno Setup 6).
; Per-user by default: installs into %LOCALAPPDATA%\Programs\HushPlayer and
; needs no administrator rights. User data lives in a separate directory and is
; intentionally left in place when uninstalling.

#define AppName "HushPlayer"
#define AppVersion "1.1.18"
#define AppExe "HushPlayer.exe"
#define AppId "{{6F1C2B7E-3A4D-4E5B-9C8A-2D1E0B7F4A21}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=HushPlayer
VersionInfoVersion={#AppVersion}
VersionInfoDescription=HushPlayer 安装程序
DefaultDirName={code:PreviousDir}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; The page exists on every run, but ShouldSkipPage() hides it on upgrades
; unless the welcome-page checkbox asks for it; DisableDirPage=auto would
; remove the page before ShouldSkipPage() ever runs.
DisableDirPage=no
UsePreviousAppDir=yes
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
; Vendored from the official Inno Setup repository (Files/Languages), BOM added.
; Only Chinese is listed so the wizard never asks the user to pick a language.
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"

[CustomMessages]
CreateDesktopIcon=创建桌面快捷方式(&D)
AdditionalIcons=附加快捷方式：
LaunchProgram=运行 %1

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "登录 Windows 时自动启动 HushPlayer"; GroupDescription: "启动选项"; Flags: unchecked

[Files]
Source: "F:\HushPlayerBuild\out\HushPlayer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: autostart

[Registry]
Root: HKCU; Subkey: "Software\HushPlayer"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"
Root: HKCU; Subkey: "Software\HushPlayer"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only the program directory; %LOCALAPPDATA%\HushPlayerReimagined (library,
; playlists, settings, cache) is kept so re-installing keeps the user's data.
; PyInstaller's runtime folder and the updater helper are recreated on every
; install, so an upgrade can leave copies the original uninstall log never saw.
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\HushPlayerUpdater.exe"
Type: filesandordirs; Name: "{app}\Data"

[Code]
function PreviousInstallDir(): String;
var
  value: String;
  marker: String;
begin
  Result := '';
  { 1) our own record, kept even after uninstall so "next install" remembers }
  if RegQueryStringValue(HKCU, 'Software\HushPlayer', 'InstallDir', value) then
    Result := value;
  { 2) the running app writes its folder here, which survives uninstall and
       also works for portable copies that were never installed }
  if Result = '' then
  begin
    marker := ExpandConstant('{localappdata}\HushPlayerReimagined\last_program_dir.ini');
    if FileExists(marker) then
      Result := GetIniString('install', 'dir', '', marker);
  end;
  { 3) Inno's own uninstall record for this AppId }
  if Result = '' then
  begin
    if RegQueryStringValue(
         HKCU,
         'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1',
         'InstallLocation', value) then
      Result := value;
  end;
  { Do not require the folder to exist: a moved/cleaned folder is still the
    user's last choice, and Inno recreates whatever is missing. }
  Result := Trim(Result);
end;

function PreviousDir(Param: String): String;
var
  remembered: String;
begin
  remembered := PreviousInstallDir();
  if remembered = '' then
    remembered := ExpandConstant('{localappdata}\Programs\{#AppName}');
  Result := remembered;
end;

procedure InitializeWizard();
var
  previous: String;
begin
  { Tell the user on the welcome page what Next will do. }
  previous := PreviousInstallDir();
  if (previous <> '') and (ExpandConstant('{param:DIR|}') = '') then
  begin
    WizardForm.WelcomeLabel2.Caption :=
      WizardForm.WelcomeLabel2.Caption + #13#10 + #13#10 +
      '升级安装：将覆盖到上次目录 ' + previous + '；如需更换，可在下一步修改。';
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
var
  previous: String;
begin
  { Inno fills the destination box with its own record (or the default) when the
    page is shown, which would overwrite anything set in InitializeWizard.
    Re-apply our remembered folder after the page has been prepared. }
  if CurPageID = wpSelectDir then
  begin
    { An explicit /DIR (or a manual folder) must win over our memory. }
    if ExpandConstant('{param:DIR|}') = '' then
    begin
      previous := PreviousInstallDir();
      if previous <> '' then
        WizardForm.DirEdit.Text := previous;
    end;
  end;
end;

#define MyAppName "HushPlayer"
#define MyAppPublisher "HushPlayer Project"
#define MyAppExeName "HushPlayer.exe"

#ifndef MyAppVersion
  #error MyAppVersion must be supplied by build_windows_installer.ps1
#endif
#ifndef MyAppNumericVersion
  #error MyAppNumericVersion must be supplied by build_windows_installer.ps1
#endif
#ifndef MyAppArchitecture
  #error MyAppArchitecture must be supplied by build_windows_installer.ps1
#endif

[Setup]
; 这个 AppId 以后所有 HushPlayer 更新版本都不要修改
AppId={{8A9C184E-32A0-4D9E-A3D4-51C492A5D7B6}

AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}

; Windows 文件属性要求纯数字版本
VersionInfoVersion={#MyAppNumericVersion}
VersionInfoDescription=HushPlayer Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppNumericVersion}
VersionInfoProductTextVersion={#MyAppVersion}

; 当前用户安装，不弹管理员权限确认
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
UsePreviousAppDir=yes

; HushPlayer 当前只发布 Windows x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; 安装包输出位置
OutputDir=..\..\dist\installer
OutputBaseFilename=HushPlayer-{#MyAppVersion}-{#MyAppArchitecture}-setup

SetupIconFile=..\..\assets\icons\HushPlayer.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

DisableProgramGroupPage=yes
DisableWelcomePage=no
AllowNoIcons=yes

; 更新时检测正在运行的 HushPlayer
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; \
    Description: "创建桌面快捷方式"; \
    GroupDescription: "附加选项："; \
    Flags: unchecked

[Files]
Source: "..\..\dist\HushPlayer\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\HushPlayer"; \
    Filename: "{app}\{#MyAppExeName}"; \
    WorkingDir: "{app}"

Name: "{userdesktop}\HushPlayer"; \
    Filename: "{app}\{#MyAppExeName}"; \
    WorkingDir: "{app}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "启动 HushPlayer"; \
    WorkingDir: "{app}"; \
    Flags: nowait postinstall skipifsilent

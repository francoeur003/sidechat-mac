#define AppVersion "0.3.0"
[Setup]
AppId={{173CB92F-C89C-4C65-BE1D-47F09A48317F}
AppName=SideChat
AppVersion={#AppVersion}
AppPublisher=SideChat Community
AppPublisherURL=https://github.com/francoeur003/sidechat-mac
DefaultDirName={localappdata}\Programs\SideChat
DefaultGroupName=SideChat
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=SideChat-{#AppVersion}-Windows-x64-Setup
SetupIconFile=..\assets\SideChat.ico
UninstallDisplayIcon={app}\SideChat.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\LICENSE
InfoBeforeFile=..\docs\Windows安装说明.txt
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\dist\SideChat\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\SideChat"; Filename: "{app}\SideChat.exe"
Name: "{autodesktop}\SideChat"; Filename: "{app}\SideChat.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\SideChat.exe"; Description: "Launch SideChat"; Flags: nowait postinstall skipifsilent

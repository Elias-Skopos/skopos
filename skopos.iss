#ifndef BundleDir
  #error BundleDir required
#endif
#ifndef OutputDir
  #error OutputDir required
#endif
#ifndef AppVersion
  #define AppVersion "0.1.4"
#endif
[Setup]
AppId={{A5A9DC11-739D-46B8-9F24-E55CD84E5063}
AppName=Skopos
AppVersion={#AppVersion}
AppPublisher=Skopos
DefaultDirName={localappdata}\Programs\Skopos
DefaultGroupName=Skopos
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=Skopos-Setup-{#AppVersion}-windows-x64
SetupIconFile=..\assets\skopos_desktop_novo.ico
UninstallDisplayIcon={app}\Skopos.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
[Tasks]
Name: "desktopicon"; Description: "Criar atalho Skopos que abre no navegador padrão"; GroupDescription: "Atalhos:"
[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\Skopos"; Filename: "{app}\Skopos.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Skopos.exe"; Comment: "Inicia o servidor local e abre o Skopos no navegador padrão"
Name: "{autodesktop}\Skopos"; Filename: "{app}\Skopos.exe"; WorkingDir: "{app}"; IconFilename: "{app}\Skopos.exe"; Comment: "Inicia o servidor local e abre o Skopos no navegador padrão"; Tasks: desktopicon
[Run]
Filename: "{app}\Skopos.exe"; Description: "Abrir Skopos"; Flags: nowait postinstall skipifsilent
; Private data is outside {app}, in %LOCALAPPDATA%\Skopos\Data.
; No [UninstallDelete] rule: uninstall preserves the database and backups.

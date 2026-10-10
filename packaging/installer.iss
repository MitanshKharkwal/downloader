[Setup]
AppName=Downloader
AppVersion=1.1.0
VersionInfoVersion=1.1.0.0
AppPublisher=MitanshKharkwal
AppPublisherURL=https://github.com/MitanshKharkwal/downloader
AppSupportURL=https://github.com/MitanshKharkwal/downloader/issues
AppUpdatesURL=https://github.com/MitanshKharkwal/downloader/releases
DefaultDirName={autopf}\Downloader
DefaultGroupName=Downloader
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=DownloaderSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\flutter_ui.exe

[Files]
Source: "..\packaging\dist\downloader-daemon.exe"; DestDir: "{app}"
Source: "..\packaging\dist\downloader-native-host.exe"; DestDir: "{app}\native_host"
Source: "..\packaging\dist\register-native-host.exe"; DestDir: "{app}\native_host"
Source: "..\flutter_ui\build\windows\x64\runner\Release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\browser_extension\*"; DestDir: "{app}\browser_extension"; Excludes: "tests\*"; Flags: ignoreversion recursesubdirs
[Icons]
Name: "{group}\Downloader"; Filename: "{app}\flutter_ui.exe"
Name: "{group}\Uninstall Downloader"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "DownloaderDaemon"; ValueData: """{app}\downloader-daemon.exe"""; Flags: uninsdeletevalue

[Run]
Filename: "{app}\downloader-daemon.exe"; Description: "Start background service"; Flags: nowait postinstall skipifsilent
Filename: "{app}\flutter_ui.exe"; Description: "Launch Downloader"; Flags: nowait postinstall skipifsilent unchecked

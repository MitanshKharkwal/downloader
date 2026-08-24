[Setup]
AppName=Downloader
AppVersion=1.0.0
DefaultDirName={autopf}\Downloader
DefaultGroupName=Downloader
OutputDir=dist
OutputBaseFilename=DownloaderSetup

[Files]
Source: "..\packaging\dist\downloader-daemon.exe"; DestDir: "{app}"
Source: "..\packaging\dist\downloader-native-host.exe"; DestDir: "{app}\native_host"
Source: "..\packaging\dist\register-native-host.exe"; DestDir: "{app}\native_host"

[Icons]
Name: "{group}\Downloader"; Filename: "{app}\flutter_ui.exe"
Name: "{group}\Uninstall Downloader"; Filename: "{uninstallexe}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "DownloaderDaemon"; ValueData: """{app}\downloader-daemon.exe"""; Flags: uninsdeletevalue

[Run]
Filename: "{app}\downloader-daemon.exe"; Description: "Start background service"; Flags: nowait postinstall skipifsilent
Filename: "{app}\flutter_ui.exe"; Description: "Launch Downloader"; Flags: nowait postinstall skipifsilent unchecked

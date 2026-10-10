# Packaging Instructions

Run these commands from the repository root on Windows. The build requires the
project virtual environment, Flutter with Windows desktop support, and Inno
Setup 7.

1. Build the Flutter UI so both packages receive the latest interface:

```powershell
& C:\src\flutter\bin\flutter.bat build windows --release --build-name 1.1.0 --build-number 2
```

2. Build the daemon and browser native-host utilities:

```powershell
venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\daemon.spec --distpath packaging\dist --workpath packaging\build
venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\native_host.spec --distpath packaging\dist --workpath packaging\build
```

3. Build the self-contained portable application:

```powershell
venv\Scripts\pyinstaller.exe --noconfirm --clean packaging\portable.spec --distpath packaging\dist --workpath packaging\build
```

4. Build the installer:

```powershell
& 'C:\Program Files\Inno Setup 7\ISCC.exe' packaging\installer.iss
```

The distributable outputs are `packaging/dist/Downloader.exe` and
`packaging/dist/DownloaderSetup.exe`. The installer also includes the browser
extension and the native messaging registration utility.

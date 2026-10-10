# Packaging Instructions

Run these commands from the repository root on Windows. The build requires the
project virtual environment, Flutter with Windows desktop support, and Inno
Setup 7.

1. Build the Flutter UI so both packages receive the latest interface:

```powershell
& C:\src\flutter\bin\flutter.bat build windows --release --build-name 1.2.0 --build-number 3
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

## Signed releases and automatic updates

The `Signed Windows release` workflow builds releases for `v*` tags. Configure
these GitHub Actions secrets before creating a tag:

- `WINDOWS_CERTIFICATE`: the Base64-encoded contents of a trusted code-signing
  `.pfx` certificate.
- `WINDOWS_CERTIFICATE_PASSWORD`: the password for that certificate.

The workflow signs every executable and the installer, then publishes
`DownloaderSetup.exe`, `Downloader.exe`, and `SHA256SUMS.txt`. The in-app
updater refuses a package unless its SHA-256 matches the manifest and Windows
reports a valid trusted publisher signature.

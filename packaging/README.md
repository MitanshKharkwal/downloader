# Packaging Instructions

1. **Build Python Daemon**:
```bash
venv\Scripts\pyinstaller packaging/daemon.spec --distpath packaging/dist --workpath packaging/build
```

2. **Build Flutter App**:
```bash
cd flutter_ui
flutter build windows --release
cd ..
```

3. **Build Installer**:
```bash
iscc packaging/installer.iss
```
(Requires Inno Setup installed: https://jrsoftware.org/isinfo.php)

Output will be in `packaging/dist/DownloaderSetup.exe`.

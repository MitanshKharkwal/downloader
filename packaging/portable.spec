# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
import os

datas = []
binaries = []
hiddenimports = [
    'yt_dlp.extractor',
    'win11toast'
]

tmp_ret = collect_all('libtorrent')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# Include the Flutter build output
flutter_release_dir = os.path.abspath(os.path.join(SPECPATH, '..', 'flutter_ui', 'build', 'windows', 'x64', 'runner', 'Release'))
datas.append((flutter_release_dir, 'flutter_ui_bundle'))

a = Analysis(
    [os.path.join(SPECPATH, '..', 'portable_launcher.py')],
    pathex=[os.path.join(SPECPATH, '..')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Downloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # Set to False to hide the console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None # You can add an icon here if needed
)

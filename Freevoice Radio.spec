# -*- mode: python ; coding: utf-8 -*-
#
# Freevoice Radio is built as an ONEDIR bundle on purpose.
#
# The previous one-file build had to unpack itself into %TEMP% before any of
# our code ran.  On machines where %TEMP% is restricted (or antivirus blocks
# unsigned executables writing there) that fails with
# "Could not create temporary directory!" and the app never starts.
# An onedir bundle runs in place, needs no temp folder, and starts faster.

import os

# Static resources. 'assets' is optional so the build does not fail if the
# folder has not been created yet.
datas = [("src", "src")]
if os.path.isdir("assets"):
    datas.append(("assets", "assets"))

# QtMultimedia is imported lazily inside src/audio/backends.py.
hiddenimports = [
    "PyQt6.QtMultimedia",
    "PyQt6.QtMultimediaWidgets",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pygame", "pydub", "numpy", "scipy", "matplotlib"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Freevoice Radio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/freevoice.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Freevoice Radio",
)

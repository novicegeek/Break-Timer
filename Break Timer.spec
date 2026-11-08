# -*- mode: python ; coding: utf-8 -*-
import struct
import os

# Pre-build: wrap timer.png as timer.ico
_png = "timer.png"
_ico = "timer.ico"
if os.path.exists(_png) and not os.path.exists(_ico):
    with open(_png, "rb") as f:
        d = f.read()
    buf = struct.pack("<HHH", 0, 1, 1)
    buf += struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(d), 22)
    buf += d
    with open(_ico, "wb") as f:
        f.write(buf)

a = Analysis(
    ["timer.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("index.html", "."),
        ("alert.html", "."),
        ("timer.png", "."),
    ],
    hiddenimports=[
        "webview",
        "bottle",
        "proxy_tools",
    ],
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
    name="Break Timer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ico if os.path.exists(_ico) else _png,
)

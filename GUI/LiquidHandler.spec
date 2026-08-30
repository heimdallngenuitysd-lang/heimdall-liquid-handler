# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

datas = [("configs", "configs"), ("assets", "assets")]
icon_file = "assets/logo.ico"
if sys.platform == "darwin" and os.path.exists("assets/logo.icns"):
    icon_file = "assets/logo.icns"
binaries = []
hiddenimports = [
    "serial",
    "serial.tools.list_ports",
    "cv2",
    "yaml",
    "spatialmath",
    "matplotlib",
    "matplotlib.backends.backend_tkagg",
    "dotenv",
    "google.genai",
    "numpy",
    "PIL",
    "scipy",
    "tkinter",
    "_tkinter",
    "zmq",
    "pymodbus",
    "pymodbus.client",
]

for pkg in ("cv2", "spatialmath", "google", "matplotlib", "zmq", "pymodbus"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LiquidHandler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=icon_file if os.path.exists(icon_file) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LiquidHandler",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="LiquidHandler.app",
        icon=icon_file if os.path.exists(icon_file) else None,
        bundle_identifier="com.selfdrivinglab.liquidhandler",
        info_plist={
            "NSCameraUsageDescription": (
                "Liquid Handler uses the camera to list available devices "
                "and to read pipette volume during volume adjustment."
            ),
        },
    )

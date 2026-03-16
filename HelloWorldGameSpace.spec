# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path.cwd()

block_cipher = None

datas = [
    (str(project_root / "testing" / "game_logic"), "testing/game_logic"),
    (str(project_root / "testing" / "Battleship"), "testing/Battleship"),
    (str(project_root / "testing" / "apples" / "apples_min.db"), "testing/apples"),
    (str(project_root / "tts.py"), "."),
]

hiddenimports = [
    "customtkinter",
    "pygame",
    "pygame.sndarray",
    "numpy",
    "numpy.typing",
    "pyttsx3",
    "win32com",
    "win32com.client",
    "pythoncom",
    "comtypes",
]

a = Analysis(
    ["launch_gamespace.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HelloWorldGameSpace",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HelloWorldGameSpace",
)

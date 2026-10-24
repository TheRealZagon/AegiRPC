# -*- mode: python ; coding: utf-8 -*-
# Build with: pyinstaller AegiRPC.spec  (the Windows exe has to be built on Windows)
import sys

windows = sys.platform == 'win32'

a = Analysis(
    ['aegi_rpc.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['gui'],
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
    name='AegiRPC' if windows else 'aegi_rpc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=not windows,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'] if windows else None,
)

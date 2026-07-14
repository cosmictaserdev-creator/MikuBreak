# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assests', 'assests'), ('font', 'font')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# This venv runs on a uv-managed Python 3.14.4, not the system Python.
# Two files named libssl-3-x64.dll / libcrypto-3-x64.dll exist on this
# machine -- the correct one next to _ssl.pyd under the uv Python's own
# DLLs folder, and an unrelated one in Git's MinGW bin. PyInstaller's
# dependency scan grabs the MinGW copy (earlier on PATH), which doesn't
# match _ssl.pyd's build, crashing the packaged EXE with
# "DLL load failed while importing _ssl: procedure not found".
# Force the DLLs that actually match this interpreter.
import os
_PY_DLLS = r'C:\Users\cosmi\AppData\Roaming\uv\python\cpython-3.14.4-windows-x86_64-none\DLLs'
_correct_ssl = {name: os.path.join(_PY_DLLS, name)
                for name in ('_ssl.pyd', 'libssl-3-x64.dll', 'libcrypto-3-x64.dll')}
a.binaries = [b for b in a.binaries if os.path.basename(b[0]) not in _correct_ssl]
a.binaries += [(name, path, 'BINARY') for name, path in _correct_ssl.items()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='mikuBreak',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        'libssl-3.dll', 'libssl-3-x64.dll',
        'libcrypto-3.dll', 'libcrypto-3-x64.dll',
        '_ssl.pyd', '_hashlib.pyd',
        'python311.dll', 'python3.dll',
        'vcruntime140.dll', 'vcruntime140_1.dll',
    ],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assests\\appIcon.png'],
)

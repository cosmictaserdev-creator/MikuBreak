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

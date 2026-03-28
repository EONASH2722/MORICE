# -*- mode: python ; coding: utf-8 -*-


import os

project_dir = os.path.abspath(SPECPATH)

a = Analysis(
    [os.path.join(project_dir, 'morice_app_launcher.py')],
    pathex=[project_dir],
    binaries=[],
    datas=[
        (os.path.join(project_dir, 'morice', 'assets', 'morice_logo.ico'), 'morice\\assets'),
        (os.path.join(project_dir, 'morice', 'assets', 'Meta-Llama-3.1-8B-Instruct-Q5_K_M.gguf'), 'morice\\assets'),
        (os.path.join(project_dir, 'morice', 'assets', 'llama-bin'), 'morice\\assets\\llama-bin'),
        (os.path.join(project_dir, 'morice', 'assets', 'tesseract'), 'morice\\assets\\tesseract'),
    ],
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
    [],
    exclude_binaries=True,
    name='MORICE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(project_dir, 'morice', 'assets', 'morice_logo.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MORICE',
)

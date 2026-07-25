# -*- mode: python ; coding: utf-8 -*-


import os

project_dir = os.path.abspath(SPECPATH)
model_candidates = [
    os.path.join(project_dir, 'Qwen2.5-Coder-7B-Instruct-abliterated-Q4_K_M.gguf'),
    os.path.join(project_dir, 'qwen2.5-coder-7b-instruct-q4_k_m.gguf'),
]
bundled_model = next((path for path in model_candidates if os.path.isfile(path)), None)
if not bundled_model:
    raise SystemExit('Install a Qwen2.5 Coder 7B GGUF before packaging MORICE.')

a = Analysis(
    [os.path.join(project_dir, 'morice_app_launcher.py')],
    pathex=[project_dir],
    binaries=[],
    datas=[
        (os.path.join(project_dir, 'morice', 'assets', 'morice_logo.ico'), 'morice\\assets'),
        (os.path.join(project_dir, 'morice', 'assets', 'morice_logo.png'), 'morice\\assets'),
        (os.path.join(project_dir, 'morice', 'assets', 'web'), 'morice\\assets\\web'),
        (bundled_model, 'morice\\assets'),
        (os.path.join(project_dir, 'morice', 'assets', 'llama-bin'), 'morice\\assets\\llama-bin'),
        (os.path.join(project_dir, 'morice', 'assets', 'OCR_NOTES.md'), 'morice\\assets'),
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

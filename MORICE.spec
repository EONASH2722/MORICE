# -*- mode: python ; coding: utf-8 -*-


import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

project_dir = os.path.abspath(SPECPATH)
model_candidates = [
    os.path.join(project_dir, 'Parable-Qwen3-4B-Claude-Fable-5-GGUF-Q5_K_M.gguf'),
    os.path.join(project_dir, 'Qwen2.5-Coder-7B-Instruct-abliterated-Q4_K_M.gguf'),
    os.path.join(project_dir, 'qwen2.5-coder-7b-instruct-q4_k_m.gguf'),
]
bundled_model = next((path for path in model_candidates if os.path.isfile(path)), None)
if not bundled_model:
    raise SystemExit('Install a Qwen2.5 Coder 7B GGUF before packaging MORICE.')
vosk_binaries = collect_dynamic_libs('vosk')
voice_model = os.path.join(project_dir, 'voice_models', 'vosk-model-small-en-us-0.15')
vision_roots = [
    os.environ.get('MORICE_LOCAL_DATA_DIR', '').strip(),
    r'E:\MORICE_DATA',
    os.path.join(os.environ.get('LOCALAPPDATA', ''), 'MORICE'),
]
vision_files = None
for vision_root in (path for path in vision_roots if path):
    candidate_root = os.path.join(
        vision_root,
        'models',
        'vision',
        'SmolVLM2-500M-Video-Instruct-GGUF',
    )
    candidate_model = os.path.join(
        candidate_root, 'SmolVLM2-500M-Video-Instruct-Q8_0.gguf'
    )
    candidate_projector = os.path.join(
        candidate_root, 'mmproj-SmolVLM2-500M-Video-Instruct-Q8_0.gguf'
    )
    if os.path.isfile(candidate_model) and os.path.isfile(candidate_projector):
        vision_files = (candidate_model, candidate_projector)
        break
data_files = [
    (os.path.join(project_dir, 'morice', 'assets', 'morice_logo.ico'), 'morice\\assets'),
    (os.path.join(project_dir, 'morice', 'assets', 'morice-logo-rgb.png'), 'morice\\assets'),
    (os.path.join(project_dir, 'morice', 'assets', 'web'), 'morice\\assets\\web'),
    (bundled_model, 'morice\\assets'),
    (os.path.join(project_dir, 'third_party', 'llama-win-cpu'), 'morice\\assets\\llama-bin'),
]
if os.path.isdir(voice_model):
    data_files.append((voice_model, 'voice_models\\vosk-model-small-en-us-0.15'))
if vision_files:
    for vision_file in vision_files:
        data_files.append((vision_file, 'morice\\assets\\vision'))

a = Analysis(
    [os.path.join(project_dir, 'morice_app_launcher.py')],
    pathex=[project_dir],
    binaries=vosk_binaries,
    datas=data_files,
    hiddenimports=(
        ['morice.plugin_host', 'morice_wake_listener', 'dotenv', 'websockets']
        + collect_submodules('elevenlabs')
        + collect_submodules('winrt')
        + collect_submodules('uiautomation')
        + collect_submodules('pycaw')
        + collect_submodules('comtypes')
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# The Codex desktop runtime adds Poppler's private ICU build to PATH.  QtCore
# links against Windows' system ``icuuc.dll``; collecting Poppler's unrelated
# DLL under that same name makes the frozen app fail before the first window
# opens with WinError 127.  Keep those host-only ICU binaries out of the
# portable build so Windows resolves the API-compatible system ICU instead.
_host_icu_dlls = {'icuuc.dll', 'icudt78.dll'}
a.binaries = type(a.binaries)(
    entry for entry in a.binaries if os.path.basename(entry[0]).casefold() not in _host_icu_dlls
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
    version=os.path.join(project_dir, 'installer', 'version_info.txt'),
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

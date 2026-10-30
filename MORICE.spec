# -*- mode: python ; coding: utf-8 -*-


import os
import hashlib
from pathlib import Path
from PyInstaller.config import CONF
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

project_dir = os.path.abspath(SPECPATH)
model_candidates = [
    os.path.join(project_dir, 'Parable-Qwen3-4B-Claude-Fable-5-GGUF-Q5_K_M.gguf'),
    os.path.join(project_dir, 'Qwen2.5-Coder-7B-Instruct-abliterated-Q4_K_M.gguf'),
    os.path.join(project_dir, 'qwen2.5-coder-7b-instruct-q4_k_m.gguf'),
]
bundled_model = next((path for path in model_candidates if os.path.isfile(path)), None)
bundle_models = os.environ.get('MORICE_BUNDLE_MODELS', '').strip().lower() in {'1', 'true', 'yes'}
if bundle_models and not bundled_model:
    raise SystemExit('MORICE_BUNDLE_MODELS requires an existing local GGUF.')
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
    (os.path.join(project_dir, 'morice', 'media_lab', 'worker.py'), 'morice\\media_lab'),
    (os.path.join(project_dir, 'morice', 'project_build', 'localtools.py'), 'morice\\project_build'),
    (os.path.join(project_dir, 'morice', 'assets', 'morice_logo.ico'), 'morice\\assets'),
    (os.path.join(project_dir, 'morice', 'assets', 'morice-logo-rgb.png'), 'morice\\assets'),
    (os.path.join(project_dir, 'morice', 'assets', 'web'), 'morice\\assets\\web'),
    (os.path.join(project_dir, 'morice', 'assets', 'pets'), 'morice\\assets\\pets'),
    (os.path.join(project_dir, 'morice', 'assets', 'spatial'), 'morice\\assets\\spatial'),
    (os.path.join(project_dir, 'third_party', 'llama-win-cpu'), 'morice\\assets\\llama-bin'),
]
if bundle_models:
    data_files.append((bundled_model, 'morice\\assets'))
if os.path.isdir(voice_model):
    data_files.append((voice_model, 'voice_models\\vosk-model-small-en-us-0.15'))
if bundle_models and vision_files:
    for vision_file in vision_files:
        data_files.append((vision_file, 'morice\\assets\\vision'))

# Pint loads its unit definitions from package data at runtime.
# Release builders install .[dev,research]; fail here if it is missing.
import pint
data_files += collect_data_files('pint')
data_files += collect_data_files('uiautomation')

a = Analysis(
    [os.path.join(project_dir, 'morice_app_launcher.py')],
    pathex=[project_dir],
    binaries=vosk_binaries,
    datas=data_files,
    hiddenimports=(
        ['morice.plugin_host', 'morice_wake_listener', 'dotenv', 'websockets']
        + collect_submodules('morice.kernel')
        + collect_submodules('morice.agent_runtime')
        + collect_submodules('morice.action_runtime')
        + collect_submodules('morice.project_build')
        + collect_submodules('morice.device_mesh')
        + collect_submodules('morice.research')
        + collect_submodules('morice.ambient')
        + collect_submodules('morice.connectors')
        + collect_submodules('morice.security')
        + collect_submodules('morice.security_lab')
        + collect_submodules('pyzipper')
        + collect_submodules('Cryptodome',filter=lambda name:not name.startswith('Cryptodome.SelfTest'))
        + collect_submodules('morice.media_lab')
        + collect_submodules('morice.spatial')
        + collect_submodules('morice.ui_next')
        + collect_submodules('geographiclib')
        + collect_submodules('elevenlabs')
        + collect_submodules('winrt')
        + collect_submodules('uiautomation')
        + collect_submodules('pycaw')
        + collect_submodules('comtypes', filter=lambda name: not name.startswith('comtypes.test'))
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
# Bind the Python archive name to application contents. A source edit during a
# previous build can otherwise leave a newer PYZ cache with older code objects.
# The normal Analysis dependency checks and final frozen-source parity still
# apply; a new content name forces PYZ to compile the current source.
source_digest = hashlib.sha256()
for source_path in sorted((Path(project_dir) / 'morice').rglob('*.py')):
    source_digest.update(str(source_path.relative_to(project_dir)).encode())
    source_digest.update(source_path.read_bytes())
# Analysis may retain older module-graph code objects after an incremental
# build. Compile application modules from the current checkout even when the
# dependency graph itself is reused. Final archive parity remains mandatory.
application_code_cache = CONF['code_cache'].get(id(a.pure))
if application_code_cache is not None:
    for module_name, module_path, module_type in a.pure:
        if module_name == 'morice' or module_name.startswith('morice.'):
            application_code_cache[module_name] = compile(Path(module_path).read_bytes(), module_path, 'exec', dont_inherit=True, optimize=0)
pyz = PYZ(a.pure, name=os.path.join(CONF['workpath'], 'PYZ-' + source_digest.hexdigest()[:16] + '.pyz'))

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

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# 1. Functional Module Collection (Top-Level Project Directories)
# We include these as datas to ensure they remain reachable in the frozen environment.
# Note: Subdirectories like 'world_model' or 'temporal' are included via 'core'.
datas = [
    ('interface/static', 'interface/static'), 
    ('core', 'core'),
    ('skills', 'skills'),
    ('utils', 'utils'),
    ('interface', 'interface'),
    ('infrastructure', 'infrastructure'),
    ('integration', 'integration'),
    ('llm', 'llm'),
    ('senses', 'senses'),
    ('prompts', 'prompts'),
    ('memory', 'memory'),
    ('optimizer', 'optimizer'),
    ('security', 'security'),
    ('storage', 'storage'),
    ('executors', 'executors'),
    ('cradle', 'cradle'),
    ('archives', 'archives'),
    ('data', 'data'),
]

binaries = []
hiddenimports = [
    'uvicorn.loops.auto', 
    'uvicorn.protocols.http.auto', 
    'websockets.legacy.server', 
    'websockets.legacy.client',
    'litellm', 
    'pydantic', 
    'pydantic_settings',
    'fastapi', 
    'jinja2', 
    'sentence_transformers', 
    'chromadb', 
    'cv2', 
    'pyautogui', 
    'pygetwindow', 
    'pywebview', 
    'aiosqlite', 
    'redis', 
    'psutil', 
    'httpx', 
    'aiohttp', 
    'aiofiles',
    'websockets', 
    'typing_extensions',
    'yaml',
    'numpy',
    'scipy',
    'PIL',
    'pyttsx3',
    'sounddevice',
    'pyaudio',
    'faster_whisper',
    'playwright',
    'netifaces',
    'opentelemetry.api',
    'opentelemetry.sdk',
    'opentelemetry.instrumentation',
    'onnx'
]

# 2. Third-Party Heavyweight Collection
complex_libs = [
    'torch', 'transformers', 'sentence_transformers', 'chromadb', 
    'cv2', 'pydantic', 'fastapi', 'webview', 'numpy', 'pandas', 
    'matplotlib', 'scipy', 'sklearn', 'onnxruntime', 'aiohttp', 'httpx'
]

for lib in complex_libs:
    try:
        tmp_ret = collect_all(lib)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

a = Analysis(
    ['aura_main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='Aura',
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
    icon=['aura_icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Aura',
)
app = BUNDLE(
    coll,
    name='Aura.app',
    icon='aura_icon.icns',
    bundle_identifier=None,
)

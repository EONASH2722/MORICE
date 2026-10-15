"""Keep older Qt tests' default-profile/runtime writes out of real user data."""
from pathlib import Path
import os
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

with tempfile.TemporaryDirectory(prefix='morice-isolated-tests-') as directory:
    root=Path(directory)
    os.environ.update(APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local'),MORICE_LOCAL_DATA_DIR=str(root/'data'),
        MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_NODE_NETWORK='0',MORICE_REDUCE_MOTION='1',QT_QPA_PLATFORM='offscreen',
        QT_QUICK_BACKEND='software',QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu')
    from morice import settings
    settings.save_settings({**settings.DEFAULT_SETTINGS,'pet_enabled':'false','tts_enabled':'false','stt_enabled':'false','model_path':''})
    import pytest
    try: result=pytest.main(sys.argv[1:])
    finally:
        import morice.runtime_services as runtime_module
        if runtime_module._RUNTIME_SERVICES is not None:
            runtime_module._RUNTIME_SERVICES.shutdown()
    sys.exit(result)

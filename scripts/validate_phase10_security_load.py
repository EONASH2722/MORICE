"""Real owned Security scan/Core state and existing resource-lease adaptation."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
output = ROOT/'build/phase10-security-load-current'; output.mkdir(parents=True, exist_ok=True)
digest = hashlib.sha256()
for path in sorted((ROOT/'morice').rglob('*.py')):
    digest.update(str(path.relative_to(ROOT)).encode()); digest.update(path.read_bytes())
with tempfile.TemporaryDirectory(prefix='morice-security-ui-') as directory:
    root = Path(directory)
    os.environ.update(APPDATA=str(root/'roaming'), LOCALAPPDATA=str(root/'local'),
        MORICE_RUNTIME_DIR=str(root/'runtime'), MORICE_LOCAL_DATA_DIR=str(root/'data'),
        MORICE_PRELOAD='0', MORICE_DISABLE_SESSION='1', MORICE_DISABLE_RECOVERY='1',
        MORICE_NODE_NETWORK='0', MORICE_REDUCE_MOTION='1', QT_QPA_PLATFORM='windows')
    from PySide6.QtWidgets import QApplication, QLabel
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from morice import settings
    import morice.runtime_services as services
    from morice.runtime_services import RuntimeServices
    from morice.pyside_app import create_application_window
    from morice.kernel import ResourceClaim
    from morice.kernel.resources import ResourceDescriptor
    from morice.ui_next.core_state import CoreState
    settings.save_settings({**settings.DEFAULT_SETTINGS, 'pet_enabled':'false', 'tts_enabled':'false', 'stt_enabled':'false'})
    app = QApplication([]); runtime = RuntimeServices(root/'runtime', project_root=ROOT)
    services._RUNTIME_SERVICES = runtime
    window = create_application_window(runtime, runtime.start()); window.show(); app.processEvents()
    record = {'source_sha256':digest.hexdigest(), 'scope':'Owned harmless file and actual existing Security/Kernel; controlled GPU lease admission is not physical GPU generation.'}
    try:
        window.navigate('security'); security = runtime.ambient.security
        assert not security.enabled and not runtime.kernel.dispatch('security.scan', {}).success
        selected = root/'selected'; selected.mkdir(); fixture = selected/'harmless.txt'
        fixture.write_text('Harmless, owned Phase 10 security fixture.', encoding='utf-8')
        file_digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
        security.enable(sources=('files',), directories=(selected,), user_confirmed=True)
        security.indicator(file_digest, 'local:owned-phase10-fixture', 'Explicit harmless test indicator', user_confirmed=True)
        result = runtime.kernel.dispatch('security.scan', {}); assert result.success
        deadline = time.monotonic()+5
        while window.core_presentation.snapshot.state != CoreState.SECURITY_ALERT and time.monotonic()<deadline: QTest.qWait(20)
        assert window.core_presentation.snapshot.state == CoreState.SECURITY_ALERT
        findings = security.snapshot()['findings']; finding = next(row for row in findings if row['category']=='KNOWN_HASH')
        window.navigate('home'); banner = QLabel('CONTROLLED HARMLESS SECURITY FIXTURE'); banner.setAlignment(Qt.AlignCenter)
        window.presentation_root.layout().insertWidget(1, banner); app.processEvents()
        assert window.grab().save(str(output/'controlled-security-alert.png'))
        record['finding_id'] = finding['finding_id']; record['core_alert_state'] = window.core_presentation.snapshot.state.value
        security.ignore(finding['finding_id'], 'Owned harmless fixture', user_confirmed=True)
        assert runtime.kernel.dispatch('security.scan', {}).success; security.disable()
        QTest.qWait(12500); window.core_presentation.sample()
        assert window.core_presentation.snapshot.state != CoreState.SECURITY_ALERT
        record['security_notice_expired_after_resolution'] = True
        window.theme_engine.update(quality='ULTRA', persist=False)
        runtime.kernel.resources.register(ResourceDescriptor('GPU'))
        assert runtime.kernel.resources.acquire('owned-ui-gpu-lease', (ResourceClaim('GPU'),))
        window._refresh_top_bar_status(); assert window.effect_policy.budget.effective == 'BALANCED'
        assert window.effect_policy.budget.selected == 'ULTRA'
        record['real_resource_lease_effective_quality'] = window.effect_policy.budget.effective
        runtime.kernel.resources.release('owned-ui-gpu-lease'); window._refresh_top_bar_status()
        assert window.effect_policy.budget.effective == 'ULTRA'
        record['lease_release_restores_selected_quality'] = True
    finally:
        runtime.kernel.resources.release('owned-ui-gpu-lease')
        window.close(); app.processEvents(); runtime.shutdown()
    record['shutdown'] = runtime.shutdown_report; assert record['shutdown']['clean']
    record['status'] = 'OWNED_SECURITY_AND_LEASE_UI_PASSED'
    (output/'evidence.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record), flush=True)

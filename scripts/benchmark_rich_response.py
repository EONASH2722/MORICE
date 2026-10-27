"""Measured native chat rendering with actual user data and isolated profiles.

No model is called, no downloads occur, and no normal user profile is opened.
This is a controlled renderer workload, not a GPU/inference stress certificate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='build/rich-response-benchmark.json')
    parser.add_argument('--messages',type=int,default=100);args=parser.parse_args()
    if not 10<=args.messages<=200:raise ValueError('Use 10–200 controlled rich response messages.')
    with tempfile.TemporaryDirectory(prefix='morice-rich-benchmark-') as directory:
        root=Path(directory)
        os.environ.update(APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local'),MORICE_LOCAL_DATA_DIR=str(root/'data'),
            MORICE_PRELOAD='0',MORICE_DISABLE_SESSION='1',MORICE_DISABLE_RECOVERY='1',MORICE_NODE_NETWORK='0',
            MORICE_WEB='0',MORICE_REDUCE_MOTION='1',MORICE_START_AWAKE='1',QT_QPA_PLATFORM='offscreen',
            QT_QUICK_BACKEND='software',QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu')
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        from PySide6.QtTest import QTest
        import psutil
        from morice import settings
        import morice.runtime_services as module
        from morice.runtime_services import RuntimeServices
        from morice.pyside_app import create_application_window
        from morice.rich_response import Component,ResponsePlan,SourceRef
        from morice.premium_experience import MAX_VISIBLE_CHAT_WIDGETS
        settings.save_settings({**settings.DEFAULT_SETTINGS,'tts_enabled':'false','stt_enabled':'false','pet_enabled':'false'})
        app=QApplication([]);started=time.perf_counter();runtime=RuntimeServices(root/'runtime',project_root=ROOT)
        module._RUNTIME_SERVICES=runtime;window=create_application_window(runtime,runtime.start());window.show();window.navigate('chats');app.processEvents()
        report={'scope':__doc__.strip(),'constructor_to_window_ms':(time.perf_counter()-started)*1000,'model_calls':0}
        ticks=[];previous=[time.perf_counter()]
        def tick():
            now=time.perf_counter();ticks.append((now-previous[0])*1000);previous[0]=now
        timer=QTimer();timer.setInterval(16);timer.timeout.connect(tick);timer.start()
        def settle(seconds=.08):
            until=time.monotonic()+seconds
            while time.monotonic()<until:app.processEvents();QTest.qWait(5)
        try:
            plain=[]
            for i in range(20):
                started=time.perf_counter();window._append_direct_reply('Owned plain request '+str(i),'Actual short reply.',address=False);app.processEvents()
                plain.append((time.perf_counter()-started)*1000)
            report['plain_append_ms']={'p50':statistics.median(plain),'max':max(plain)}
            content='Plot this actual controlled user data, not hardware measurements.\nx,y\n'+'\n'.join(f'{i},{i*i}' for i in range(1000))
            window._append_direct_reply(content,'The chart uses exactly these user supplied values.',address=False)
            original=window.history[-2];reference=SourceRef('chat_dataset',original['message_id'],hashlib.sha256(content.encode()).hexdigest(),window._chat_id)
            settle(.3);process=psutil.Process();memory_before=process.memory_info().rss;rich=[]
            for i in range(args.messages):
                started=time.perf_counter();window._append_direct_reply('Show controlled dataset '+str(i),'Actual supplied data '+str(i)+'.',address=False)
                window._present_response_plan(ResponsePlan(window._chat_id,(Component('chart',reference,'Actual 1,000-row dataset',{'x':'x','ys':['y'],'table':True}),)))
                settle(.03);rich.append((time.perf_counter()-started)*1000)
            settle(.4)
            visible=[h for h in window._rich_hosts if not h.closed]
            report.update(rich_responses=args.messages,source_rows=1000,mounted_chat_rows=len(window._message_rows),chat_row_limit=MAX_VISIBLE_CHAT_WIDGETS,
                retained_hosts=len(visible),loaded_sections=sum(s['view'] is not None for h in visible for s in h.sections.values()),
                pending_deliveries=window.ui_bridge.diagnostics()['pending_deliveries'],rss_growth_bytes=process.memory_info().rss-memory_before,
                rich_append_and_30ms_settle_ms={'p50':statistics.median(rich),'p95':sorted(rich)[int(.95*(len(rich)-1))],'max':max(rich)},
                ui_timer_interval_ms={'p50':statistics.median(ticks),'p95':sorted(ticks)[int(.95*(len(ticks)-1))],'max':max(ticks),'samples':len(ticks)})
            assert report['mounted_chat_rows']<=MAX_VISIBLE_CHAT_WIDGETS
            assert report['loaded_sections']<=8,'Offscreen charts were not disposed.'
            assert not any(name in sys.modules for name in ('torch','diffusers','transformers'))
        finally:
            timer.stop();window.wake_controller.cancel();window.close();settle(.2);runtime.shutdown()
        report['shutdown']=runtime.shutdown_report
        assert report['shutdown']['clean'] and not report['shutdown']['leases_remaining']
        target=(ROOT/args.output).resolve();target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))


if __name__=='__main__':main()

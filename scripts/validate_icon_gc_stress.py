"""Owned icon-paint/worker-GC reproduction; no models, user profile or desktop capture."""
import faulthandler
faulthandler.enable()
import gc
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['QT_QPA_PLATFORM']='windows'
from PySide6.QtCore import Qt,QCoreApplication,QEvent,QPoint
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QApplication,QWidget,QGridLayout,QPushButton,QCheckBox,QRadioButton,QComboBox
from PySide6.QtTest import QTest
import PySide6
from morice.ui_next.icons import MARKS,icon,AuthoredControlStyle

output=ROOT/sys.argv[sys.argv.index('--output')+1] if '--output' in sys.argv else ROOT/'build/phase11-icon-gc-stress.json'
seconds=float(sys.argv[sys.argv.index('--seconds')+1]) if '--seconds' in sys.argv else 12.
stop=threading.Event();collections=[0]
def collect():
    while not stop.wait(.003):gc.collect();collections[0]+=1

with tempfile.TemporaryDirectory(prefix='morice-icon-gc-') as directory:
    os.environ.update(APPDATA=str(Path(directory)/'roaming'),LOCALAPPDATA=str(Path(directory)/'local'))
    app=QApplication([])
    if '--with-style' in sys.argv:
        app._owned_test_style=AuthoredControlStyle();app.setStyle(app._owned_test_style)
    root=QWidget();root.resize(800,600);layout=QGridLayout(root);buttons=[]
    for index,name in enumerate(MARKS):
        button=QPushButton(name);button.setIcon(icon(name));layout.addWidget(button,index//8,index%8);buttons.append((button,name))
    check=QCheckBox('Authored check');radio=QRadioButton('Authored radio');combo=QComboBox();combo.addItems(['Authored arrow','Second choice'])
    for index,control in enumerate((check,radio,combo)):layout.addWidget(control,8,index*2,1,2)
    root.show();app.processEvents()
    thread=threading.Thread(target=collect,name='owned-icon-gc-fixture',daemon=True);thread.start()
    start=time.monotonic();frames=0
    try:
        while time.monotonic()-start<seconds:
            for button,name in buttons:button.setIcon(icon(name,color=f'#{(0x90c6d0+frames*173)%0xffffff:06x}'))
            check.setChecked(bool(frames%2));radio.setChecked(bool(frames%2));combo.setCurrentIndex(frames%2)
            root.update();app.processEvents()
            image=QImage(root.size(),QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
            painter=QPainter(image)
            try:root.render(painter,QPoint())
            finally:painter.end()
            frames+=1;QTest.qWait(2)
    finally:
        stop.set();thread.join(2);root.close();root.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
    value={'status':'ICON_WORKER_GC_STRESS_PASSED','qt':PySide6.__version__,'seconds':time.monotonic()-start,
        'frames':frames,'icons':len(buttons),'native_control_kinds':['button','checkbox','radio','combo'],
        'worker_collections':collections[0],'authored_style':'--with-style' in sys.argv,
        'scope':'Owned native Qt buttons using authored icons, recolor/render loop and explicit worker cyclic GC; not a compositor or model benchmark.'}
    output.write_text(json.dumps(value,indent=2),encoding='utf-8');print(json.dumps(value),flush=True)

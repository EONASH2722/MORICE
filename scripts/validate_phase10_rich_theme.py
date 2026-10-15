"""Exercise actual owned Qt HTML rendering, load and repeated theme changes."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
with tempfile.TemporaryDirectory(prefix='morice-rich-theme-') as directory:
    root=Path(directory)
    os.environ.update(APPDATA=str(root/'roaming'),LOCALAPPDATA=str(root/'local'),QT_QPA_PLATFORM='windows',MORICE_LOCAL_DATA_DIR=str(root/'data'),
        MORICE_PRELOAD='0',MORICE_NODE_NETWORK='0',MORICE_DISABLE_RECOVERY='1',MORICE_DISABLE_SESSION='1')
    from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout
    from PySide6.QtTest import QTest
    from morice.pyside_app import RichContentView,QWebEngineView
    from morice.ui_next.themes import ThemeEngine
    assert QWebEngineView is not None,'Native rich HTML renderer unavailable.'
    app=QApplication([]);theme=ThemeEngine(root/'appearance');owner=QWidget();layout=QVBoxLayout(owner)
    view=RichContentView('# Owned rendering check\n\n$2+3=5$\n\n```python\nanswer = 2 + 3\n```\n\n| Item | Value |\n| --- | --- |\n| Result | 5 |',owner);layout.addWidget(view)
    owner.resize(780,600);owner.show();rows=[];loaded=[];view.loadFinished.connect(lambda ok:loaded.append(ok))
    # Update before load completion: this must survive the asynchronous load.
    theme.update(preset='ARCTIC',persist=False);view.apply_design_tokens(theme.tokens)
    def until(predicate):
        end=time.monotonic()+20
        while not predicate() and time.monotonic()<end:QTest.qWait(20)
        assert predicate(),'Owned HTML operation did not settle.'
    until(lambda:loaded and loaded[-1])
    try:
        owner.setObjectName('RichValidationRoot')
        for preset,scale in (('ARCTIC',1.),('CRIMSON',1.3),('MORICE',1.),('SOLAR',.8),('ARCTIC',1.8),('ICE',1.8)):
            theme.update(preset=preset,font_scale=scale,persist=False);view.apply_design_tokens(theme.tokens);QTest.qWait(60)
            owner.setStyleSheet(f"QWidget#RichValidationRoot {{ background: {theme.tokens['surface']}; }}")
            result=[]
            view.page().runJavaScript("(()=>{const s=getComputedStyle(document.documentElement);return JSON.stringify({text:s.getPropertyValue('--text').trim(),code:s.getPropertyValue('--code-bg').trim(),size:s.getPropertyValue('--font-size').trim(),katex:document.querySelectorAll('.katex').length,highlighted:document.querySelectorAll('.hljs').length});})()",lambda value:result.append(value))
            until(lambda:bool(result));values=json.loads(result[0])
            assert values['text']==theme.tokens['text_primary'] and values['code']==theme.tokens['surface_elevated']
            assert values['size']==f'{theme.tokens.body_size}px' and values['katex']>0 and values['highlighted']>0
            rows.append({'preset':preset,'scale':scale,**values})
        output=ROOT/'build/phase10-rich-theme-current';output.mkdir(parents=True,exist_ok=True)
        assert owner.grab().save(str(output/'ice-large.png'))
        (output/'evidence.json').write_text(json.dumps({'status':'OWNED_NATIVE_RICH_THEME_PASSED','rows':rows,'scope':'Actual internal Qt HTML renderer, local assets only; load and repeated palette/font changes, no external browser or user conversation.'},indent=2),encoding='utf-8')
        print(json.dumps({'status':'OWNED_NATIVE_RICH_THEME_PASSED','checks':len(rows)}))
    finally:owner.close();owner.deleteLater();app.processEvents()

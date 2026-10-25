"""Exercise bundled Markdown/KaTeX and actual streamed reply finalization."""
import json
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from test_fast_memory_ui import app,window,pump
from morice.pyside_app import ChatBubble,RichContentView


def javascript(view,app,expression):
    result=[];view.page().runJavaScript(expression,result.append)
    pump(app,lambda:bool(result))
    return result[0]


def rendered(view,app,count):
    deadline=time.monotonic()+10
    data={'state':'Waiting for the owned page to load.'}
    while time.monotonic()<deadline:
        value=javascript(view,app,"document.body && JSON.stringify({math:document.querySelectorAll('.katex').length,errors:document.querySelectorAll('.morice-math-error').length,text:document.body.innerText})")
        if not value:QTest.qWait(20);app.processEvents();continue
        data=json.loads(value)
        if data['math']==count:return data
        QTest.qWait(20);app.processEvents()
    raise AssertionError(data)


def test_bundled_math_preserves_slashes_subscripts_units_tables_and_code(app):
    text=r'''# Owned rendering fixture

Inline \(F_{\text{weight}}=m\cdot g\), $a_{\text{net}}=\frac{F-mg}{m}$ and spaced $ m = 126.7 \,\text{mg} $.

\[
\begin{aligned}
F &= m g \\
a &= \frac{F-mg}{m}
\end{aligned}
\]

$$
m_{\max}=\frac{F}{9.81}
$$

| Quantity | Value |
| --- | --- |
| $g$ | $9.81$ |

`$not_math$ and \(not_math\)`

```latex
\[not_math\]
```
'''
    view=RichContentView(text);view.resize(850,600);view.show()
    try:
        result=rendered(view,app,7);assert result['errors']==0
        assert javascript(view,app,"document.querySelectorAll('h1').length")==1
        assert javascript(view,app,"document.querySelectorAll('table tbody tr').length")==1
        assert javascript(view,app,"document.querySelectorAll('.katex-display').length")==2
        annotations=javascript(view,app,"JSON.stringify(Array.from(document.querySelectorAll('annotation')).map(x=>x.textContent))")
        assert r'F_{\text{weight}}=m\cdot g' in json.loads(annotations)
        assert 'not_math' in javascript(view,app,"document.querySelector('pre code').textContent")
        assert javascript(view,app,"document.querySelector('pre .katex')===null")
    finally:view._measure_timer.stop();view.stop();view.close();view.deleteLater();app.processEvents()


def test_currency_stays_text_and_invalid_math_keeps_readable_source(app):
    view=RichContentView(r'Price $5 and $10. Valid \(x^2\). Invalid \(\notAMoriceCommand{x}\).');view.show()
    try:
        result=rendered(view,app,1)
        assert result['errors']==1 and '$5 and $10' in result['text']
        assert r'\notAMoriceCommand{x}' in result['text']
    finally:view._measure_timer.stop();view.stop();view.close();view.deleteLater();app.processEvents()


def test_stream_finishes_with_math_in_same_bubble_and_keeps_copy_text(window,app):
    window._session_enabled=True;window._render_chat_messages([]);window.follow_latest=True
    response=r'# Actual answer'+ '\n\n'+r'Force \(F=mg\).'+ '\n\n$$\na=\\frac{F-mg}{m}\n$$'
    window.history=[{'role':'user','content':'Show the supplied equations.'}]
    window._on_assistant_stream_delta('owned-math-stream',response[:30])
    bubble=window._stream_bubble;row=window._message_rows[-1]
    assert bubble is not None and bubble._message_label.textFormat()==Qt.PlainText
    window._on_assistant_stream_delta('owned-math-stream',response[30:]);app.processEvents()
    assert bubble._message_label.text()==response and not bubble.findChildren(RichContentView)
    window.history.append({'role':'assistant','content':response})
    window._on_assistant_stream_finished('owned-math-stream',response);app.processEvents()
    assert window._message_rows[-1] is row and row.findChild(ChatBubble) is bubble
    assert sum(r.findChild(ChatBubble).message==response for r in window._message_rows)==1
    view=bubble.findChild(RichContentView);assert view is not None
    rendered(view,app,2)
    assert bubble.message==response
    window._load_history_page(earlier=False);pump(app,lambda:not window._loading_history)
    assert sum(r.findChild(ChatBubble).message==response for r in window._message_rows)==1

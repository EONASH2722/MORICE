"""Reuse existing math, diagram and globe renderers for typed rich responses."""
from __future__ import annotations

import math
import os

from PySide6.QtCore import Qt,QPoint,QRect
from PySide6.QtGui import QPainter,QPen,QColor,QPolygon
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QPushButton,QPlainTextEdit

from ..pyside_app import DiagramCanvas,RichContentView,QWebEngineView
from ..domain_engine import DiagramArtifact,DiagramNode,DiagramEdge
from ..kernel import ExecutionContext
from .spatial_view import GlobeCanvas
from .rich_primitives import plain,display


class MathView(QWidget):
    def __init__(self,component,context):
        super().__init__();layout=QVBoxLayout(self);formula=component.config.get('formula')
        if formula is None and context.snapshot is not None:
            data=context.snapshot.data;formula=data.get('expression') or data.get('inputs',{}).get('expression')
        if not formula:raise ValueError('No actual expression is available for this math component.')
        self.view=RichContentView('$$\n'+formula+'\n$$',self) if QWebEngineView is not None and os.getenv('MORICE_WEB','1')!='0' else plain(formula)
        layout.addWidget(self.view);layout.addWidget(plain('Expression display; physical assumptions require their own evidence.',role='secondary'))
    def dispose(self):
        timer=getattr(self.view,'_measure_timer',None)
        if timer is not None:timer.stop()
        stop=getattr(self.view,'stop',None)
        if callable(stop):stop()


class ResponseDiagramCanvas(DiagramCanvas):
    def __init__(self,theme):super().__init__();self.theme=theme;self.setMaximumHeight(580);self.setFocusPolicy(Qt.StrongFocus)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);t=self.theme.tokens;rect=self.rect()
        painter.fillRect(rect,QColor(t['surface']))
        if not self.artifact:painter.end();return
        self._node_rects=self._layout_nodes(rect.adjusted(28,24,-28,-24))
        painter.setPen(QPen(QColor(t['accent_secondary']),2));painter.setBrush(QColor(t['accent_secondary']))
        for edge in self.artifact.edges:
            if edge.source not in self._node_rects or edge.target not in self._node_rects:continue
            start,end=self._edge_points(self._node_rects[edge.source],self._node_rects[edge.target]);painter.drawLine(start,end)
            angle=math.atan2(end.y()-start.y(),end.x()-start.x())
            painter.drawPolygon(QPolygon([end,QPoint(round(end.x()-10*math.cos(angle-.4)),round(end.y()-10*math.sin(angle-.4))),
                QPoint(round(end.x()-10*math.cos(angle+.4)),round(end.y()-10*math.sin(angle+.4)))]))
            if edge.label:painter.drawText(QRect((start.x()+end.x())//2,(start.y()+end.y())//2,120,22),edge.label)
        for node in self.artifact.nodes:
            box=self._node_rects[node.node_id];painter.setPen(QPen(QColor(t['border_hover']),1.5));painter.setBrush(QColor(t['surface_elevated']))
            painter.drawRoundedRect(box,10,10);painter.setPen(QColor(t['text_primary']));painter.drawText(box.adjusted(6,3,-6,-3),Qt.AlignCenter|Qt.TextWordWrap,node.label)
        painter.end()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Home:self.reset_view()
        elif event.key() in {Qt.Key_Left,Qt.Key_Right,Qt.Key_Up,Qt.Key_Down}:
            self.pan_x+=20 if event.key()==Qt.Key_Right else -20 if event.key()==Qt.Key_Left else 0
            self.pan_y+=20 if event.key()==Qt.Key_Down else -20 if event.key()==Qt.Key_Up else 0;self.update()
        else:return super().keyPressEvent(event)
        event.accept()


class DiagramView(QWidget):
    def __init__(self,component,context):
        super().__init__();layout=QVBoxLayout(self);config=component.config
        nodes=config.get('nodes',[]);edges=config.get('edges',[])
        derived=False
        if not nodes and context.snapshot is not None and context.snapshot.source.kind=='research_project':
            derived=True
            nodes=[{'id':r['id'],'label':r['title']} for r in context.snapshot.data['records'][:64]]
            identities={n['id'] for n in nodes}
            edges=[{'from':r['source'],'to':r['target'],'label':r['relation']} for r in context.snapshot.data.get('edges',[]) if r['source'] in identities and r['target'] in identities]
        if not nodes:raise ValueError('No typed diagram nodes are available.')
        self.canvas=ResponseDiagramCanvas(context.theme)
        self.canvas.set_artifact(DiagramArtifact(component.title or 'Explanation diagram','flowchart',
            [DiagramNode(r['id'],r['label']) for r in nodes],[DiagramEdge(r['from'],r['to'],r.get('label','')) for r in edges],
            {'parameters':{'layout':config.get('orientation','horizontal')}},[]))
        layout.addWidget(self.canvas);reset=QPushButton('Fit diagram');reset.clicked.connect(self.canvas.reset_view);layout.addWidget(reset)
        self.details=plain('Select a node to inspect its links.',role='secondary');self.canvas.inspected.connect(self.details.setText);layout.addWidget(self.details)
        toggle=QPushButton('Show accessible node list');toggle.setCheckable(True);layout.addWidget(toggle)
        self.text=QPlainTextEdit();self.text.setReadOnly(True);self.text.setMaximumHeight(220)
        self.text.setPlainText('\n'.join(r['label'] for r in nodes)+'\n\n'+'\n'.join(r['from']+' → '+r['to'] for r in edges))
        self.text.hide();toggle.toggled.connect(self.text.setVisible);layout.addWidget(self.text)
        layout.addWidget(plain('Links from the actual saved source.' if derived else 'Explanation diagram; not an execution or completion receipt.',role='secondary'))
    def dispose(self):self.canvas.artifact=None;self.canvas._node_rects={}


class SpatialResultView(QWidget):
    def __init__(self,component,context):
        super().__init__();self.component=component;self.context=context;self._disposed=False;self._revision=0
        host=context._host();window=host.window() if host else None
        if window is None:raise ValueError('The owning MORICE window is unavailable.')
        layout=QVBoxLayout(self);self.canvas=GlobeCanvas(context.theme,window.effect_policy,window.effect_clock)
        self.canvas.setMinimumHeight(300);self.canvas.setMaximumHeight(460);self.canvas.autorotate=False;self.canvas.set_context(context.snapshot.data)
        layout.addWidget(self.canvas);controls=QHBoxLayout();self.mode=QComboBox();self.mode.addItems(['GEODESIC','CHORD'])
        self.mode.setCurrentText(component.config.get('mode',context.snapshot.data.get('mode','GEODESIC')));self.mode.setAccessibleName('Geographic distance mode')
        self.unit=QComboBox();self.unit.addItems(['m','km','miles','nautical miles']);self.unit.setCurrentText(component.config.get('unit',context.snapshot.data.get('unit','km')))
        self.unit.setAccessibleName('Geographic distance unit');controls.addWidget(self.mode);controls.addWidget(self.unit);layout.addLayout(controls)
        self.value=plain('');layout.addWidget(self.value);self.set_result(context.snapshot.data.get('result'))
        self.mode.currentTextChanged.connect(self.recalculate);self.unit.currentTextChanged.connect(self.recalculate)
        self.canvas.cursor_location.connect(lambda text:self.value.setToolTip(text))

    def set_result(self,value):
        if isinstance(value,dict) and 'distance' in value:self.value.setText(display(value['distance'],value.get('unit',''))+' · '+value.get('mode',''))
        else:self.value.setText('Actual stored markers. Select a pair in Spatial to calculate a distance.')

    def recalculate(self,*_):
        self._revision+=1;revision=self._revision
        data=self.context.snapshot.data
        if not data.get('origin') or not data.get('destination'):self.value.setText('A real origin and destination are required.');return
        mode=self.mode.currentText();unit=self.unit.currentText()
        args={'origin':data['origin']['coordinate'],'destination':data['destination']['coordinate'],'mode':mode,'unit':unit}
        def done(result):
            if self._disposed or revision!=self._revision:return
            if not result.success or not result.verification or result.verification.status.value!='verified':
                self.value.setText('; '.join(error.message for error in result.errors) or 'Geographic calculation did not verify.');return
            self.canvas.set_context({**data,'result':result.output,'mode':mode,'unit':unit});self.set_result(result.output)
            self.context.save_config(mode=mode,unit=unit)
        self.context.submit(self,'Recalculate actual geographic result',lambda:self.context.runtime.kernel.dispatch('spatial.distance.calculate',args,
            ExecutionContext(conversation_id=self.context.sources.conversation_id)),done,lambda error:self.value.setText(str(error)))

    def dispose(self):
        self._disposed=True;self.canvas.clock.unsubscribe_id(id(self.canvas));self.canvas._cache=None;self.canvas.context={};self.canvas.rings=[]

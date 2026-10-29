"""Lazy native response host over the existing chat, workers and domain owners."""
from __future__ import annotations

from dataclasses import asdict,replace
import weakref
import time

from PySide6.QtCore import Qt,QPoint,QRect,QTimer,QEvent
from PySide6.QtWidgets import QWidget,QFrame,QVBoxLayout,QHBoxLayout,QPushButton,QFileDialog
from shiboken6 import isValid

from ..kernel import CancellationToken,ExecutionContext
from ..rich_response import Component,ResponsePlan,SourceRef
from ..rich_response.registry import ResponseComponentRegistry
from ..rich_response.sources import ResponseSources
from ..rich_response.exports import register_response_exports
from .rich_primitives import MetricsView,StatusView,DataTableView,TimelineView,plain
from .rich_charts import ChartView
from .rich_controls import CalculatorView,ProgressView,ValidationView,ComparisonView
from .rich_mesh import MeshView
from .rich_files import FilesView,PreviewView,MediaView
from .rich_science import MathView,DiagramView,SpatialResultView


def capture_chart(context,canvas,format):
    import tempfile
    from pathlib import Path
    from ..rich_response.exports import ResponseRender
    if format not in {'png','svg','pdf'}:raise ValueError('Choose PNG, SVG or PDF for this chart.')
    root=Path(context.runtime.directory)/'response-cache';root.mkdir(parents=True,exist_ok=True)
    temporary=tempfile.TemporaryDirectory(prefix='chart-',dir=root);path=Path(temporary.name)/('chart.'+format)
    try:
        if not getattr(canvas,'export_'+format)(str(path)):raise ValueError('The actual native chart could not be captured.')
    except BaseException:temporary.cleanup();raise
    return ResponseRender(context.sources,context.component.source,path,format,temporary)


def native_registry():
    registry=ResponseComponentRegistry()
    for kind,factory in (('metrics',MetricsView),('status',StatusView),('table',DataTableView),('timeline',TimelineView),('chart',ChartView),
        ('calculator',CalculatorView),('simulation',ProgressView),('progress',ProgressView),('validation',ValidationView),('comparison',ComparisonView)):
        registry.register(kind,factory)
    for kind in ('mesh','assembly'):registry.register(kind,MeshView,sources={'research_record','experiment','build_session'})
    for kind,factory in (('files',FilesView),('preview',PreviewView),('media',MediaView)):
        registry.register(kind,factory,sources={'research_record','experiment','build_session','media_generation'})
    registry.register('math',MathView);registry.register('diagram',DiagramView)
    registry.register('spatial',SpatialResultView,sources={'spatial'})
    return registry


class RichRenderContext:
    def __init__(self,host,component,snapshot):
        self._host=weakref.ref(host);self.component=component;self.snapshot=snapshot
        self.sources=host.sources;self.runtime=host.runtime;self.bridge=host.bridge;self.theme=host.theme
        self.epoch=host.sections[component.id]['epoch']

    def submit(self,target,title,operation,done,failed=None,*,cancellable=False):
        host=self._host()
        if host is None or host.closed:return None
        token=CancellationToken(parent=host.cancellation);host.jobs.add(token);target_ref=weakref.ref(target)
        generation=host.generation
        state=host.sections[self.component.id]
        state['jobs'].add(token)
        def completed(envelope):
            owner=self._host()
            if owner is not None:owner.jobs.discard(token)
            state['jobs'].discard(token)
            widget=target_ref()
            if owner is None or owner.closed or token.cancelled or owner.generation!=generation or state['epoch']!=self.epoch or widget is None or not isValid(widget):return
            if envelope['ok']:done(envelope['value'])
            elif failed is not None:failed(envelope.get('error','The source operation failed.'))
        def execute():
            with self.sources.using_cancellation(token):
                value=operation(token) if cancellable else operation()
            return value
        try:host.bridge.submit(title,execute,completed)
        except Exception as exc:completed({'ok':False,'error':str(exc)})
        return token

    def action(self,target,action,arguments=None,done=None,failed=None):
        host=self._host()
        if host is None or host.closed:return
        window=host.window()
        if window is None or window._chat_id!=host.plan.conversation_id:
            if failed:failed('Return to the conversation that owns this result before acting on it.')
            return
        arguments=arguments or {};source=self.component.source
        if action in {'export_chart','export_data','export_report'}:
            from ..nlui.contracts import IntentResolution,Operation
            resolution=IntentResolution(operations=(Operation('nlui.response.control',{'action':action,'reference':self.component.id,'format':arguments.get('format','png')}),))
            context=window.nlui_port.context()
            return self.submit(target,'Export actual response chart',lambda token:host.runtime.nlui.execute(resolution,context,cancellation=token),
                lambda result:(done(result) if done else None),failed,cancellable=True)
        if action in {'run','pause','cancel'} and source and (source.kind=='experiment' or source.kind=='media_generation' and action=='cancel'):
            from ..nlui.contracts import IntentResolution,Operation
            arguments=({'reference':source.id,'project_reference':self.snapshot.data['project_id']} if source.kind=='experiment' else {'reference':source.id})
            resolution=IntentResolution(operations=(Operation(('nlui.research.' if source.kind=='experiment' else 'nlui.media.')+action,arguments),))
            context=window.nlui_port.context()
            return self.submit(target,'Response experiment control',
                lambda token:host.runtime.nlui.execute(resolution,context,cancellation=token),
                lambda result:(done(result) if done else None),failed,cancellable=True)
        if action=='export' and source:
            artifact=next((item for item in self.snapshot.artifacts if item.id==arguments.get('artifact')),None)
            if artifact is None:
                if failed:failed('The selected source has no such actual artifact.')
                return
            if not artifact.available:
                if failed:failed(artifact.reason)
                return
            from .file_access import require_selected_file
            try:require_selected_file(host.runtime,'file_write')
            except PermissionError as exc:
                if failed:failed(str(exc))
                return
            destination,_=QFileDialog.getSaveFileName(target,'Export verified artifact',artifact.name)
            if not destination:return
            context=ExecutionContext(conversation_id=host.plan.conversation_id,active_files=(destination,))
            args={'source':asdict(source),'artifact':artifact.id,'destination':destination}
            return self.submit(target,'Export response artifact',lambda:host.runtime.kernel.dispatch('response.artifact.export',args,context),
                lambda result:(done(result) if done else None),failed)
        if action=='refresh':host.refresh_source(source);return
        if failed:failed('That response action has no implemented binding for this source.')

    def save_config(self,**changes):
        host=self._host()
        if host is not None and not host.closed:
            window=host.window()
            if window is not None:
                window.follow_latest=False
                window._user_scroll_guard_until=max(window._user_scroll_guard_until,time.monotonic()+.5)
            current=host.sections[self.component.id]['component']
            host.update_component(self.component.id,config={**current.config,**changes})
            self.component=host.sections[self.component.id]['component']


class RichResponseHost(QFrame):
    def __init__(self,plan,window,parent=None,*,on_changed=None,registry=None):
        super().__init__(parent)
        self.plan=ResponsePlan.from_dict(plan.to_dict()) if isinstance(plan,ResponsePlan) else ResponsePlan.from_dict(plan)
        if self.plan.conversation_id!=window._chat_id:raise ValueError('Response belongs to another active conversation.')
        self.window=weakref.ref(window);self.runtime=window.runtime;self.bridge=window.ui_bridge;self.theme=window.theme_engine
        wanted={c.source.id for c in self.plan.components if c.source and c.source.kind in {'chat_calculation','chat_dataset','spatial','chat_metadata'}}
        self.sources=ResponseSources(self.runtime,self.plan.conversation_id,messages=[m for m in window.history if m.get('message_id') in wanted]);register_response_exports(self.runtime)
        self.registry=registry or native_registry();self.on_changed=on_changed;self.closed=False;self.generation=0
        self.cancellation=CancellationToken();self.jobs=set();self.sections={};self._visible=True
        self._requested_section='';self._reading_anchor=None
        self.setObjectName('RichResponse');self.setProperty('role','surface');self.setAccessibleName('Interactive result with actual sources')
        layout=QVBoxLayout(self);layout.setContentsMargins(8,8,8,8);layout.addWidget(plain('Interactive result',role='title'))
        report=QPushButton('Export response report as PDF…');layout.addWidget(report);self.report_status=plain('',role='secondary');layout.addWidget(self.report_status)
        report.clicked.connect(lambda:RichRenderContext(self,next(iter(self.sections.values()))['component'],None).action(report,'export_report',{'format':'pdf'},
            done=lambda result:self.report_status.setText(result.message),failed=lambda error:self.report_status.setText(str(error))))
        for index,component in enumerate(self.plan.components):
            section=QFrame();box=QVBoxLayout(section);box.setContentsMargins(4,4,4,4)
            bar=QHBoxLayout();toggle=QPushButton(component.title or component.kind.title());toggle.setCheckable(True)
            toggle.setChecked(self.plan.profile!='compact' and index<3);toggle.setAccessibleName('Expand '+(component.title or component.kind))
            bar.addWidget(toggle,1);refresh=QPushButton('Refresh');refresh.setAccessibleName('Refresh actual source for '+(component.title or component.kind));bar.addWidget(refresh)
            box.addLayout(bar);placeholder=plain('Open to load the actual source.');box.addWidget(placeholder)
            state={'component':component,'section':section,'layout':box,'toggle':toggle,'placeholder':placeholder,'view':None,'loading':False,'error':False,'epoch':0,'jobs':set()}
            self.sections[component.id]=state;layout.addWidget(section)
            toggle.toggled.connect(lambda checked,cid=component.id:self.expand(cid,checked))
            refresh.clicked.connect(lambda _=False,source=component.source:self.refresh_source(source))
        self._visibility_timer=QTimer(self);self._visibility_timer.setSingleShot(True);self._visibility_timer.timeout.connect(self.refresh_visibility)
        window.scroll.verticalScrollBar().valueChanged.connect(self.schedule_visibility)
        window.scroll.viewport().installEventFilter(self)
        self.schedule_visibility()

    def schedule_visibility(self,*_):
        if not self.closed:self._visibility_timer.start(0)

    def eventFilter(self,source,event):
        if event.type() in {QEvent.Resize,QEvent.Show,QEvent.Hide}:self.schedule_visibility()
        return False

    def showEvent(self,event):super().showEvent(event);self.schedule_visibility()
    def hideEvent(self,event):super().hideEvent(event);self.release_views()

    def select_section(self,identifier):
        """Mark explicit native/NLUI navigation before changing scroll position."""
        if identifier not in self.sections:raise ValueError('Unknown response section.')
        window=self.window()
        if window is not None and isValid(window):
            window._history_scroll_epoch+=1;window.follow_latest=False
            window._user_scroll_guard_until=max(window._user_scroll_guard_until,time.monotonic()+.5)
        self._reading_anchor=None;self._requested_section=identifier
        if window is not None and isValid(window):
            epoch=window._history_scroll_epoch
            # A compact chat can reflow after a theme/size change or mounting
            # the response. Resolve the explicit target after that layout work,
            # while allowing subsequent user scrolling to cancel the request.
            for delay in (0,60):
                QTimer.singleShot(delay,lambda cid=identifier,e=epoch:self._show_selected_section(cid,e))

    def _show_selected_section(self,identifier,epoch):
        if not isValid(self) or self.closed:return
        window=self.window()
        if (window is None or not isValid(window) or window._is_closing or
            window.active_route!='chats' or window._chat_id!=self.plan.conversation_id or
            window._history_scroll_epoch!=epoch or self._requested_section!=identifier):return
        state=self.sections[identifier]
        if not state['toggle'].isChecked():return
        parent=state['section']
        while parent is not None:
            if parent.layout() is not None:parent.layout().activate()
            if parent is window.scroll.widget():break
            parent=parent.parentWidget()
        target=state['toggle'];viewport=window.scroll.viewport()
        y=target.mapTo(viewport,QPoint()).y()
        if y<0 or y+target.height()>viewport.height():
            window.scroll.ensureWidgetVisible(target,20,20)
        self.schedule_visibility()

    def _capture_reading_anchor(self):
        window=self.window()
        if window is None or not isValid(window) or not self.isVisible() or window._chat_id!=self.plan.conversation_id:return
        viewport=window.scroll.viewport();now=time.monotonic()
        if not QRect(self.mapTo(viewport,QPoint()),self.size()).intersects(viewport.rect()):return
        anchor=self._reading_anchor
        if not anchor or anchor['expires']<now or anchor['epoch']!=window._history_scroll_epoch:
            candidates=[]
            for identifier,state in self.sections.items():
                y=state['toggle'].mapTo(viewport,QPoint()).y()
                if y<viewport.height() and y+state['section'].height()>0:
                    candidates.append((identifier,y,state))
            if not candidates:return
            chosen=next((row for row in candidates if row[0]==self._requested_section and row[1]>=0),None)
            if chosen is None:chosen=min(candidates,key=lambda row:abs(row[1]))
            identifier,y,state=chosen
            anchor={'id':identifier,'widget':weakref.ref(state['toggle']),'offset':y,
                'epoch':window._history_scroll_epoch,'expires':now+.3}
            self._reading_anchor=anchor
        window.follow_latest=False
        window._user_scroll_guard_until=max(window._user_scroll_guard_until,now+.4)

    def _restore_reading_anchor(self):
        window=self.window();anchor=self._reading_anchor
        if self.closed or not isValid(self) or window is None or not isValid(window) or not self.isVisible() or not anchor:return
        if anchor['epoch']!=window._history_scroll_epoch or anchor['expires']<time.monotonic() or window._chat_id!=self.plan.conversation_id:return
        widget=anchor['widget']()
        if widget is None or not isValid(widget):return
        parent=self
        while parent is not None:
            if parent.layout() is not None:parent.layout().activate()
            if parent is window.scroll.widget():break
            parent=parent.parentWidget()
        bar=window.scroll.verticalScrollBar();previous=window._auto_scrolling
        window._auto_scrolling=True
        try:bar.setValue(bar.value()+widget.mapTo(window.scroll.viewport(),QPoint()).y()-anchor['offset'])
        finally:window._auto_scrolling=previous
        window.follow_latest=False;self.schedule_visibility()

    def refresh_visibility(self):
        if self.closed:return
        window=self.window()
        if window is None or not isValid(window):return
        viewport=window.scroll.viewport()
        visible=self.isVisible() and QRect(self.mapTo(viewport,QPoint()),self.size()).intersects(viewport.rect())
        self._visible=visible
        if not visible:self.release_views();return
        if self._requested_section:self._capture_reading_anchor()
        nearby=viewport.rect().adjusted(0,-200,0,200)
        for identifier,state in self.sections.items():
            section_visible=QRect(state['section'].mapTo(viewport,QPoint()),state['section'].size()).intersects(nearby)
            if not section_visible:
                anchored=(self._reading_anchor and self._reading_anchor['id']==identifier
                    and self._reading_anchor['expires']>time.monotonic()
                    and self._reading_anchor['epoch']==window._history_scroll_epoch)
                if not anchored and (state['view'] is not None or state['loading']):self.release(state)
            elif state['toggle'].isChecked() and state['view'] is None and not state['loading'] and not state['error']:self.load(identifier)

    def expand(self,identifier,checked):
        state=self.sections[identifier]
        self.select_section(identifier)
        if not checked:self._requested_section=''
        if checked:
            state['error']=False
            if self._visible:self.schedule_visibility()
        else:self.release(state,preserve_height=False)

    def load(self,identifier):
        state=self.sections[identifier]
        if self.closed or state['loading'] or state['view'] is not None:return
        component=state['component'];state['loading']=True;state['placeholder'].setText('Reading the actual source…');state['placeholder'].show()
        generation=self.generation;epoch=state['epoch'];token=CancellationToken(parent=self.cancellation);self.jobs.add(token);state['jobs'].add(token)
        def completed(envelope):
            self.jobs.discard(token)
            state['jobs'].discard(token)
            if self.closed or generation!=self.generation or epoch!=state['epoch']:return
            state['loading']=False
            if token.cancelled or not self._visible or not state['toggle'].isChecked():return
            if not envelope['ok']:
                state['error']=True;state['placeholder'].setText(envelope.get('error','Source unavailable.'));return
            self._capture_reading_anchor()
            try:
                snapshot=envelope['value'];context=RichRenderContext(self,component,snapshot)
                view=self.registry.create(component,context);state['view']=view;state['layout'].addWidget(view)
                state['placeholder'].hide();state['placeholder'].setMinimumHeight(0)
                if snapshot is not None:
                    note=plain(snapshot.provenance+' · '+snapshot.limitation,role='secondary');state['layout'].addWidget(note);state['note']=note
            except Exception as exc:
                state['error']=True;state['placeholder'].setText(str(exc));state['placeholder'].show()
            # Each source delivery starts fresh layout work. Keep a shared
            # reading anchor through this batch, even if a previous source's
            # restoration window was about to expire.
            if self._reading_anchor:self._reading_anchor['expires']=time.monotonic()+.3
            for delay in (0,60,180):QTimer.singleShot(delay,self._restore_reading_anchor)
        def execute():
            with self.sources.using_cancellation(token):return self.sources.resolve(component.source) if component.source else None
        try:self.bridge.submit('Load response source',execute,completed,priority='background')
        except Exception as exc:completed({'ok':False,'error':str(exc)})

    def release(self,state,*,preserve_height=True):
        state['epoch']+=1
        for token in tuple(state['jobs']):
            token.cancel('Response section closed or outside the visible chat.');self.jobs.discard(token)
        state['jobs'].clear();state['loading']=False
        view=state.get('view')
        if view is not None:
            note=state.get('note');height=view.height()+(note.height()+state['layout'].spacing() if note is not None else 0)
            if hasattr(view,'dispose'):view.dispose()
            state['layout'].removeWidget(view);view.deleteLater();state['view']=None
            if preserve_height:state['placeholder'].setMinimumHeight(max(0,height))
        note=state.pop('note',None)
        if note is not None:state['layout'].removeWidget(note);note.deleteLater()
        state['placeholder'].setText('Result paused while outside the visible chat.');state['placeholder'].setVisible(state['toggle'].isChecked())

    def release_views(self):
        if self.closed:return
        self.generation+=1
        for token in tuple(self.jobs):token.cancel('Rich result is no longer visible.')
        self.jobs.clear()
        for state in self.sections.values():state['loading']=False;self.release(state)

    def update_component(self,identifier,**changes):
        components=tuple(replace(c,**changes) if c.id==identifier else c for c in self.plan.components)
        self.plan=ResponsePlan.from_dict(replace(self.plan,components=components).to_dict());self.sections[identifier]['component']=next(c for c in self.plan.components if c.id==identifier)
        if self.on_changed:self.on_changed(self.plan)

    def refresh_source(self,source):
        if source is None:return
        unpinned=replace(source,revision='')
        generation=self.generation;token=CancellationToken(parent=self.cancellation);self.jobs.add(token)
        def ready(value):
            for identifier,state in self.sections.items():
                current=state['component'].source
                if current and (current.kind,current.id)==(source.kind,source.id):
                    self.release(state,preserve_height=False);state['error']=False
                    self.update_component(identifier,source=replace(current,revision=value.revision))
            self.schedule_visibility()
        def completed(envelope):
            self.jobs.discard(token)
            if self.closed or token.cancelled or self.generation!=generation:return
            if envelope['ok']:ready(envelope['value'])
            else:
                for state in self.sections.values():
                    if state['component'].source==source:state['placeholder'].setText(envelope.get('error','Source unavailable.'));state['placeholder'].show()
        def execute():
            with self.sources.using_cancellation(token):return self.sources.resolve(unpinned)
        self.bridge.submit('Refresh response source',execute,completed)

    def dispose(self):
        if self.closed:return
        self.release_views();self.closed=True;self.cancellation.cancel('Response disposed.');self._visibility_timer.stop()
        window=self.window()
        if window is not None and isValid(window):
            try:window.scroll.verticalScrollBar().valueChanged.disconnect(self.schedule_visibility)
            except (RuntimeError,TypeError):pass
            window.scroll.viewport().removeEventFilter(self)

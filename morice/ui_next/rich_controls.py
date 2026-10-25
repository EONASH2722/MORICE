"""Real calculator, validation, comparison and job controls for rich results."""
from __future__ import annotations

import math

from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QComboBox,
    QPushButton,QTableView,QProgressBar,QScrollArea,QFrame)

from ..rich_response.calculators import recipe,calculate
from .rich_primitives import plain,display,ResultTableModel
from .responsive import FlowLayout


class CalculatorView(QWidget):
    def __init__(self,component,context):
        super().__init__();self.component=component;self.context=context;self.definition=recipe(context.sources,context.snapshot)
        self._token=None;self._disposed=False;self._revision=0;self.last_result=None
        layout=QVBoxLayout(self);layout.addWidget(plain('Unsaved model exploration. Changes recalculate the supplied model without changing its saved experiment.',role='secondary'))
        if self.definition.get('expression'):layout.addWidget(plain(self.definition['expression']))
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setMinimumHeight(100);scroll.setMaximumHeight(260)
        form_host=QWidget();form=QFormLayout(form_host);form.setRowWrapPolicy(QFormLayout.WrapLongRows);self.inputs={}
        restored=component.config.get('values',{})
        if set(restored)-self.definition['parameters'].keys():raise ValueError('Saved calculator inputs no longer belong to this source model.')
        for key,value in self.definition['parameters'].items():
            value=restored.get(key,value)
            field=QLineEdit(repr(value));field.setAccessibleName('Calculator '+key+' '+self.definition['units'][key])
            field.setMaximumWidth(260);self.inputs[key]=field;form.addRow(key.replace('_',' ')+' ['+(self.definition['units'][key] or 'dimensionless')+']',field)
            field.textEdited.connect(lambda _=False:self.schedule())
        scroll.setWidget(form_host);layout.addWidget(scroll)
        controls=QHBoxLayout();self.strategy=QComboBox()
        self.strategy.addItem('Use the supplied parameters','')
        if self.definition.get('tool_id')=='electromagnetic_harvester':
            self.strategy.addItem('Maximum output in sampled loads','maximum_output');self.strategy.addItem('Balanced sampled output and efficiency','balanced')
            self.strategy.addItem('Maximum efficiency in sampled loads','maximum_efficiency')
        self.strategy.setCurrentIndex(max(0,self.strategy.findData(component.config.get('strategy',''))))
        self.strategy.setAccessibleName('Operating strategy');controls.addWidget(self.strategy,1)
        self.run=QPushButton('Recalculate');controls.addWidget(self.run);self.cancel=QPushButton('Cancel');controls.addWidget(self.cancel)
        layout.addLayout(controls);self.status=plain('Ready to calculate actual model outputs.');layout.addWidget(self.status)
        self.model=ResultTableModel(parent=self);self.results=QTableView();self.results.setModel(self.model);self.results.setMaximumHeight(250)
        self.results.setAccessibleName('Actual recalculated values and units');layout.addWidget(self.results)
        self.note=plain('',role='secondary');layout.addWidget(self.note)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(250);self.timer.timeout.connect(self.recalculate)
        self.strategy.currentIndexChanged.connect(self.schedule);self.run.clicked.connect(self.recalculate);self.cancel.clicked.connect(self.stop)
        self.recalculate()

    def schedule(self,*_):
        if not self._disposed:self.timer.start()

    def recalculate(self):
        if self._disposed:return
        self.timer.stop();self._revision+=1;revision=self._revision
        if self._token is not None:self._token.cancel('New calculator inputs replaced the previous calculation.')
        try:
            values={key:float(field.text().strip()) for key,field in self.inputs.items()}
            if any(not math.isfinite(value) for value in values.values()):raise ValueError('Use finite numeric quantities.')
        except ValueError as exc:self.failed('Invalid input: '+str(exc));return
        self.run.setEnabled(False);self.status.setText('Calculating with the existing guarded scientific backend…')
        strategy=self.strategy.currentData()
        def done(value):
            if self._disposed or revision!=self._revision:return
            self._token=None;self.run.setEnabled(True);self.last_result=value
            rows=[{'quantity':key.replace('_',' '),'value':number,'unit':value['units'].get(key,'')} for key,number in value['outputs'].items()]
            self.model.set_page(rows,('quantity','value','unit'));self.results.resizeColumnsToContents()
            self.status.setText('Calculation verified · '+value['provenance']+f' · {value["elapsed_ms"]:.1f} ms')
            self.note.setText(value['limitations']+('\n'+value['strategy_note'] if strategy else ''))
            self.context.save_config(strategy=strategy,values=values)
        self._token=self.context.submit(self,'Interactive model calculation',
            lambda token:calculate(self.context.sources,self.component.source,values,strategy=strategy,cancellation=token),done,self.failed,cancellable=True)

    def failed(self,error):
        if self._disposed:return
        self.run.setEnabled(True);self.last_result=None;self.model.set_page([]);self.status.setText(str(error))
        self.note.setText('No new result is established for these inputs.')

    def stop(self):
        self.timer.stop();self._revision+=1
        if self._token is not None:self._token.cancel('Calculation cancelled by user.');self._token=None
        self.run.setEnabled(True);self.status.setText('Calculation cancelled; saved experiment unchanged.')

    def dispose(self):self.stop();self._disposed=True;self.model.set_page([])


class ProgressView(QWidget):
    def __init__(self,component,context):
        super().__init__();self.component=component;self.context=context;self._disposed=False;self._loading=False
        layout=QVBoxLayout(self);self.status=plain('Reading actual job state…');layout.addWidget(self.status)
        self.progress=QProgressBar();layout.addWidget(self.progress);self.details=plain('',role='secondary');layout.addWidget(self.details)
        controls=QHBoxLayout();layout.addLayout(controls)
        actions=('run','pause','cancel') if component.source.kind=='experiment' else ('cancel',) if component.source.kind=='media_generation' else ()
        self.buttons=[]
        for action in actions:
            button=QPushButton(action.title());button.clicked.connect(lambda _=False,verb=action:self.control(verb));controls.addWidget(button);self.buttons.append(button)
        self.timer=QTimer(self);self.timer.setInterval(round(component.config.get('refresh_seconds',1.5)*1000));self.timer.timeout.connect(self.refresh)
        self.apply(context.snapshot)

    def apply(self,snapshot):
        self.context.snapshot=snapshot;data=snapshot.data;status=str(data.get('status','Unknown')).upper()
        self.status.setText('Actual state: '+status.replace('_',' ').title())
        completed=data.get('completed_runs');planned=data.get('estimate',{}).get('planned_runs')
        if type(completed) is int and type(planned) is int and 0<=completed<=planned and planned>0:
            self.progress.setRange(0,planned);self.progress.setValue(completed);self.details.setText(f'{completed:,} / {planned:,} saved runs')
        else:self.progress.setRange(0,0);self.details.setText('No measured completion fraction is available for this stage.')
        terminal={'SUCCEEDED','COMPLETED','COMPLETED_WITH_WARNINGS','FAILED','CANCELLED','INTERRUPTED','PREPARED','PAUSED','PARTIAL','VERIFIED'}
        if status=='PLANNED':self.details.setText('Source proposal is waiting for native review and apply. No build has completed.')
        for button in self.buttons:
            action=button.text().casefold()
            button.setEnabled(status in {'PREPARED','PAUSED','CANCELLED','INTERRUPTED'} if action=='run' else
                status in {'QUEUED','RUNNING'} if action=='pause' else status not in terminal or status in {'PREPARED','PAUSED'})
        if status in terminal:
            self.timer.stop()
            if completed is None:self.progress.setRange(0,1);self.progress.setValue(1 if status=='SUCCEEDED' else 0);self.progress.setTextVisible(False)
        elif not self.timer.isActive():self.timer.start()

    def refresh(self):
        if self._disposed or self._loading:return
        self._loading=True
        def ready(snapshot):self._loading=False;self.apply(snapshot)
        def failed(error):self._loading=False;self.timer.stop();self.status.setText(str(error))
        self.context.submit(self,'Read actual job progress',lambda:self.context.sources.resolve(self.component.source),ready,failed)

    def control(self,action):
        for button in self.buttons:button.setEnabled(False)
        def done(result):
            for button in self.buttons:button.setEnabled(True)
            self.status.setText(result.message);self.refresh()
        def failed(error):
            for button in self.buttons:button.setEnabled(True)
            self.status.setText(str(error))
        self.context.action(self,action,done=done,failed=failed)

    def dispose(self):self._disposed=True;self.timer.stop()


class ValidationView(QWidget):
    def __init__(self,component,context):
        super().__init__();self.component=component;self.context=context;self._disposed=False
        outer=QVBoxLayout(self);self.refresh_button=QPushButton('Refresh recorded checks');outer.addWidget(self.refresh_button)
        self.refresh_button.clicked.connect(self.refresh)
        self.body=QWidget();self.body_layout=QVBoxLayout(self.body);outer.addWidget(self.body);self.apply(context.snapshot)

    def apply(self,snapshot):
        self.context.snapshot=snapshot;layout=self.body_layout;data=snapshot.data
        while layout.count():
            item=layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        if snapshot.source.kind=='experiment':
            summary=data.get('summary',{})
            for key in ('valid_runs','invalid_runs','infeasible_runs'):
                if key in summary:layout.addWidget(plain(key.replace('_',' ').title()+': '+display(summary[key])))
            layout.addWidget(plain('Valid computational runs are not physical or scientific validation.',role='secondary'))
        elif snapshot.source.kind=='build_session':
            for stage,state in data.get('health',{}).items():layout.addWidget(plain(stage.title()+': '+str(state)))
            for receipt in data.get('command_evidence',[])[-12:]:
                layout.addWidget(plain(str(receipt.get('stage','Command'))+': '+str(receipt.get('status','Unavailable'))+
                    ' · exit '+str(receipt.get('exitCode',receipt.get('exit_code',receipt.get('returncode','unavailable'))))))
                output=str(receipt.get('stdout',''))+'\n'+str(receipt.get('stderr',''))
                if output.strip():layout.addWidget(plain(output[-1600:],role='secondary'))
            layout.addWidget(plain('These are recorded checks for that build; current untested changes are not certified.',role='secondary'))
        else:
            execution=data.get('execution',{});verification=execution.get('verification') or {}
            layout.addWidget(plain('Recorded operation verification: '+str(verification.get('status','Unavailable'))))
            for evidence in verification.get('evidence',[])[:20]:layout.addWidget(plain(evidence,role='secondary'))
        layout.addWidget(plain(snapshot.limitation,role='secondary'))

    def refresh(self):
        self.refresh_button.setEnabled(False)
        def done(snapshot):self.refresh_button.setEnabled(True);self.apply(snapshot)
        def failed(error):self.refresh_button.setEnabled(True);self.body_layout.addWidget(plain(str(error),role='secondary'))
        self.context.submit(self,'Refresh actual validation receipts',lambda:self.context.sources.resolve(self.component.source),done,failed)

    def dispose(self):self._disposed=True


class ComparisonView(QWidget):
    def __init__(self,component,context):
        super().__init__();layout=QVBoxLayout(self);cards=FlowLayout();layout.addLayout(cards)
        rows=context.snapshot.rows;requested=component.config.get('fields')
        if requested:rows=[row for row in rows if row.get('parameter') in requested]
        for row in rows[-8:]:
            first=row.get('first');second=row.get('second');unit=row.get('unit','')
            card=QFrame();card.setProperty('role','surface');card.setMinimumWidth(180);body=QVBoxLayout(card)
            body.addWidget(plain(row.get('parameter','Value').replace('_',' '),role='secondary'))
            body.addWidget(plain(display(first,unit)+' → '+display(second,unit)))
            if type(first) in (int,float) and type(second) in (int,float):
                change=second-first;relative=f'{change/abs(first)*100:+.3g}%' if first else 'relative change undefined at zero baseline'
                body.addWidget(plain('Change: '+display(change,unit)+' · '+relative,role='secondary'))
            cards.addWidget(card)
        if not rows:layout.addWidget(plain('No aligned comparison values are available.'))
        layout.addWidget(plain(context.snapshot.limitation,role='secondary'))

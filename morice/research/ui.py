"""Compact project/experiment inspection using actual persistent job progress."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox,QDialog,QHBoxLayout,QLabel,QLineEdit,QPlainTextEdit,
    QProgressBar,QPushButton,QTableWidget,QTableWidgetItem,QVBoxLayout,QSlider,QCheckBox)
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtCore import QByteArray,QItemSelectionModel


class ResearchDialog(QDialog):
    def __init__(self, runtime, project_id="", parent=None):
        super().__init__(parent)
        self.runtime=runtime
        self.project_id=project_id
        self.manager=runtime.laboratory
        self.future=None
        self.evidence_ids=()
        self.trajectory=[]
        self.inspection_mode=False
        self.pool=ThreadPoolExecutor(1,thread_name_prefix="morice-research-panel")
        self.setWindowTitle("Research projects")
        self.resize(980,720)
        layout=QVBoxLayout(self)
        self.projects=QComboBox()
        for p in runtime.store.list_projects():
            self.projects.addItem(p['objective'][:100],p['id'])
        selected=self.projects.findData(project_id)
        if selected>=0: self.projects.setCurrentIndex(selected)
        self.projects.currentIndexChanged.connect(self.refresh)
        layout.addWidget(self.projects)
        self.status=QLabel("Structured projects and computational experiments")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.evidence=QComboBox();self.evidence.currentIndexChanged.connect(self.inspect_evidence);layout.addWidget(self.evidence)
        self.filter=QLineEdit()
        self.filter.setPlaceholderText("Filter experiments by title or status")
        self.filter.textChanged.connect(self.refresh)
        layout.addWidget(self.filter)
        self.experiments=QTableWidget(0,5)
        self.experiments.setHorizontalHeaderLabels(["Experiment","Status","Completed","Planned","Error"])
        self.experiments.setSelectionBehavior(QTableWidget.SelectRows)
        self.experiments.setSelectionMode(QTableWidget.ExtendedSelection)
        self.experiments.setEditTriggers(QTableWidget.NoEditTriggers)
        self.experiments.setSortingEnabled(True)
        self.experiments.itemSelectionChanged.connect(self.select)
        layout.addWidget(self.experiments)
        self.progress=QProgressBar();self.progress.setValue(0);layout.addWidget(self.progress)
        buttons=QHBoxLayout()
        for label,action in (("Run / Resume",self.manager.start),("Pause",self.manager.pause),("Cancel",self.manager.cancel)):
            button=QPushButton(label)
            button.clicked.connect(lambda checked=False,fn=action:self.control(fn))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        compare=QPushButton("Compare two selected experiments");compare.clicked.connect(self.compare);layout.addWidget(compare)
        self.run_filter=QLineEdit();self.run_filter.setPlaceholderText("Filter actual runs by status, parameter or output")
        self.run_filter.textChanged.connect(self.select);layout.addWidget(self.run_filter)
        self.runs=QTableWidget(0,4)
        self.runs.setHorizontalHeaderLabels(["Run","Parameters (SI)","Status","Outputs / warnings"])
        self.runs.setEditTriggers(QTableWidget.NoEditTriggers)
        self.runs.setSortingEnabled(True)
        layout.addWidget(self.runs)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(120)
        layout.addWidget(self.detail)
        self.plot=QSvgWidget();self.plot.setFixedHeight(140);layout.addWidget(self.plot)
        playback=QHBoxLayout()
        self.scrub=QSlider(Qt.Horizontal);self.scrub.valueChanged.connect(self.frame)
        self.play=QPushButton("Play / Pause");self.play.clicked.connect(self.toggle_play)
        step=QPushButton("Step");step.clicked.connect(lambda:self.scrub.setValue(min(self.scrub.maximum(),self.scrub.value()+1)))
        self.speed=QComboBox();self.speed.addItems(["1×","2×","4×"])
        self.trails=QCheckBox("Trails");self.trails.setChecked(True);self.trails.toggled.connect(self.frame)
        for widget in (self.play,step,self.speed,self.trails,self.scrub):playback.addWidget(widget)
        layout.addLayout(playback)
        self.frame_status=QLabel();layout.addWidget(self.frame_status)
        self.play_timer=QTimer(self);self.play_timer.setInterval(100);self.play_timer.timeout.connect(self.advance)
        self.plot.hide()
        self.specification=QPlainTextEdit()
        self.specification.setPlaceholderText('Paste an experiment JSON specification, then prepare and explicitly run it.')
        self.specification.setMaximumHeight(110)
        layout.addWidget(self.specification)
        prepare=QPushButton("Prepare reviewed computational specification")
        prepare.clicked.connect(self.prepare);layout.addWidget(prepare)
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.tick);self.timer.start()
        self.refresh()

    def selected_id(self):
        row=self.experiments.currentRow()
        item=self.experiments.item(row,0)
        return item.data(Qt.UserRole) if item else None

    def refresh(self,*_):
        selected=self.selected_id()
        selections={self.experiments.item(i.row(),0).data(Qt.UserRole) for i in self.experiments.selectionModel().selectedRows()}
        self.project_id=self.projects.currentData() or self.project_id
        rows=self.manager.list(self.project_id) if self.project_id else []
        text=self.filter.text().casefold()
        rows=[r for r in rows if text in (r['title']+' '+r['status']).casefold()]
        self.experiments.blockSignals(True);self.experiments.setSortingEnabled(False)
        self.experiments.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate((row['title'],row['status'],row['completed_runs'],row['estimate']['planned_runs'],row['error'])):
                item=QTableWidgetItem();item.setData(Qt.DisplayRole,value);item.setData(Qt.UserRole,row['id']);self.experiments.setItem(i,j,item)
        self.experiments.setSortingEnabled(True)
        for i in range(self.experiments.rowCount()):
            if self.experiments.item(i,0).data(Qt.UserRole) in selections:
                self.experiments.selectionModel().select(self.experiments.model().index(i,0),QItemSelectionModel.Select|QItemSelectionModel.Rows)
            if self.experiments.item(i,0).data(Qt.UserRole)==selected:
                self.experiments.selectionModel().setCurrentIndex(self.experiments.model().index(i,0),QItemSelectionModel.NoUpdate)
        self.experiments.blockSignals(False)
        if self.project_id:
            p=self.runtime.project(self.project_id)
            self.status.setText(f"{p.objective}\n{len(p.select('question'))} questions · {len(p.select('hypothesis'))} current hypotheses · {sum(r['stale'] for r in p.records)} stale records")
            ids=tuple((r['id'],r['stale'],r['revision']) for r in p.records)
            if ids!=self.evidence_ids:
                current=self.evidence.currentData();self.evidence.blockSignals(True);self.evidence.clear()
                self.evidence.addItem('Project timeline','timeline')
                for r in p.records:self.evidence.addItem(f"{r['kind']} · {r['provenance']} · {r['title']}"+(' · STALE' if r['stale'] else ''),r['id'])
                self.evidence.setCurrentIndex(max(0,self.evidence.findData(current)));self.evidence.blockSignals(False);self.evidence_ids=ids

    def select(self):
        self.inspection_mode=False
        identifier=self.selected_id()
        if not identifier:return
        row=self.manager.get(identifier,True)
        self.progress.setRange(0,row['estimate']['planned_runs']);self.progress.setValue(row['completed_runs'])
        self.detail.setPlainText(json.dumps({'summary':row['summary'],'error':row['error'],'specification':row['spec']},indent=2))
        # Display at most 500 actual rows; the complete matrix remains on disk.
        text=self.run_filter.text().casefold()
        runs=[r for r in row['runs'] if text in json.dumps(r).casefold()]
        self.runs.setSortingEnabled(False);self.runs.setRowCount(min(500,len(runs)))
        for i,run in enumerate(runs[:500]):
            for j,value in enumerate((run['run_index'],json.dumps(run['parameters']),run['status'],json.dumps(run['outputs'])+' '+run['error'])):
                item=QTableWidgetItem();item.setData(Qt.DisplayRole,value);self.runs.setItem(i,j,item)
        self.runs.setSortingEnabled(True)

    def compare(self):
        self.inspection_mode=True
        ids={self.experiments.item(i.row(),0).data(Qt.UserRole) for i in self.experiments.selectionModel().selectedRows()}
        if len(ids)!=2:self.detail.setPlainText('Select exactly two experiments to compare.');return
        try:self.detail.setPlainText(json.dumps(self.manager.compare(*sorted(ids)),indent=2))
        except Exception as exc:self.detail.setPlainText(str(exc))

    def inspect_evidence(self,*_):
        self.inspection_mode=True
        if not self.project_id:return
        snapshot=self.runtime.store.snapshot(self.project_id);identifier=self.evidence.currentData()
        record=next((r for r in snapshot['records'] if r['id']==identifier),None)
        self.detail.setPlainText(json.dumps(record or snapshot['timeline'][-50:],indent=2,ensure_ascii=False))
        self.trajectory=record['payload'].get('result',{}).get('rows',[]) if record and isinstance(record['payload'].get('result'),dict) else []
        self.play_timer.stop();self.plot.setVisible(bool(self.trajectory));self.scrub.setRange(0,max(0,len(self.trajectory)-1));self.scrub.setValue(0);self.frame()

    def toggle_play(self):
        if self.play_timer.isActive():self.play_timer.stop()
        elif self.trajectory:self.play_timer.start()

    def advance(self):
        next_frame=self.scrub.value()+2**self.speed.currentIndex()
        self.scrub.setValue(min(self.scrub.maximum(),next_frame))
        if next_frame>=self.scrub.maximum():self.play_timer.stop()

    def frame(self,*_):
        if not self.trajectory:return
        row=self.trajectory[self.scrub.value()]
        self.frame_status.setText(f"SIMULATED: t={row['time']:.6g} s · x={row['x']:.6g} m · y={row['y']:.6g} m · energy={row['kinetic_energy']:.6g} J")
        xs=[r['x'] for r in self.trajectory];ys=[r['y'] for r in self.trajectory];x0,x1=min(xs),max(xs);y0,y1=min(ys),max(ys)
        def xy(r):return f"{20+460*(r['x']-x0)/(x1-x0 or 1):.4f},{120-100*(r['y']-y0)/(y1-y0 or 1):.4f}"
        trail=' '.join(xy(r) for r in self.trajectory[:self.scrub.value()+1]) if self.trails.isChecked() else ''
        x,y=xy(row).split(',')
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 140"><rect width="500" height="140" fill="white"/><polyline points="{trail}" fill="none" stroke="#167a98"/><circle cx="{x}" cy="{y}" r="4" fill="#167a98"/></svg>'
        self.plot.load(QByteArray(svg.encode()))

    def control(self,action):
        identifier=self.selected_id()
        if not identifier:return
        try:action(identifier);self.refresh()
        except Exception as exc:self.detail.setPlainText(str(exc))

    def prepare(self):
        if self.future is not None:return
        try:
            spec=json.loads(self.specification.toPlainText())
            self.future=self.pool.submit(self.manager.prepare,spec,project_id=self.project_id or None)
        except Exception as exc:self.detail.setPlainText(str(exc))

    def tick(self):
        if self.future is not None and self.future.done():
            try:
                row=self.future.result();self.project_id=row['project_id']
                if self.projects.findData(self.project_id)<0:
                    self.projects.addItem(self.runtime.project(self.project_id).objective[:100],self.project_id)
                self.projects.setCurrentIndex(self.projects.findData(self.project_id))
            except Exception as exc:self.detail.setPlainText(str(exc))
            self.future=None
        self.refresh()
        if not self.inspection_mode:self.select()

    def closeEvent(self,event):
        if self.future is not None and not self.future.done():
            self.detail.setPlainText("Finishing bounded preparation before closing.");event.ignore();return
        self.timer.stop();self.play_timer.stop();self.pool.shutdown(wait=False,cancel_futures=True)
        super().closeEvent(event)

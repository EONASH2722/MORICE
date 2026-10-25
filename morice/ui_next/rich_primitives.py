"""Native, accessible rich cards and bounded table pages; no model UI code."""
from __future__ import annotations

import json
import math

from PySide6.QtCore import Qt,QAbstractTableModel,QModelIndex,Signal,QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QWidget,QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QLineEdit,QTableView,QAbstractItemView,QHeaderView,QListWidget)

from .responsive import FlowLayout


def plain(value,parent=None,*,role=''):
    label=QLabel(str(value),parent);label.setTextFormat(Qt.PlainText);label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.TextSelectableByKeyboard)
    label.setFocusPolicy(Qt.StrongFocus)
    if role:label.setProperty('role',role)
    return label


def field(data,key):
    if isinstance(data,dict) and key in data:return data[key]
    for part in str(key).split('.'):
        if not isinstance(data,dict) or part not in data:return None
        data=data[part]
    return data


def display(value,unit=''):
    if value is None:return 'Unavailable'
    if type(value) is bool:return 'Yes' if value else 'No'
    if type(value) in (int,float):
        if not math.isfinite(value):return 'Non-finite value unavailable'
        return (f'{value:,}' if type(value) is int else f'{value:,.6g}')+(' '+unit if unit else '')
    if isinstance(value,(list,dict)):return json.dumps(value,ensure_ascii=False,default=str)[:1200]
    return str(value)[:1200]


class MetricsView(QWidget):
    def __init__(self,component,context):
        super().__init__();snapshot=context.snapshot;layout=FlowLayout(self,spacing=10)
        fields=component.config.get('fields') or [key for key,value in snapshot.data.items() if type(value) in (int,float)][:8]
        for key in fields[:16]:
            card=QFrame();card.setProperty('role','surface');card.setMinimumWidth(150)
            body=QVBoxLayout(card);body.addWidget(plain(str(key).split('.')[-1].replace('_',' ').title(),role='secondary'))
            value=plain(display(field(snapshot.data,key),snapshot.units.get(key,'')))
            font=QFont(value.font());font.setPointSizeF(font.pointSizeF()+5);font.setBold(True);value.setFont(font)
            body.addWidget(value);body.addWidget(plain(snapshot.provenance,role='secondary'));layout.addWidget(card)
        if not fields:layout.addWidget(plain('No numeric metric fields are available from this source.'))


class StatusView(QWidget):
    def __init__(self,component,context):
        super().__init__();snapshot=context.snapshot;layout=QVBoxLayout(self)
        fields=component.config.get('fields') or [key for key in ('status','enabled','health','load_state','count','requirements') if key in snapshot.data]
        if fields:
            for key in fields[:16]:layout.addWidget(plain(str(key).replace('_',' ').title()+': '+display(field(snapshot.data,key))))
        else:layout.addWidget(plain('Source data was read. Open the workspace for its full details.'))
        layout.addWidget(plain('Source read verified' if snapshot.verified else 'No source verification receipt',role='secondary'))
        if snapshot.limitation:layout.addWidget(plain(snapshot.limitation,role='secondary'))


class ResultTableModel(QAbstractTableModel):
    def __init__(self,units=None,parent=None):
        super().__init__(parent);self.rows=[];self.columns=[];self.units=units or {}

    def set_page(self,rows,columns=()):
        self.beginResetModel();self.rows=rows[:200]
        self.columns=list(columns[:32]) if columns else [key for key in dict.fromkeys(key for row in self.rows for key in row) if not key.startswith('__source_row_id')][:24]
        self.endResetModel()

    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.columns)

    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.rows) or not 0<=index.column()<len(self.columns):return None
        row=self.rows[index.row()];value=row.get(self.columns[index.column()])
        if role in {Qt.DisplayRole,Qt.ToolTipRole}:return display(value)
        if role==Qt.UserRole:return row
        if role==Qt.TextAlignmentRole:return int(Qt.AlignRight|Qt.AlignVCenter) if type(value) in (int,float) else int(Qt.AlignLeft|Qt.AlignVCenter)
        return None

    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if role!=Qt.DisplayRole:return None
        if orientation==Qt.Vertical:return section+1
        if not 0<=section<len(self.columns):return None
        key=self.columns[section];unit=self.units.get(key,'')
        return key.replace('_',' ')+(' ['+unit+']' if unit else '')


class DataTableView(QWidget):
    row_selected=Signal(object)

    def __init__(self,component,context):
        super().__init__();self.component=component;self.context=context
        self.offset=0;self.total=0;self.limit=component.config.get('page_size',100);self._request=0
        self._selected_run=None
        self._selected_identity=None
        self.sort=component.config.get('sort');self._disposed=False
        layout=QVBoxLayout(self);bar=QHBoxLayout()
        self.search=QLineEdit();self.search.setPlaceholderText('Filter actual source records…');self.search.setAccessibleName('Filter source data')
        self.search.setText(component.config.get('filter',''));bar.addWidget(self.search,1)
        self.previous=QPushButton('Previous');self.next=QPushButton('Next');bar.addWidget(self.previous);bar.addWidget(self.next);layout.addLayout(bar)
        exports=QHBoxLayout()
        for format in ('csv','json'):
            button=QPushButton('Export source sample '+format.upper());exports.addWidget(button)
            button.clicked.connect(lambda _=False,f=format:self.context.action(self,'export_data',{'format':f},
                done=lambda result:self.status.setText(result.message),failed=lambda error:self.status.setText(str(error))))
        layout.addLayout(exports)
        self.model=ResultTableModel(context.snapshot.units,self)
        self.table=QTableView();self.table.setModel(self.model);self.table.setMinimumHeight(230);self.table.setMaximumHeight(380)
        self.table.setAccessibleName('Paged actual source data; select a row to highlight its chart point')
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True);layout.addWidget(self.table)
        self.status=plain('Loading actual source records…',role='secondary');layout.addWidget(self.status)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(200);self.timer.timeout.connect(self.filter_changed)
        self.search.textChanged.connect(lambda _text:self.timer.start())
        self.previous.clicked.connect(lambda:self.change_page(-1));self.next.clicked.connect(lambda:self.change_page(1))
        self.table.horizontalHeader().sectionClicked.connect(self.sort_column)
        self.table.clicked.connect(lambda index:self.row_selected.emit(self.model.rows[index.row()]))
        self.reload()

    def save_state(self):
        values={'filter':self.search.text()[:200]}
        if self.sort:values['sort']=self.sort
        if self.context.component.kind=='chart':values={'table_'+key:value for key,value in values.items()}
        self.context.save_config(**values)

    def filter_changed(self):self.offset=0;self.save_state();self.reload()

    def sort_column(self,index):
        if not 0<=index<len(self.model.columns):return
        key=self.model.columns[index];descending=not self.sort.get('descending',False) if self.sort and self.sort['field']==key else False
        self.sort={'field':key,'descending':descending};self.offset=0;self.save_state();self.reload()

    def change_page(self,direction):
        self.offset=max(0,self.offset+direction*self.limit);self.reload()

    def reload(self):
        if self._disposed:return
        self._request+=1;request=self._request
        self.previous.setEnabled(False);self.next.setEnabled(False);self.status.setText('Loading actual source records…')
        source=self.component.source;offset=self.offset;query=self.search.text()[:200];sort=self.sort
        def done(value):
            if self._disposed or request!=self._request:return
            self.total=value['count'];self.model.set_page(value['rows'],self.component.config.get('columns',()))
            self.previous.setEnabled(self.offset>0);self.next.setEnabled(self.offset+self.limit<self.total)
            self.status.setText(f'{self.offset+1 if self.total else 0}–{min(self.offset+len(value["rows"]),self.total)} of {self.total:,} source rows')
            if self._selected_run is not None:
                for index,row in enumerate(self.model.rows):
                    if row.get('run')==self._selected_run:
                        self.table.selectRow(index);self.table.scrollTo(self.model.index(index,0));self._selected_run=None;break
            if self._selected_identity is not None:self.select_identity(*self._selected_identity)
        self.context.submit(self,'Read response data page',
            lambda:self.context.sources.table_page(source,offset=offset,limit=self.limit,query=query,sort=sort),done,
            lambda error:self.status.setText(str(error)))

    def select_run(self,run_index):
        self._selected_run=run_index
        for index,row in enumerate(self.model.rows):
            if row.get('run')==run_index:self.table.selectRow(index);self.table.scrollTo(self.model.index(index,0));self._selected_run=None;return
        if self.component.source.kind=='experiment' and not self.search.text() and not self.sort:
            self.offset=(int(run_index)//self.limit)*self.limit;self.reload()
        self.status.setText(f'Chart point belongs to actual run {run_index}. Its data page is loading or filtered out.')

    def select_identity(self,key,value):
        self._selected_identity=(key,value)
        for index,row in enumerate(self.model.rows):
            if row.get(key)==value:
                self.table.selectRow(index);self.table.scrollTo(self.model.index(index,0));self._selected_identity=None;return
        if not self.search.text() and not self.sort:
            position=next((i for i,row in enumerate(self.context.snapshot.rows) if row.get(key)==value),None)
            if position is not None and (position//self.limit)*self.limit!=self.offset:
                self.offset=(position//self.limit)*self.limit;self.reload()

    def dispose(self):self._disposed=True;self.timer.stop()


class TimelineView(QWidget):
    def __init__(self,component,context):
        super().__init__();layout=QVBoxLayout(self);self.events=QListWidget();self.events.setMaximumHeight(300)
        self.events.setAccessibleName('Actual recorded events')
        rows=context.snapshot.data.get('timeline',context.snapshot.rows)
        for row in rows[-100:]:
            if isinstance(row,dict):
                label=' · '.join(display(row.get(key)) for key in ('timestamp','time','created','event','action','kind','stage','status','title') if row.get(key) is not None)
                payload=row.get('payload')
                if isinstance(payload,str) and len(payload)<=8192:
                    import json
                    try:payload=json.loads(payload)
                    except ValueError:payload=None
                if isinstance(payload,dict) and isinstance(payload.get('title'),str):label+=' · '+payload['title'][:200]
                if label:self.events.addItem(label)
        if not self.events.count():self.events.addItem('No recorded events are available from this source.')
        layout.addWidget(self.events)

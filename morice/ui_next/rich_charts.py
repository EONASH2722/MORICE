"""Extend the existing native ChartCanvas with real multiseries data and linked rows."""
from __future__ import annotations

import math

from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QPainter,QPen,QColor,QPainterPath
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QCheckBox,QPushButton

from ..pyside_app import ChartCanvas
from ..universal_engine import ChartArtifact
from .rich_primitives import DataTableView,plain,display
from .responsive import FlowLayout


def finite(value):return type(value) in (int,float) and math.isfinite(value)


class ResponseChartCanvas(ChartCanvas):
    row_selected=Signal(object)

    def __init__(self,context):
        super().__init__();self.context=context;self.rows=[];self.x='';self.ys=[];self.style='line'
        self.setMinimumHeight(280);self.setMaximumHeight(440);self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName('Actual source chart. Hover for values, click to select its data row. Wheel zooms, drag pans, Home resets, arrows inspect points.')
        self._points=[];self.selected=None;self.zoom=1.;self.pan=0.;self._drag=None;self._moved=False
        self.artifact=ChartArtifact('Actual source chart','line',[],{})

    def set_data(self,rows,x,ys,style='line',title='Actual source chart'):
        self.rows=rows[:1000];self.x=x;self.ys=ys[:8];self.style=style
        self.artifact.title=title;self.artifact.chart_type=style;self.selected=None;self.reset_view()

    def reset_view(self):self.zoom=1.;self.pan=0.;self.update()

    def color(self,index):
        if index==0:return QColor(self.context.theme.tokens['accent_primary'])
        if index==1:return QColor(self.context.theme.tokens['accent_secondary'])
        base=QColor(self.context.theme.tokens['accent_primary']);h,s,l,a=base.getHslF()
        return QColor.fromHslF((max(0,h)+index*.19)%1,max(.35,s),min(.75,max(.35,l)),a)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        tokens=self.context.theme.tokens;rect=self.rect();plot=QRectF(rect.adjusted(78,35,-24,-104))
        painter.fillRect(rect,QColor(tokens['surface']));self._points=[]
        points=[(index,row) for index,row in enumerate(self.rows) if finite(row.get(self.x))]
        values=[row[key] for _,row in points for key in self.ys if finite(row.get(key))]
        if not points or not values or plot.width()<30 or plot.height()<30:
            painter.setPen(QColor(tokens['text_secondary']));painter.drawText(rect,Qt.AlignCenter,'No finite source points for the selected axes.');painter.end();return
        xs=[row[self.x] for _,row in points];xscale=max(abs(v) for v in xs) or 1.;yscale=max(abs(v) for v in values) or 1.
        x0=min(v/xscale for v in xs);x1=max(v/xscale for v in xs)
        if x0==x1:x1=x0+1
        full=x1-x0;span=full/self.zoom;middle=(x0+x1)/2+self.pan*full;x0=middle-span/2;x1=middle+span/2
        y0=min(0.,min(v/yscale for v in values));y1=max(0.,max(v/yscale for v in values))
        if y0==y1:y1=y0+1
        def position(x,y):return QPointF(plot.left()+(x/xscale-x0)/(x1-x0)*plot.width(),plot.bottom()-(y/yscale-y0)/(y1-y0)*plot.height())
        painter.setFont(self.font())
        for index in range(5):
            y=plot.bottom()-index*plot.height()/4;x=plot.left()+index*plot.width()/4
            painter.setPen(QPen(QColor(tokens['border']),1));painter.drawLine(QPointF(plot.left(),y),QPointF(plot.right(),y))
            painter.setPen(QColor(tokens['text_secondary']))
            painter.drawText(QRectF(0,y-10,plot.left()-9,20),Qt.AlignRight|Qt.AlignVCenter,display((y0+(y1-y0)*index/4)*yscale))
            painter.drawText(QRectF(x-48,plot.bottom()+5,96,22),Qt.AlignHCenter|Qt.AlignVCenter,display((x0+(x1-x0)*index/4)*xscale))
        painter.save();painter.setClipRect(plot.adjusted(-2,-2,2,2))
        for series,key in enumerate(self.ys):
            color=self.color(series);painter.setPen(QPen(color,2));painter.setBrush(color);path=QPainterPath();first=True
            for index,row in points:
                if not finite(row.get(key)):first=True;continue
                point=position(row[self.x],row[key])
                if self.style=='line':
                    if first:path.moveTo(point);first=False
                    else:path.lineTo(point)
                elif self.style=='bar':
                    zero=position(row[self.x],0);width=max(2,min(20,plot.width()/max(1,len(points))/max(1,len(self.ys))*.8))
                    painter.fillRect(QRectF(point.x()+series*width, min(point.y(),zero.y()),width,max(1,abs(zero.y()-point.y()))),color)
                if plot.contains(point):
                    if self.style=='scatter' or len(points)<=60:painter.drawEllipse(point,3,3)
                    self._points.append((point,index,key))
            if self.style=='line':painter.setBrush(Qt.NoBrush);painter.drawPath(path)
        if self.selected is not None:
            for point,index,key in self._points:
                if index==self.selected:painter.setPen(QPen(QColor(tokens['text_primary']),2));painter.setBrush(Qt.NoBrush);painter.drawEllipse(point,6,6)
        painter.restore();painter.setPen(QColor(tokens['text_primary']))
        painter.drawText(QRectF(12,2,rect.width()-24,24),Qt.AlignCenter,self.artifact.title)
        xunit=self.context.snapshot.units.get(self.x,'');units={self.context.snapshot.units.get(key,'') for key in self.ys}
        yunit=next(iter(units)) if len(units)==1 else ''
        painter.drawText(QRectF(plot.left(),plot.bottom()+29,plot.width(),22),Qt.AlignCenter,self.x.replace('_',' ')+(' ['+xunit+']' if xunit else ''))
        if yunit:painter.drawText(QRectF(2,1,72,18),Qt.AlignCenter,yunit)
        left=12
        for index,key in enumerate(self.ys):
            painter.setPen(QPen(self.color(index),3));painter.drawLine(QPointF(left,rect.bottom()-37),QPointF(left+14,rect.bottom()-37))
            label=key.replace('_',' ')+' ['+(self.context.snapshot.units.get(key) or 'unit unspecified')+']'
            width=min(220,painter.fontMetrics().horizontalAdvance(label)+10)
            painter.setPen(QColor(tokens['text_primary']));painter.drawText(QRectF(left+20,rect.bottom()-48,width,22),Qt.AlignVCenter,painter.fontMetrics().elidedText(label,Qt.ElideRight,width))
            left+=width+34
            if left>rect.width()-150:break
        painter.setPen(QColor(tokens['text_secondary']));total=self.context.snapshot.data.get('completed_runs',len(self.rows))
        note=f'{self.context.snapshot.provenance} · {len(self.rows):,} actual rows'+(f' sampled from {total:,}' if total>len(self.rows) else '')
        painter.drawText(QRectF(12,rect.bottom()-22,rect.width()-24,20),Qt.AlignCenter,note)
        painter.end()

    def _inspect(self,index):
        if not 0<=index<len(self.rows):return
        self.selected=index;row=self.rows[index]
        identity=self.context.snapshot.data.get('row_identity_field','run')
        if identity in row:self.context.save_config(selected=str(row[identity]))
        parts=[self.x+' = '+display(row.get(self.x),self.context.snapshot.units.get(self.x,''))]
        parts.extend(key+' = '+display(row.get(key),self.context.snapshot.units.get(key,'')) for key in self.ys)
        self.inspected.emit(' · '.join(parts));self.update()

    def mouseMoveEvent(self,event):
        position=event.position()
        if self._drag is not None and event.buttons()&Qt.LeftButton:
            delta=position.x()-self._drag.x()
            if abs(delta)>2:self._moved=True
            self.pan-=delta/max(1,self.width()-102)/self.zoom;self._drag=position;self.update();event.accept();return
        if self._points:
            point,index,key=min(self._points,key=lambda item:(item[0].x()-position.x())**2+(item[0].y()-position.y())**2)
            if math.hypot(point.x()-position.x(),point.y()-position.y())<=25:self._inspect(index)
        event.accept()

    def mousePressEvent(self,event):
        self.setFocus();self._drag=event.position();self._moved=False;event.accept()

    def mouseReleaseEvent(self,event):
        if not self._moved and self._points:
            position=event.position();point,index,key=min(self._points,key=lambda item:(item[0].x()-position.x())**2+(item[0].y()-position.y())**2)
            if math.hypot(point.x()-position.x(),point.y()-position.y())<=30:self._inspect(index);self.row_selected.emit(self.rows[index])
        self._drag=None;event.accept()

    def wheelEvent(self,event):
        self.zoom=max(1.,min(100.,self.zoom*(1.2 if event.angleDelta().y()>0 else 1/1.2)));self.update();event.accept()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Home:self.reset_view()
        elif event.key() in {Qt.Key_Left,Qt.Key_Right}:
            index=0 if self.selected is None else self.selected+(1 if event.key()==Qt.Key_Right else -1)
            self._inspect(max(0,min(len(self.rows)-1,index)))
        elif event.key() in {Qt.Key_Return,Qt.Key_Enter} and self.selected is not None:self.row_selected.emit(self.rows[self.selected])
        else:return super().keyPressEvent(event)
        event.accept()


class ChartView(QWidget):
    def __init__(self,component,context):
        super().__init__();self.component=component;self.context=context;self._disposed=False
        layout=QVBoxLayout(self);controls=QHBoxLayout();self.x=QComboBox();self.style=QComboBox();self.style.addItems(['line','bar','scatter'])
        rows=context.snapshot.rows;self.numeric=[key for key in dict.fromkeys(k for row in rows for k in row) if any(finite(r.get(key)) for r in rows)]
        if component.config.get('x') and component.config['x'] not in self.numeric:raise ValueError('The requested chart axis has no numeric source values.')
        self.x.addItems(self.numeric);self.x.setCurrentText(component.config.get('x',self.numeric[0] if self.numeric else ''))
        self.x.setAccessibleName('Chart x axis');self.style.setCurrentText(component.config.get('style','line'));self.style.setAccessibleName('Chart style')
        controls.addWidget(self.x,1);controls.addWidget(self.style);reset=QPushButton('Reset view');controls.addWidget(reset);layout.addLayout(controls)
        exports=QHBoxLayout();exports.addStretch(1);self.export_format=QComboBox();self.export_format.addItems(['PNG','SVG','PDF']);exports.addWidget(self.export_format)
        export=QPushButton('Export chart…');exports.addWidget(export);layout.addLayout(exports)
        export.clicked.connect(lambda:self.context.action(self,'export_chart',{'format':self.export_format.currentText().casefold()},
            done=lambda result:self.values.setText(result.message),failed=lambda error:self.values.setText(str(error))))
        self.series={};series=FlowLayout();layout.addLayout(series)
        initial=component.config.get('ys',[key for key in self.numeric if key!=self.x.currentText()][:1])
        if any(key not in self.numeric for key in initial):raise ValueError('The requested chart series has no numeric source values.')
        first_unit=context.snapshot.units.get(initial[0],'') if initial else ''
        for key in list(dict.fromkeys([*initial,*self.numeric]))[:12]:
            if key==self.x.currentText():continue
            check=QCheckBox(key.replace('_',' '));check.setChecked(key in initial and context.snapshot.units.get(key,'')==first_unit);check.setAccessibleName('Show series '+key)
            check.toggled.connect(lambda _=False,k=key:self.series_changed(k));self.series[key]=check;series.addWidget(check)
        self.canvas=ResponseChartCanvas(context);layout.addWidget(self.canvas);reset.clicked.connect(self.canvas.reset_view)
        self.values=plain('Hover a source point for its exact values.',role='secondary');layout.addWidget(self.values)
        self.canvas.inspected.connect(self.values.setText)
        total=context.snapshot.data.get('completed_runs',len(rows));stride=context.snapshot.data.get('presentation_stride',1)
        self.note=plain(f'{len(rows):,} actual source rows plotted'+(f' from {total:,} saved runs (stride {stride}).' if stride>1 else '.')+' '+context.snapshot.provenance,role='secondary');layout.addWidget(self.note)
        self.table=None;self._layout=layout;self.table_toggle=None
        if component.config.get('table',False):
            self.table_toggle=QPushButton('Show data table');self.table_toggle.setCheckable(True);layout.addWidget(self.table_toggle)
            self.table_toggle.toggled.connect(self.toggle_table);self.canvas.row_selected.connect(self.point_selected)
            self.table_toggle.setChecked(component.config.get('table_expanded',False))
        self.x.currentTextChanged.connect(self.refresh);self.style.currentTextChanged.connect(self.refresh);self.refresh()

    def series_changed(self,key):
        if self.series[key].isChecked():
            unit=self.context.snapshot.units.get(key,'')
            for other,check in self.series.items():
                if other!=key and check.isChecked() and self.context.snapshot.units.get(other,'')!=unit:
                    check.blockSignals(True);check.setChecked(False);check.blockSignals(False)
        self.refresh()

    def refresh(self,*_):
        keys=[key for key,check in self.series.items() if check.isChecked() and key!=self.x.currentText()]
        self.canvas.set_data(self.context.snapshot.rows,self.x.currentText(),keys,self.style.currentText(),self.component.title)
        selected=self.context.component.config.get('selected')
        identity=self.context.snapshot.data.get('row_identity_field','run')
        if selected is not None:
            for index,row in enumerate(self.canvas.rows):
                if identity in row and str(row[identity])==selected:self.canvas._inspect(index);break
        self.context.save_config(x=self.x.currentText(),ys=keys,style=self.style.currentText())

    def toggle_table(self,checked):
        if checked and self.table is None:
            from ..rich_response import Component
            config=self.context.component.config
            state={key:config['table_'+key] for key in ('filter','sort') if 'table_'+key in config}
            self.table=DataTableView(Component('table',self.component.source,config=state),self.context);self._layout.addWidget(self.table)
            self.table.row_selected.connect(self.select_row)
        if self.table is not None:self.table.setVisible(checked)
        self.table_toggle.setText('Hide data table' if checked else 'Show data table')
        self.context.save_config(table_expanded=checked)

    def point_selected(self,row):
        if self.table_toggle is None:return
        self.table_toggle.setChecked(True)
        if self.table is not None and 'run' in row:self.table.select_run(row['run'])
        elif self.table is not None:
            key=self.context.snapshot.data.get('row_identity_field')
            if key:self.table.select_identity(key,row.get(key))

    def select_row(self,row):
        identity=self.context.snapshot.data.get('row_identity_field','run')
        for index,candidate in enumerate(self.context.snapshot.rows):
            if candidate.get(identity,candidate)==row.get(identity,row):self.canvas._inspect(index);break

    def dispose(self):
        self._disposed=True;self.canvas.rows=[];self.canvas._points=[]
        if self.table:self.table.dispose()

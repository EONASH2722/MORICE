"""Native projected views of verified STL vertices and actual part collections."""
from __future__ import annotations

import math

from PySide6.QtCore import Qt,QPointF,Signal
from PySide6.QtGui import QPainter,QPen,QColor,QPolygonF
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QCheckBox,QSlider,QListWidget,QListWidgetItem,QGridLayout

from ..rich_response.mesh import load_stl
from .rich_primitives import plain,display


class MeshCanvas(QWidget):
    view_changed=Signal()
    def __init__(self,theme,*,thumbnail=False):
        super().__init__();self.theme=theme;self.parts=[];self.hidden=set();self.selected='';self.wireframe=False
        self.explode=0.;self.yaw=.65;self.pitch=.55;self.zoom=1.;self._drag=None;self.thumbnail=thumbnail
        self.setMinimumHeight(110 if thumbnail else 310);self.setMaximumHeight(170 if thumbnail else 480)
        self.setFocusPolicy(Qt.StrongFocus);self.setAccessibleName('Actual STL geometry. Drag rotates, wheel zooms, Home fits the model.')

    def set_parts(self,parts):self.parts=parts;self.update()
    def reset_view(self):self.yaw=.65;self.pitch=.55;self.zoom=1.;self.update();self.view_changed.emit()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        tokens=self.theme.tokens;painter.fillRect(self.rect(),QColor(tokens['surface']))
        visible=[p for p in self.parts if p['artifact'].id not in self.hidden]
        if not visible:
            painter.setPen(QColor(tokens['text_secondary']));painter.drawText(self.rect(),Qt.AlignCenter,'No visible verified mesh parts.');painter.end();return
        low=[min(part['mesh'].minimum[axis]+part['translation'][axis] for part in visible) for axis in range(3)]
        high=[max(part['mesh'].maximum[axis]+part['translation'][axis] for part in visible) for axis in range(3)]
        center=[(a+b)/2 for a,b in zip(low,high)];span=max(b-a for a,b in zip(low,high)) or 1.
        scale=min(self.width(),self.height())*.72*self.zoom/(span*(1+self.explode*.65))
        cy,sy=math.cos(self.yaw),math.sin(self.yaw);cp,sp=math.cos(self.pitch),math.sin(self.pitch)
        polygons=[];budget=250 if self.thumbnail else 2500 if self.theme.profile.quality=='LOW' else 6000
        for number,part in enumerate(visible):
            mesh=part['mesh'];vertices=mesh.vertices;translation=part['translation']
            centroid=[(mesh.minimum[i]+mesh.maximum[i])/2+translation[i]-center[i] for i in range(3)]
            length=math.sqrt(sum(v*v for v in centroid))
            direction=[v/length for v in centroid] if length>span*1e-6 else [math.cos(number*math.tau/max(1,len(visible))),math.sin(number*math.tau/max(1,len(visible))),.35]
            offset=[translation[i]-center[i]+direction[i]*span*self.explode*.45 for i in range(3)]
            stride=max(1,math.ceil(mesh.triangles/max(1,budget//len(visible))))
            base=QColor(tokens['accent_primary'] if number%2==0 else tokens['accent_secondary'])
            for triangle in range(0,mesh.triangles,stride):
                points=[];depth=0.;start=triangle*9
                for index in range(3):
                    x,y,z=(vertices[start+index*3+axis]+offset[axis] for axis in range(3))
                    xr=cy*x-sy*y;yr=sy*x+cy*y;vertical=cp*yr-sp*z;depth+=sp*yr+cp*z
                    points.append(QPointF(self.width()/2+xr*scale,self.height()/2-vertical*scale))
                area=(points[1].x()-points[0].x())*(points[2].y()-points[0].y())-(points[1].y()-points[0].y())*(points[2].x()-points[0].x())
                color=base.lighter(110 if area>0 else 80);polygons.append((depth,QPolygonF(points),color,part['artifact'].id==self.selected))
        for depth,polygon,color,selected in sorted(polygons,key=lambda item:item[0]):
            painter.setBrush(Qt.NoBrush if self.wireframe else color)
            painter.setPen(QPen(QColor(tokens['text_primary']) if selected else QColor(tokens['border']),1.8 if selected else .5));painter.drawPolygon(polygon)
        painter.end()

    def mousePressEvent(self,event):self._drag=event.position();self.setFocus();event.accept()
    def mouseReleaseEvent(self,event):self._drag=None;self.view_changed.emit();event.accept()
    def mouseMoveEvent(self,event):
        if self._drag is not None:
            delta=event.position()-self._drag;self.yaw+=delta.x()*.01;self.pitch=max(-1.5,min(1.5,self.pitch+delta.y()*.01));self._drag=event.position();self.update()
        event.accept()
    def wheelEvent(self,event):self.zoom=max(.15,min(12.,self.zoom*(1.15 if event.angleDelta().y()>0 else 1/1.15)));self.update();self.view_changed.emit();event.accept()
    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Home:self.reset_view();event.accept()
        else:super().keyPressEvent(event)


class MeshView(QWidget):
    def __init__(self,component,context):
        super().__init__();self.component=component;self.context=context;self._disposed=False;self.parts=[];self.thumbnails=[]
        layout=QVBoxLayout(self);controls=QHBoxLayout();self.wire=QCheckBox('Wireframe');self.wire.setChecked(component.config.get('wireframe',False));controls.addWidget(self.wire)
        for name,yaw,pitch in (('Isometric',.65,.55),('Front',0.,0.),('Side',math.pi/2,0.),('Top',0.,math.pi/2)):
            button=QPushButton(name);button.clicked.connect(lambda _=False,y=yaw,p=pitch:self.camera(y,p));controls.addWidget(button)
        fit=QPushButton('Fit');fit.clicked.connect(lambda:self.canvas.reset_view());controls.addWidget(fit);layout.addLayout(controls)
        self.canvas=MeshCanvas(context.theme);layout.addWidget(self.canvas);self.wire.toggled.connect(self.change_wireframe)
        for key,value in component.config.get('camera',{}).items():setattr(self.canvas,key,value)
        self.canvas.view_changed.connect(self.save_camera)
        self.status=plain('Reading the actual verified STL bytes…');layout.addWidget(self.status)
        self.explode=None
        if component.kind=='assembly':
            layout.addWidget(plain('Exploded view changes display offsets; original CAD geometry and exported files stay unchanged.',role='secondary'))
            self.explode=QSlider(Qt.Horizontal);self.explode.setRange(0,200);self.explode.setValue(round(component.config.get('explode',0)*100))
            self.explode.setAccessibleName('Exploded assembly separation');self.explode.valueChanged.connect(self.change_explode);layout.addWidget(self.explode)
        self.part_list=QListWidget();self.part_list.setMaximumHeight(150);self.part_list.setAccessibleName('Actual mesh parts; uncheck to hide, select to highlight')
        self.part_list.itemChanged.connect(self.part_visibility);self.part_list.currentItemChanged.connect(self.part_selected);layout.addWidget(self.part_list)
        self.grid=QGridLayout();layout.addLayout(self.grid)
        all_files=[a for a in context.snapshot.artifacts if a.path.suffix.casefold()=='.stl']
        files=[a for a in all_files if a.available];self._expected_parts=len(all_files)
        selected=component.config.get('artifact')
        if selected:files=[a for a in files if a.id==selected]
        if not files:
            self.status.setText('No actual STL artifact is available. STEP preview is unavailable: no tested CAD backend is installed.');return
        if len(files)>12:raise ValueError('Interactive assembly limit is twelve actual parts.')
        def load():
            parts=[];total=0;payload=context.snapshot.data.get('result',context.snapshot.data)
            declared=payload.get('parts',[]) if isinstance(payload,dict) else []
            for artifact in files:
                mesh=load_stl(artifact.path,artifact.sha256,context.sources.current_cancellation());total+=mesh.triangles
                if total>150000:raise ValueError('Assembly preview exceeds the 150,000-triangle total bound.')
                entry=next((p for i,p in enumerate(declared) if 'part:'+str(p.get('id',i))==artifact.id),{})
                if entry.get('rotation') or entry.get('matrix'):raise ValueError('This assembly transform needs a tested CAD adapter; it is not displayed as an untransformed substitute.')
                translation=entry.get('translation',[0,0,0])
                if not isinstance(translation,(list,tuple)) or len(translation)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e6 for v in translation):
                    raise ValueError('Part translations must be explicit finite geometry data.')
                parts.append({'artifact':artifact,'mesh':mesh,'translation':tuple(translation)})
            units={part['artifact'].unit for part in parts if part['artifact'].unit}
            if len(units)>1:raise ValueError('Part units differ; normalize them through the CAD/source owner before combining.')
            return parts
        context.submit(self,'Load actual STL geometry',load,self.loaded,lambda error:self.status.setText(str(error)))

    def loaded(self,parts):
        if self._disposed:return
        self.parts=parts;self.canvas.set_parts(parts);self.canvas.wireframe=self.wire.isChecked();self.canvas.explode=(self.explode.value()/100 if self.explode else 0)
        self.part_list.blockSignals(True)
        for part in parts:
            artifact=part['artifact'];item=QListWidgetItem(artifact.name);item.setData(Qt.UserRole,artifact.id);item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if artifact.id in self.component.config.get('hidden',[]) else Qt.Checked);self.part_list.addItem(item)
        self.part_list.blockSignals(False);self.part_visibility()
        selected=self.component.config.get('selected')
        if selected:
            for i in range(self.part_list.count()):
                if self.part_list.item(i).data(Qt.UserRole)==selected:self.part_list.setCurrentRow(i);break
        total=sum(part['mesh'].triangles for part in parts);bad=sum(part['mesh'].degenerate_faces for part in parts)
        unit=next((part['artifact'].unit for part in parts if part['artifact'].unit),'unspecified (STL does not encode units)')
        self.status.setText(f'{len(parts)} / {self._expected_parts} actual part(s) available · {total:,} triangles · {bad:,} degenerate faces · source units: {unit}. Missing/changed parts are not displayed. Large redraws use representative actual faces; no strength or manufacturability validation is claimed.')
        if self.component.kind=='assembly':
            for index,part in enumerate(parts):
                view=QWidget();box=QVBoxLayout(view);thumb=MeshCanvas(self.context.theme,thumbnail=True);thumb.set_parts([part]);box.addWidget(thumb)
                button=QPushButton(part['artifact'].name);button.clicked.connect(lambda _=False,i=index:self.part_list.setCurrentRow(i));box.addWidget(button)
                self.grid.addWidget(view,index//3,index%3);self.thumbnails.append(thumb)

    def camera(self,yaw,pitch):self.canvas.yaw=yaw;self.canvas.pitch=pitch;self.canvas.update();self.save_camera()
    def save_camera(self):self.context.save_config(camera={key:getattr(self.canvas,key) for key in ('yaw','pitch','zoom')})
    def change_wireframe(self,checked):self.canvas.wireframe=checked;self.canvas.update();self.context.save_config(wireframe=checked)
    def change_explode(self,value):self.canvas.explode=value/100;self.canvas.update();self.context.save_config(explode=value/100)
    def part_visibility(self,*_):
        hidden=[self.part_list.item(i).data(Qt.UserRole) for i in range(self.part_list.count()) if self.part_list.item(i).checkState()!=Qt.Checked]
        self.canvas.hidden=set(hidden);self.canvas.update()
        if self.component.kind=='assembly':self.context.save_config(hidden=hidden)
    def part_selected(self,item,previous=None):
        if item:self.canvas.selected=item.data(Qt.UserRole);self.canvas.update();self.context.save_config(selected=self.canvas.selected)
    def dispose(self):
        self._disposed=True;self.parts=[];self.canvas.parts=[]
        for thumbnail in self.thumbnails:thumbnail.parts=[]
        self.thumbnails=[]

"""Original software-painted orbital presence, separate from MORICE's logo."""
from __future__ import annotations

from collections import deque
from functools import lru_cache
import math
import time

from PySide6.QtCore import Qt, QPointF, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient, QBrush
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy

from .core_state import CoreState, CoreSnapshot
from .theme_scenes import LOOP_SECONDS, loop_angle, scene_points


def core_color(snapshot, tokens):
    state = snapshot.state
    if state == CoreState.SECURITY_ALERT: return QColor('#ec587b')
    role = ('error' if state in {CoreState.ERROR, CoreState.SECURITY_ALERT} else
        'warning' if state == CoreState.WARNING else 'success' if state == CoreState.SUCCESS else
        'accent_secondary' if state in {CoreState.UNDERSTANDING, CoreState.THINKING, CoreState.MEDIA_GENERATING, CoreState.RESEARCH_RUNNING} else 'accent_primary')
    return QColor(tokens[role])


def with_alpha(color, alpha):
    result = QColor(color); result.setAlpha(max(0, min(255, round(alpha)))); return result


@lru_cache(maxsize=64)
def _orbit_geometry(radius, orbit, deformation):
    """Cache spline geometry; native painter transforms carry smooth rotation."""
    path=QPainterPath();positions=[];tilt=.34+orbit*.59
    for i in range(101):
        a=i/100*math.tau;r=radius*(.9+.11*math.sin(a*3+orbit*.7+deformation))
        point=QPointF(r*math.cos(a),r*math.sin(a)*(.48+.12*math.sin(tilt)));positions.append(point)
        if i==0:path.moveTo(point)
        else:path.lineTo(point)
    return path,tuple(positions)


@lru_cache(maxsize=64)
def _theme_orbit_geometry(radius,orbit,paths,preset):
    path=QPainterPath();positions=[]
    for index,(x,y) in enumerate(scene_points(preset,orbit,paths,0.,100)):
        point=QPointF((x-.5)*radius*2,(y-.5)*radius*2);positions.append(point)
        if index==0:path.moveTo(point)
        else:path.lineTo(point)
    return path,tuple(positions)


def draw_core(painter, rect, snapshot, tokens, phase, complexity=3, brightness=.7, moving=True, motion_strength=1.,core_scale=1.):
    """Spline orbits with a luminous point; no face, eyes or identity mark."""
    center = rect.center(); radius = min(rect.width(), rect.height()) * .33 * max(.5,min(1.5,core_scale))
    if radius < 1: return
    color = core_color(snapshot, tokens); secondary = QColor(tokens['accent_secondary'])
    moving = moving and motion_strength > 0
    phase = loop_angle(phase) if moving else 0.
    motion_strength = max(0., min(1., motion_strength))
    active = snapshot.state not in {CoreState.IDLE, CoreState.ARMED}
    breath = 1 + (.025 * math.sin(phase)*motion_strength if moving else 0)
    if snapshot.state == CoreState.UNDERSTANDING: radius *= .86
    amplitude = snapshot.audio_level if snapshot.state in {CoreState.LISTENING, CoreState.SPEAKING} else 0
    halo = QRadialGradient(center, radius * 1.5)
    halo.setColorAt(0, with_alpha(color, 34 * brightness)); halo.setColorAt(.5, with_alpha(color, 10 * brightness)); halo.setColorAt(1, with_alpha(color, 0))
    painter.setPen(Qt.NoPen); painter.setBrush(QBrush(halo)); painter.drawEllipse(center, radius*1.5, radius*1.5)
    paths = min(6, max(1, complexity)); samples = 100
    for orbit in range(paths):
        # Independent orbital planes rise, fall and precess around a stable
        # centre. These decorative cycles never encode elapsed task progress.
        direction = -1 if orbit % 3 == 1 else 1
        rotation = phase*direction + orbit*1.17
        lift = radius*.11*math.sin(phase*2 + orbit*1.6)*motion_strength if moving else 0.
        tilt = 1. + .18*math.sin(phase + orbit*1.2)*motion_strength if moving else 1.
        preset=getattr(tokens,'scene','MORICE')
        if preset in {'MORICE','ARCTIC'}:
            path,positions=_orbit_geometry(round(radius,2),orbit,0.)
        else:
            path,positions=_theme_orbit_geometry(round(radius,2),orbit,paths,preset)
        painter.save();painter.translate(center + QPointF(0, lift));painter.rotate(math.degrees(rotation));painter.scale(breath,breath*tilt)
        line = color if orbit%2 == 0 else secondary
        if snapshot.state == CoreState.SECURITY_ALERT: line = color
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(with_alpha(line, 16*brightness), 7 if radius > 50 else 3)); painter.drawPath(path)
        painter.setPen(QPen(with_alpha(line, (126 if active else 84)*brightness), 1.2)); painter.drawPath(path)
        # A travelling light is decorative motion, never task progress.
        position=(phase/math.tau+orbit/paths)%1*samples;index=int(position);fraction=position-index
        point=positions[index]*(1-fraction)+positions[index+1]*fraction
        painter.setPen(Qt.NoPen); painter.setBrush(with_alpha(line, 220*brightness)); painter.drawEllipse(point, 2.2, 2.2)
        painter.restore()
    if amplitude and moving:
        painter.setPen(QPen(with_alpha(color, 160*brightness), 1.4))
        for i in range(40):
            a = i/40*math.tau; start = radius*1.12
            length = amplitude*radius*.16*(.65+.35*math.sin(i*1.7))
            painter.drawLine(center+QPointF(math.cos(a)*start,math.sin(a)*start), center+QPointF(math.cos(a)*(start+length),math.sin(a)*(start+length)))
    if snapshot.state == CoreState.SECURITY_ALERT:
        painter.setBrush(Qt.NoBrush); painter.setPen(QPen(with_alpha(color, 145*brightness), 1.8))
        ring = QRectF(center.x()-radius*1.22,center.y()-radius*1.22,radius*2.44,radius*2.44)
        for index in range(8): painter.drawArc(ring, index*45*16, 28*16)
    # Only actual active public roles/capabilities become satellite points.
    for i, node in enumerate(snapshot.nodes[:8]):
        a = i/max(1,len(snapshot.nodes))*math.tau+phase
        point = center+QPointF(math.cos(a)*radius*1.18, math.sin(a)*radius*1.18)
        painter.setPen(QPen(with_alpha(color, 34), 1)); painter.drawLine(center,point)
        painter.setPen(Qt.NoPen); painter.setBrush(with_alpha(color, 180)); painter.drawEllipse(point,3,3)
    glow = QRadialGradient(center, max(8.,radius*.17))
    glow.setColorAt(0,with_alpha(QColor('#e6fcff'),240*brightness));glow.setColorAt(.16,with_alpha(color,200*brightness));glow.setColorAt(1,with_alpha(color,0))
    painter.setPen(Qt.NoPen);painter.setBrush(QBrush(glow));painter.drawEllipse(center,radius*.17,radius*.17)


class CoreCanvas(QWidget):
    def __init__(self, model, theme, policy, clock, parent=None):
        super().__init__(parent)
        self.model=model;self.theme=theme;self.policy=policy;self.clock=clock;self._phase=0.;self.paint_samples=deque(maxlen=600);self.paint_count=0
        self.setMinimumSize(120,120);self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.setAccessibleName('MORICE Core'); self.setAttribute(Qt.WA_TransparentForMouseEvents)
        model.changed.connect(self.refresh);theme.changed.connect(self.refresh);policy.changed.connect(self.refresh);clock.subscribe(self,self.tick)

    def sizeHint(self):return QSize(460,380)

    def refresh(self,*_):
        self.setAccessibleDescription(self.model.snapshot.title+'. '+self.model.snapshot.detail);self.update();self.clock.request()

    def tick(self,delta):
        self.model.sample()
        moving=self.policy.budget.decorative_motion and self.window().isActiveWindow()
        if moving:self._phase=(self._phase+delta*self.theme.profile.motion_speed)%LOOP_SECONDS;self.update()
        return moving or self.model.snapshot.state in {CoreState.ARMED,CoreState.LISTENING,CoreState.SPEAKING}

    def paintEvent(self,event):
        started=time.perf_counter();p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        profile=self.theme.profile
        draw_core(p,QRectF(self.rect()),self.model.snapshot,self.theme.tokens,self._phase,profile.orbital_complexity,profile.core_brightness, self.policy.budget.decorative_motion, profile.motion_strength,profile.core_scale)
        p.end();self.paint_count+=1;self.paint_samples.append((time.perf_counter()-started)*1000)

    def showEvent(self,event):self.clock.request();super().showEvent(event)

    def dispose(self):self.clock.unsubscribe_id(id(self))


class CoreView(QWidget):
    def __init__(self, model, theme, policy, clock, parent=None):
        super().__init__(parent);self.model=model
        self.setObjectName('CoreView');layout=QVBoxLayout(self);layout.setContentsMargins(12,12,12,12);layout.setSpacing(8)
        self.eyebrow=QLabel('M O R I C E   /   P R I V A T E   I N T E L L I G E N C E');self.eyebrow.setProperty('role','secondary');self.eyebrow.setAlignment(Qt.AlignCenter);self.eyebrow.setWordWrap(True)
        layout.addWidget(self.eyebrow);self.canvas=CoreCanvas(model,theme,policy,clock);layout.addWidget(self.canvas,1)
        self.title=QLabel();self.title.setProperty('role','title');self.title.setWordWrap(True);self.title.setAlignment(Qt.AlignCenter);layout.addWidget(self.title)
        from .effects import AuthoredMark
        self.state_mark=AuthoredMark('core',theme);layout.addWidget(self.state_mark,0,Qt.AlignHCenter)
        self.detail=QLabel();self.detail.setProperty('role','secondary');self.detail.setWordWrap(True);self.detail.setAlignment(Qt.AlignCenter);layout.addWidget(self.detail)
        self.nodes=QLabel();self.nodes.setProperty('role','secondary');self.nodes.setWordWrap(True);self.nodes.setAlignment(Qt.AlignCenter);layout.addWidget(self.nodes)
        model.changed.connect(self.refresh);self.refresh(model.snapshot)

    def refresh(self,snapshot):
        self.title.setText(snapshot.title);self.detail.setText(snapshot.detail)
        self.state_mark.name={CoreState.ARMED:'voice',CoreState.LISTENING:'voice',CoreState.SPEAKING:'voice',CoreState.SECURITY_ALERT:'security',CoreState.MEDIA_GENERATING:'media',CoreState.RESEARCH_RUNNING:'research',CoreState.ERROR:'warning',CoreState.WARNING:'warning',CoreState.SUCCESS:'check',CoreState.WAITING_FOR_USER:'activity'}.get(snapshot.state,'core');self.state_mark.update()
        names=[]
        for node in snapshot.nodes:
            coordinator=getattr(self.model.runtime,'agents',None)
            try:name=coordinator.roles.resolve(node).display_name if coordinator else None
            except ValueError:name=None
            if not name:
                name={'research':'Research','browser':'Browser','web':'Browser','file':'Files','filesystem':'Files','terminal':'Terminal','project':'Build','build':'Build','spatial':'Spatial','media':'Media','device':'Devices','mesh':'Devices','simulation':'Simulation'}.get(node.split('.')[0],'Task')
            names.append(name)
        self.nodes.setText(' · '.join(dict.fromkeys(names)));self.nodes.setVisible(bool(snapshot.nodes))

    def dispose(self):self.canvas.dispose()

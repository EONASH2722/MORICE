"""Original software-painted orbital presence, separate from MORICE's logo."""
from __future__ import annotations

from collections import deque
from functools import lru_cache
import math
import time

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient, QBrush, QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QApplication, QPushButton

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


def draw_core(painter, rect, snapshot, tokens, phase, complexity=3, brightness=.7, moving=True, motion_strength=1.,core_scale=1.,*,preserve_pose=False):
    """Spline orbits with a luminous point; no face, eyes or identity mark."""
    center = rect.center(); radius = min(rect.width(), rect.height()) * .33 * max(.5,min(1.5,core_scale))
    if radius < 1: return
    color = core_color(snapshot, tokens); secondary = QColor(tokens['accent_secondary'])
    moving = moving and motion_strength > 0
    pose=moving or preserve_pose and motion_strength>0
    phase = loop_angle(phase) if pose else 0.
    motion_strength = max(0., min(1., motion_strength))
    active = snapshot.state not in {CoreState.IDLE, CoreState.ARMED}
    breath = 1 + (.025 * math.sin(phase)*motion_strength if pose else 0)
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
        lift = radius*.11*math.sin(phase*2 + orbit*1.6)*motion_strength if pose else 0.
        tilt = 1. + .18*math.sin(phase + orbit*1.2)*motion_strength if pose else 1.
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
    if amplitude and pose:
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
        draw_core(p,QRectF(self.rect()),self.model.snapshot,self.theme.tokens,self._phase,profile.orbital_complexity,profile.core_brightness, self.policy.budget.decorative_motion, profile.motion_strength,profile.core_scale,preserve_pose=self.policy.load_state=='UNFOCUSED' and not profile.reduced_motion)
        p.end();self.paint_count+=1;self.paint_samples.append((time.perf_counter()-started)*1000)

    def showEvent(self,event):self.clock.request();super().showEvent(event)

    def dispose(self):self.clock.unsubscribe_id(id(self))


class CoreView(QWidget):
    def __init__(self, model, theme, policy, clock, parent=None, *, immersive=False):
        super().__init__(parent);self.model=model;self._immersive=immersive
        self.setObjectName('CoreView');layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(4)
        self.eyebrow=QLabel('M O R I C E   /   P R I V A T E   I N T E L L I G E N C E');self.eyebrow.setProperty('role','secondary');self.eyebrow.setAlignment(Qt.AlignCenter);self.eyebrow.setWordWrap(True)
        self.eyebrow.hide()
        from .globe_state import GlobeBoot
        self.boot=GlobeBoot();self.fallback_reason='';self._theme=theme;self._policy=policy;self._clock=clock
        if QApplication.platformName() in {'offscreen','minimal'}:
            self.canvas=CoreCanvas(model,theme,policy,clock)
            self.fallback_reason='GPU globe unavailable on the '+QApplication.platformName()+' platform; reduced-quality preview.'
        else:
            from .globe_renderer import HolographicGlobe
            self.canvas=HolographicGlobe(model,theme,policy,clock,boot=self.boot)
            self.canvas.rendering_failed.connect(self._render_failed)
            self.canvas.boot_changed.connect(lambda *_:self.refresh(model.snapshot))
        layout.addWidget(self.canvas,1)
        self.title=QLabel();self.title.setProperty('role','title');self.title.setWordWrap(True);self.title.setAlignment(Qt.AlignCenter);layout.addWidget(self.title)
        self.state_mark=QLabel();self.state_mark.hide()  # Retained presentation binding, not another identity mark.
        self.detail=QLabel();self.detail.setProperty('role','secondary');self.detail.setWordWrap(True);self.detail.setAlignment(Qt.AlignCenter);layout.addWidget(self.detail)
        self.nodes=QLabel();self.nodes.setProperty('role','secondary');self.nodes.setWordWrap(True);self.nodes.setAlignment(Qt.AlignCenter);layout.addWidget(self.nodes)
        self.skip_button=QPushButton('Skip introduction');self.skip_button.clicked.connect(self.skip_intro)
        self.skip_button.setParent(self)
        self.skip_shortcut=QShortcut(QKeySequence('Escape'),self);self.skip_shortcut.setContext(Qt.WindowShortcut);self.skip_shortcut.activated.connect(self.skip_intro)
        if theme.profile.reduced_motion:self.boot.skip()
        model.changed.connect(self.refresh);self.refresh(model.snapshot)
        if immersive:
            for widget in (self.canvas,self.eyebrow,self.title,self.detail,self.nodes):
                layout.removeWidget(widget);widget.setParent(self)
            self.title.setProperty('role','secondary');self._position_immersive()

    def _position_immersive(self):
        if not self._immersive:return
        self.canvas.setGeometry(self.rect());self.canvas.lower()
        chat=getattr(self,'present_route','home')=='chats'
        width=min(360 if chat else 650,max(200,self.width()-80));left=round(self.width()*(.81 if chat and self.width()>1000 else .5)-width/2)
        top=round(self.height()*.66) if chat and self.width()>1000 else 64
        self.title.setGeometry(left,top,width,28);self.detail.setGeometry(left,top+28,width,30)
        self.nodes.setGeometry(left,120,width,24)
        self.title.raise_();self.detail.raise_();self.nodes.raise_()

    def skip_intro(self):
        self.boot.skip();self.canvas.update();self._clock.request();self.refresh(self.model.snapshot)

    def services_ready(self, error=''):
        if error:self.boot.fail(error)
        else:self.boot.ready=True
        self.refresh(self.model.snapshot)

    def _render_failed(self,reason):
        self.fallback_reason=reason
        QTimer.singleShot(0,self._install_fallback)

    def _install_fallback(self):
        old=self.canvas;old.dispose()
        self.canvas=CoreCanvas(self.model,self._theme,self._policy,self._clock)
        if self._immersive:self.canvas.setParent(self);self._position_immersive();self.canvas.show()
        else:self.layout().replaceWidget(old,self.canvas)
        old.hide();old.deleteLater()
        self.refresh(self.model.snapshot)

    def refresh(self,snapshot):
        self.title.setText(snapshot.title);self.detail.setText(snapshot.detail)
        from .globe_state import BootStage
        stage=self.boot.stage
        if self.fallback_reason:self.detail.setText(self.fallback_reason)
        if stage==BootStage.FAILED:self.title.setText('Startup needs attention');self.detail.setText(self.boot.error)
        elif stage!=BootStage.READY_IDLE and not self.fallback_reason:
            self.title.setText({'DORMANT':'MORICE is starting','IGNITING':'Core ignition',
                'PARTICLES_FORMING':'Assembling light','WIREFRAME_FORMING':'Forming the globe',
                'ORBITS_SYNCHRONIZING':'Synchronizing orbits','GLOW_ACTIVATING':'Coming online',
                'WAITING_FOR_SERVICES':'Waiting for application services'}.get(stage.value,'Starting'))
            self.detail.setText('Preparing your private workspace.')
        self.skip_button.setVisible(self.boot.progress<1 and not self.fallback_reason)
        if self._immersive:
            route=getattr(self,'present_route','home')
            busy=snapshot.state in {CoreState.THINKING,CoreState.UNDERSTANDING,CoreState.WORKING,CoreState.RESEARCH_RUNNING,CoreState.MEDIA_GENERATING,CoreState.SPEAKING,CoreState.LISTENING,CoreState.ERROR}
            visible=route in {'home','chats'} and (busy or stage!=BootStage.READY_IDLE or bool(self.fallback_reason))
            self.title.setVisible(visible);self.detail.setVisible(visible and (stage!=BootStage.READY_IDLE or bool(self.fallback_reason)))
            self._position_immersive()
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

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._position_immersive()
        self.skip_button.adjustSize();self.skip_button.move(max(4,self.width()-self.skip_button.width()-12),12);self.skip_button.raise_()

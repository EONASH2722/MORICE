"""Native GPU holographic globe: bounded line/point buffers and analytic emission.

No textures, model allocations, frame-by-frame geometry uploads or pixel loops.
The widget consumes the existing CorePresentation and visible-only effect clock.
"""
from __future__ import annotations

from collections import deque
import math
import time

from PySide6.QtCore import Qt, QSize, Signal, QPointF, QTimer
from PySide6.QtGui import QColor, QMatrix4x4, QVector2D, QVector3D, QSurfaceFormat
from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram, QOpenGLVertexArrayObject
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QMenu, QColorDialog, QSizePolicy

from .core_state import CoreState
from .globe_state import GlobeBoot, GlobeDynamics, BootStage, OrbRotation
from .globe_geometry import build_globe_geometry


VERTEX = '''
#version 120
attribute vec3 position;
attribute float seed;
attribute float pathPosition;
uniform mat4 projection;
uniform mat4 transform;
uniform float time;
uniform float points;
uniform float reveal;
uniform float pixelRatio;
uniform float audio;
uniform vec2 pointer;
uniform float hover;
uniform float velocity;
uniform vec3 rippleOrigin;
uniform float rippleAge;
uniform vec2 viewOffset;
uniform float sceneScale;
varying float light;
varying float visible;
void main() {
    vec3 p = position;
    if (points > .5) {
        p += .008 * vec3(sin(time*.8+seed), cos(time*.67+seed*1.8), sin(time*.5+seed*.6));
        p *= mix(.12, 1., reveal);
    }
    vec4 world = transform * vec4(p, 1.);
    vec2 field = world.xy / max(.1,sceneScale);
    float nearPointer = exp(-dot(field-pointer, field-pointer)*14.) * hover;
    world.xy += (field-pointer) * nearPointer * .025 * sceneScale * (1.+velocity*.2);
    float rippleDistance = distance(normalize(world.xyz), rippleOrigin);
    float ripple = exp(-pow((rippleDistance-rippleAge*1.25)*12.,2.)) * max(0.,1.-rippleAge/1.8);
    world.xyz *= 1. + ripple*.022 + audio*.025*sin(seed+time*5.);
    gl_Position = projection * world;
    gl_Position.xy += viewOffset * gl_Position.w;
    float front = .45 + .55 * smoothstep(-1., 1., world.z);
    light = front * (1.+nearPointer*(1.4+velocity*.15)+ripple*3.+audio*.6);
    visible = smoothstep(pathPosition-.04,pathPosition+.04,reveal);
    gl_PointSize = (1.4 + 1.8*pow(.5+.5*sin(seed*3.1),8.) + nearPointer*1.2) * pixelRatio;
}
'''

FRAGMENT = '''
#version 120
uniform vec3 color;
uniform float brightness;
uniform float points;
varying float light;
varying float visible;
void main() {
    float shape=1.;
    if (points > .5) {
        float r=length(gl_PointCoord-vec2(.5))*2.;
        shape=exp(-r*r*3.)*(1.-smoothstep(.65,1.,r));
    }
    gl_FragColor=vec4(color, clamp(brightness*light*shape*visible,0.,1.));
}
'''

HALO_VERTEX = '''
#version 120
attribute vec3 position;
varying vec2 uv;
void main() {uv=position.xy;gl_Position=vec4(position.xy,0.,1.);}
'''

HALO_FRAGMENT = '''
#version 120
varying vec2 uv;
uniform vec2 aspect;
uniform float radius;
uniform vec3 globeColor;
uniform vec3 glowColor;
uniform float halo;
uniform float core;
uniform float pulse;
uniform vec2 viewOffset;
uniform vec3 background;
uniform float lightTheme;
uniform float transparentPet;
void main() {
    float r=length((uv-viewOffset)*aspect)/max(.01,radius);
    float haze=exp(-r*r*1.18)*.46*halo;
    float rim=exp(-pow((r-1.)*22.,2.))*.028*halo;
    float nucleus=exp(-r*r*95.)*.32*core;
    float point=exp(-r*r*4800.)*.7*core;
    vec3 c=glowColor*(haze+rim)+globeColor*(nucleus+point)*(1.+pulse*.22);
    if (transparentPet>.5) {
        float a=clamp(rim*.9+nucleus*.35+point*.5,0.,.38);
        gl_FragColor=vec4(glowColor,a);
    } else gl_FragColor=vec4(mix(background+c,mix(background,glowColor,min(.15,haze*.5+nucleus*.15)),lightTheme),1.);
}
'''


class GlobeProgram(QOpenGLShaderProgram):
    """Use cached integer locations, including PySide's scalar-float overload."""
    def __init__(self,parent):
        super().__init__(parent);self.locations={}

    def setUniformValue(self,name,*values):
        if name not in self.locations:self.locations[name]=self.uniformLocation(name)
        if len(values)==1 and isinstance(values[0],float):
            # Qt's Python overload resolver can pick the integer uniform
            # overload for a scalar. The typed GL entry point is unambiguous.
            from PySide6.QtGui import QOpenGLContext
            QOpenGLContext.currentContext().functions().glUniform1f(self.locations[name],values[0])
        elif len(values)==1 and isinstance(values[0],QVector3D):
            from PySide6.QtGui import QOpenGLContext
            value=values[0];QOpenGLContext.currentContext().functions().glUniform3f(self.locations[name],value.x(),value.y(),value.z())
        elif len(values)==1 and isinstance(values[0],QVector2D):
            from PySide6.QtGui import QOpenGLContext
            value=values[0];QOpenGLContext.currentContext().functions().glUniform2f(self.locations[name],value.x(),value.y())
        else:super().setUniformValue(self.locations[name],*values)


class HolographicGlobe(QOpenGLWidget):
    boot_changed = Signal(str)
    rendering_failed = Signal(str)

    def __init__(self, model, theme, policy, clock, parent=None, *, boot=None, transparent_pet=False):
        super().__init__(parent)
        fmt=QSurfaceFormat();fmt.setVersion(2,1);fmt.setProfile(QSurfaceFormat.NoProfile)
        fmt.setDepthBufferSize(0);fmt.setStencilBufferSize(0);fmt.setSamples(2);fmt.setSwapInterval(1)
        self.transparent_pet=bool(transparent_pet);self.orb_rotation=OrbRotation() if self.transparent_pet else None
        if self.transparent_pet:
            fmt.setAlphaBufferSize(8);self.setAttribute(Qt.WA_TranslucentBackground);self.setAutoFillBackground(False)
        self.setFormat(fmt);self.setUpdateBehavior(QOpenGLWidget.NoPartialUpdate)
        self.model=model;self.theme=theme;self.policy=policy;self.clock=clock
        self.boot=boot or GlobeBoot();self.dynamics=GlobeDynamics()
        self.layers=build_globe_geometry(compact=self.transparent_pet);self._buffers=[];self._program=None;self._halo=None
        self._quad=None;self._vao=None;self._failed='';self._closed=False;self._last_stage=None
        self._last_input=time.perf_counter();self._press=None;self._last_pos=None;self._drag_distance=0.
        self.paint_samples=deque(maxlen=600);self.frame_intervals=deque(maxlen=600);self.paint_count=0
        self._last_paint=0.;self._tick_accumulator=0.;self.gl_info={};self._boot_started=None
        self._center=(.5,.42);self._center_target=self._center;self._display_scale=1.;self._scale_target=1.;self.presentation='home'
        self._orbit_phases=[0. for _ in self.layers];self._activity_mix=0.;self._idle_mix=1.;self.animation_mode='idle'
        self._presence_opacity=1.;self._presence_target=1.
        self._audio_envelope=0.
        self.setMinimumSize(100,100);self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)
        self.setMouseTracking(True);self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName('MORICE holographic globe')
        self.setAccessibleDescription('Drag to rotate, scroll to zoom, double-click to reset. Escape skips the visual introduction.')
        self.setToolTip('Drag to rotate · Scroll to zoom · Double-click to reset · Right-click for colors')
        model.changed.connect(self.refresh);theme.changed.connect(self.refresh);policy.changed.connect(self.refresh)
        theme.globe_changed.connect(self.refresh)
        self._context_check=QTimer(self);self._context_check.setSingleShot(True);self._context_check.setInterval(500)
        self._context_check.timeout.connect(self._validate_context)
        clock.subscribe(self,self.tick)

    def _validate_context(self):
        if not self._closed and self.isVisible() and not self.isValid() and not self._failed:
            self._failed='GPU globe unavailable: Windows did not create a valid OpenGL context.'
            self.rendering_failed.emit(self._failed)

    def sizeHint(self): return QSize(720,520)

    @staticmethod
    def _color(value):
        color=QColor(value);return QVector3D(color.redF(),color.greenF(),color.blueF())

    def _shader(self,vertex,fragment):
        program=GlobeProgram(self)
        if not program.addShaderFromSourceCode(QOpenGLShader.Vertex,vertex):raise RuntimeError(program.log())
        if not program.addShaderFromSourceCode(QOpenGLShader.Fragment,fragment):raise RuntimeError(program.log())
        program.bindAttributeLocation('position',0);program.bindAttributeLocation('seed',1);program.bindAttributeLocation('pathPosition',2)
        if not program.link():raise RuntimeError(program.log())
        return program

    def initializeGL(self):
        try:
            self.gl=self.context().functions();self.gl.initializeOpenGLFunctions()
            self.gl_info={'version':self.context().format().majorVersion(),
                'minor':self.context().format().minorVersion(),'opengl_es':self.context().isOpenGLES(),
                'samples':self.context().format().samples(),'buffer_bytes':sum(x.vertices.nbytes for x in self.layers)}
            self._program=self._shader(VERTEX,FRAGMENT);self._halo=self._shader(HALO_VERTEX,HALO_FRAGMENT)
            self._vao=QOpenGLVertexArrayObject(self);self._vao.create();self._vao.bind()
            for layer in self.layers:
                buffer=QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
                if not buffer.create():raise RuntimeError('Could not allocate globe vertex buffer.')
                buffer.bind();raw=layer.vertices.tobytes();buffer.allocate(raw,len(raw));buffer.release();self._buffers.append(buffer)
            import struct
            self._quad=QOpenGLBuffer(QOpenGLBuffer.VertexBuffer);self._quad.create();self._quad.bind()
            data=struct.pack('12f',-1,-1,0,1,-1,0,-1,1,0,1,1,0);self._quad.allocate(data,len(data));self._quad.release()
            self.context().aboutToBeDestroyed.connect(self.cleanup)
        except Exception as exc:
            self._failed='GPU globe unavailable: '+str(exc)[:500];self.rendering_failed.emit(self._failed)

    def _sphere_radius(self):
        return min(self.width(),self.height())*.337*self.dynamics.zoom*self._display_scale

    def _coords(self,position):
        radius=max(1,self._sphere_radius())
        return ((position.x()-self.width()*self._center[0])/radius,(self.height()*self._center[1]-position.y())/radius)

    def set_presentation(self,route,*,compact=False):
        self.presentation=route
        self._center_target=(.5,.40) if route=='home' else (.5,.54) if route=='voice' else (.55,.20) if compact and route=='chats' else (.81,.43)
        self._scale_target=1. if route=='home' else .9 if route=='voice' else .34 if compact and route=='chats' else .59 if route=='chats' else .45
        self._presence_target=1. if route in {'home','chats','voice'} else .12
        if self.theme.profile.reduced_motion:self._center=self._center_target;self._display_scale=self._scale_target
        self.clock.request();self.update()

    def refresh(self,*_):
        self.setAccessibleDescription(self.model.snapshot.title+'. Drag to rotate; scroll to zoom.')
        state=self.model.snapshot.state
        previous=getattr(self,'_state',CoreState.IDLE)
        if state!=previous and state in {CoreState.LISTENING,CoreState.UNDERSTANDING,CoreState.SUCCESS}:
            self.dynamics.wake_age=0.
            if state==CoreState.SUCCESS:self.dynamics.click(0,0)
        self._state=state
        if self.theme.profile.reduced_motion:self.boot.skip()
        self.update();self.clock.request()

    def tick(self,delta):
        if self._closed or self._failed:return False
        if hasattr(self.model,'sample'):self.model.sample()
        level=self.model.snapshot.audio_level if self.model.snapshot.state in {CoreState.SPEAKING,CoreState.LISTENING} else 0.
        rate=40 if level>self._audio_envelope else 11
        self._audio_envelope+=(level-self._audio_envelope)*(1-math.exp(-rate*delta))
        if self._boot_started is not None:
            self.boot.advance(max(0.,time.perf_counter()-self._boot_started-self.boot.elapsed))
        stage=self.boot.stage
        if stage!=self._last_stage:self._last_stage=stage;self.boot_changed.emit(stage.value)
        reduced=self.theme.profile.reduced_motion or self.theme.profile.motion_strength==0
        active=self.model.snapshot.state in {CoreState.THINKING,CoreState.UNDERSTANDING,CoreState.WORKING,
            CoreState.MULTI_AGENT,CoreState.RESEARCH_RUNNING,CoreState.MEDIA_GENERATING}
        blend_activity=1-math.exp(-7*delta)
        self._activity_mix+=(float(active)-self._activity_mix)*blend_activity
        cursor=self.dynamics.hover>.15 or self.dynamics.dragging
        self._idle_mix+=((.12 if cursor else 1.)-self._idle_mix)*blend_activity
        self.animation_mode=('thinking + cursor' if cursor else 'thinking') if active else 'cursor' if cursor else 'idle'
        if not reduced:
            for i,layer in enumerate(self.layers):
                energy=self._idle_mix+self._activity_mix*(2.1 if 'core' in layer.name else 1.2)
                self._orbit_phases[i]+=min(.1,delta)*layer.speed*energy*self.theme.profile.motion_speed
        focused=self.transparent_pet or self.window().isActiveWindow()
        if self.orb_rotation:self.orb_rotation.advance(delta*self.theme.profile.motion_speed,interactive=cursor,reduced=reduced)
        interaction=self.dynamics.dragging or self.dynamics.pointer_speed>.15 and cursor or self.dynamics.ripple_age<2 or self.dynamics.wake_age<1.2 or abs(self.dynamics.zoom-self.dynamics.zoom_target)>.001 or abs(self.dynamics.yaw_velocity)+abs(self.dynamics.pitch_velocity)>.005
        changing=math.dist(self._center,self._center_target)>.001 or abs(self._display_scale-self._scale_target)>.001
        interaction=interaction or changing
        blend=1. if reduced else 1-math.exp(-10*delta)
        self._center=tuple(a+(b-a)*blend for a,b in zip(self._center,self._center_target))
        self._display_scale+=(self._scale_target-self._display_scale)*blend
        self._presence_opacity+=(self._presence_target-self._presence_opacity)*blend
        booting=self.boot.progress<1
        animated=(focused and not reduced) or interaction or booting
        self.dynamics.advance(delta,reduced=reduced or (not focused and not interaction),speed=self.theme.profile.motion_speed)
        fps=60 if interaction or booting else min(30,self.policy.budget.fps)
        if self.presentation not in {'home','chats','voice'} and not interaction:fps=min(fps,15)
        if self.policy.load_state in {'VRAM_PRESSURE','POWER_SAVING','MEDIA_GENERATING','GPU_BUSY'}:fps=min(fps,24)
        self.clock.set_rate_hint(self,fps if animated else 0)
        self._tick_accumulator+=delta
        if animated and self._tick_accumulator>=1/fps-.0005:
            self._tick_accumulator=max(0.,self._tick_accumulator-1/fps);self.update()
        return animated

    def paintGL(self):
        started=time.perf_counter()
        if self._closed:return
        gl=self.context().functions()
        background=QColor(self.theme.tokens['background'])
        gl.glClearColor(0.,0.,0.,0.) if self.transparent_pet else gl.glClearColor(background.redF(),background.greenF(),background.blueF(),1.)
        gl.glClear(0x00004000)
        if self._failed or self._program is None:return
        ratio=self.devicePixelRatioF();gl.glViewport(0,0,round(self.width()*ratio),round(self.height()*ratio))
        self._vao.bind()
        gl.glDisable(0x0B71);gl.glDisable(0x0BE2)
        gl.glDisable(0x0C11);gl.glDisable(0x0B90);gl.glBlendEquation(0x8006)
        if self.transparent_pet:gl.glEnable(0x0BE2);gl.glBlendFuncSeparate(0x0302,0x0303,1,0x0303)
        gl.glEnable(0x8642)  # GL_PROGRAM_POINT_SIZE
        gl.glEnable(0x8861)  # Compatibility-context point sprites / gl_PointCoord.
        d=self.dynamics;profile=self.theme.profile;state=self.model.snapshot.state
        audio=self._audio_envelope if not profile.reduced_motion else 0.
        active=state in {CoreState.THINKING,CoreState.UNDERSTANDING,CoreState.WORKING,CoreState.MULTI_AGENT,CoreState.RESEARCH_RUNNING,CoreState.MEDIA_GENERATING}
        pulse=math.exp(-d.wake_age*3.) + self._audio_envelope*1.5
        projection=QMatrix4x4();projection.perspective(40.,max(.01,self.width()/max(1,self.height())),.1,20.)
        projection.translate(0,0,-4.1)
        scale=min(1.,self.width()/max(1,self.height()))*d.zoom*self._display_scale
        offset=QVector2D(self._center[0]*2-1,1-self._center[1]*2)
        from .themes import luminance
        light_theme=not self.transparent_pet and luminance(self.theme.tokens['background'])>.45
        globe_color=self._color(profile.globe_color);glow_color=self._color(profile.globe_glow_color)
        halo=self._halo;halo.bind();self._quad.bind();halo.enableAttributeArray(0);halo.setAttributeBuffer(0,0x1406,0,3,12)
        halo.setUniformValue('aspect',QVector2D(self.width()/max(1,min(self.width(),self.height())),self.height()/max(1,min(self.width(),self.height()))))
        halo.setUniformValue('radius',float(.674*d.zoom*self._display_scale));halo.setUniformValue('globeColor',globe_color);halo.setUniformValue('glowColor',glow_color)
        halo.setUniformValue('viewOffset',offset);halo.setUniformValue('background',self._color(self.theme.tokens['background']))
        halo.setUniformValue('lightTheme',1. if light_theme else 0.)
        halo.setUniformValue('transparentPet',1. if self.transparent_pet else 0.)
        halo.setUniformValue('halo',float(self.boot.layer(.72,1.) * (.5+profile.core_brightness*.65)*self._presence_opacity))
        halo.setUniformValue('core',float(self.boot.layer(.03,.24)*self._presence_opacity));halo.setUniformValue('pulse',float(pulse))
        gl.glDrawArrays(0x0005,0,4);halo.disableAttributeArray(0);self._quad.release();halo.release()
        # The backing FBO is already opaque. Preserve its alpha while blending
        # emission; reducing alpha here corrupts Qt's premultiplied composition
        # over White and can invert fine lines into green/yellow artifacts.
        gl.glEnable(0x0BE2)
        if self.transparent_pet:gl.glBlendFuncSeparate(0x0302,0x0303,1,0x0303)
        else:gl.glBlendFuncSeparate(0x0302,0x0303 if light_theme else 1,0,1)
        program=self._program;program.bind();program.setUniformValue('projection',projection)
        program.setUniformValue('viewOffset',offset);program.setUniformValue('sceneScale',float(scale))
        program.setUniformValue('time',float(d.time));program.setUniformValue('pixelRatio',float(ratio))
        program.setUniformValue('pointer',QVector2D(*d.pointer));program.setUniformValue('hover',float(d.hover))
        program.setUniformValue('velocity',float(d.pointer_speed));program.setUniformValue('audio',float(audio))
        program.setUniformValue('rippleOrigin',QVector3D(*d.ripple_origin));program.setUniformValue('rippleAge',float(d.ripple_age))
        program.setUniformValue('color',globe_color*.52 if light_theme else globe_color)
        for index,(layer,buffer) in enumerate(zip(self.layers,self._buffers)):
            if layer.points and profile.reduced_motion:continue
            reveal=self.boot.layer(*layer.reveal)
            if reveal<=0:continue
            matrix=QMatrix4x4();matrix.scale(scale);matrix.rotate(math.degrees(d.pitch),1,0,0);matrix.rotate(math.degrees(d.yaw),0,1,0)
            if self.orb_rotation:
                matrix.rotate(math.degrees(self.orb_rotation.pitch),1,0,0);matrix.rotate(math.degrees(self.orb_rotation.yaw),0,1,0)
            matrix.rotate(math.degrees(self._orbit_phases[index]),*layer.axis)
            brightness=layer.brightness*(.55+profile.core_brightness*.7)*(1.+pulse*.3)*self._presence_opacity
            if state in {CoreState.ERROR,CoreState.SECURITY_ALERT}:brightness*=.8+.18*math.sin(d.time*3.)
            program.setUniformValue('transform',matrix);program.setUniformValue('reveal',float(reveal))
            program.setUniformValue('brightness',float(brightness));program.setUniformValue('points',1. if layer.points else 0.)
            buffer.bind()
            for attr,size,offset in ((0,3,0),(1,1,12),(2,1,16)):
                program.enableAttributeArray(attr);program.setAttributeBuffer(attr,0x1406,offset,size,20)
            if not layer.points and self.policy.budget.effective!='LOW':
                gl.glLineWidth(3.);program.setUniformValue('brightness',float(brightness*.12))
                gl.glDrawArrays(0x0001,0,len(layer.vertices));gl.glLineWidth(1.)
                program.setUniformValue('brightness',float(brightness))
            gl.glDrawArrays(0x0000 if layer.points else 0x0001,0,len(layer.vertices))
            for attr in (0,1,2):program.disableAttributeArray(attr)
            buffer.release()
        program.release();self._vao.release();gl.glDisable(0x0BE2)
        self.gl_info['last_gl_error']=gl.glGetError()
        self.paint_count+=1
        ended=time.perf_counter();self.paint_samples.append((ended-started)*1000)
        if self._last_paint:self.frame_intervals.append((ended-self._last_paint)*1000)
        self._last_paint=ended

    def mouseMoveEvent(self,event):
        now=time.perf_counter();dt=now-self._last_input;self._last_input=now
        pos=event.position();x,y=self._coords(pos);self.dynamics.move(x,y,dt)
        if self._press is not None and self._last_pos is not None:
            delta=pos-self._last_pos;self._drag_distance+=abs(delta.x())+abs(delta.y())
            self.dynamics.dragging=self._drag_distance>4
            if self.dynamics.dragging:self.dynamics.drag(delta.x()/max(100,self.height()),delta.y()/max(100,self.height()),dt)
        self._last_pos=QPointF(pos);self.update();self.clock.request();event.accept()

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason);self._press=QPointF(event.position());self._last_pos=self._press;self._drag_distance=0.
            self.dynamics.yaw_velocity=self.dynamics.pitch_velocity=0.;event.accept()
        else:super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton:
            if self._press is not None and self._drag_distance<=4:self.dynamics.click(*self._coords(event.position()))
            self._press=None;self.dynamics.dragging=False;self.clock.request();self.update();event.accept()
        else:super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:self.dynamics.reset();self._press=None;self.dynamics.dragging=False;self.clock.request();self.update();event.accept()
        else:super().mouseDoubleClickEvent(event)

    def leaveEvent(self,event):
        self.dynamics.pointer=(4.,4.);self.clock.request();super().leaveEvent(event)

    def wheelEvent(self,event):
        pixels=event.pixelDelta().y()
        self.dynamics.wheel(pixels/100. if pixels else event.angleDelta().y()/120.)
        self.clock.request();self.update();event.accept()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key_Escape and self.boot.progress<1:
            self.boot.skip();self.boot_changed.emit(self.boot.stage.value);self.update();event.accept()
        elif event.key() in {Qt.Key_Left,Qt.Key_Right,Qt.Key_Up,Qt.Key_Down}:
            self.dynamics.drag(.04 if event.key()==Qt.Key_Right else -.04 if event.key()==Qt.Key_Left else 0.,.04 if event.key()==Qt.Key_Down else -.04 if event.key()==Qt.Key_Up else 0.)
            self.clock.request();event.accept()
        elif event.key() in {Qt.Key_Plus,Qt.Key_Equal,Qt.Key_Minus}:
            self.dynamics.wheel(-1 if event.key()==Qt.Key_Minus else 1);self.clock.request();event.accept()
        else:super().keyPressEvent(event)

    def contextMenuEvent(self,event):
        menu=QMenu(self);menu.addAction('Reset view',self.reset_view)
        menu.addSeparator();menu.addAction('Globe Color…',lambda:self.choose_color('globe_color'))
        menu.addAction('Globe Glow Color…',lambda:self.choose_color('globe_glow_color'))
        menu.setAttribute(Qt.WA_DeleteOnClose);menu.popup(event.globalPos())

    def reset_view(self):self.dynamics.reset();self.clock.request();self.update()

    def choose_color(self,key):
        from .globe_colors import choose_globe_color
        choose_globe_color(self.theme,key,self)

    def showEvent(self,event):
        if self._boot_started is None:self._boot_started=time.perf_counter()
        self._context_check.start()
        self._last_paint=0.;self.clock.request();super().showEvent(event)

    def cleanup(self):
        if self.context() is None:return
        if not self._buffers and self._program is None and self._halo is None:return
        from PySide6.QtGui import QOpenGLContext
        previous=QOpenGLContext.currentContext();surface=previous.surface() if previous is not None else None
        self.makeCurrent()
        for buffer in self._buffers:buffer.destroy()
        self._buffers.clear()
        if self._vao is not None:self._vao.destroy();self._vao=None
        if self._quad is not None:self._quad.destroy();self._quad=None
        for program in (self._program,self._halo):
            if program is not None:program.removeAllShaders();program.deleteLater()
        self._program=self._halo=None;self.doneCurrent()
        if previous is not None and previous is not self.context() and surface is not None:previous.makeCurrent(surface)

    def dispose(self):
        self._closed=True;self._context_check.stop();self.clock.unsubscribe_id(id(self));self.cleanup()

    def diagnostics(self):
        ordered=sorted(self.paint_samples);intervals=sorted(self.frame_intervals)
        return {'gpu':not bool(self._failed) and self._program is not None,'error':self._failed,'gl':self.gl_info,
            'paints':self.paint_count,'layers':len(self.layers),'boot':self.boot.stage.value,
            'animation_mode':self.animation_mode,'orbit_phases':list(self._orbit_phases),
            'cpu_submission_p95_ms':ordered[int((len(ordered)-1)*.95)] if ordered else None,
            'present_interval_p95_ms':intervals[int((len(intervals)-1)*.95)] if intervals else None,
            'frame_samples':len(intervals),'scope':'CPU submission and paint intervals; GPU time is measured externally.'}

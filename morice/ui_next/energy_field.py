"""Native vector scenes over cached soft light; no video or desktop capture."""
from __future__ import annotations

from collections import deque
import math
import random
import time

from PySide6.QtCore import Qt, QPointF, QRect
from PySide6.QtGui import QColor, QImage, QPixmap, QPainter, QPainterPath, QPen, QRadialGradient, QBrush, QTransform
from PySide6.QtWidgets import QWidget

from .core_view import core_color, with_alpha
from .core_state import CoreSnapshot
from .theme_scenes import LOOP_SECONDS, loop_angle, scene_points, particle_position, SCENES


FIELD_BUDGETS = {'LOW': (256,144,4,4), 'BALANCED': (336,210,12,8), 'HIGH': (432,270,16,12), 'ULTRA': (560,350,20,18)}


class EnergyField(QWidget):
    """Cached software raster, regenerated at a separate bounded field cadence."""
    def __init__(self, owner, theme, policy, clock, model=None):
        super().__init__(owner);self.owner=owner;self.theme=theme;self.policy=policy;self.clock=clock;self.model=model
        self.setAttribute(Qt.WA_TransparentForMouseEvents);self.setAttribute(Qt.WA_NoSystemBackground)
        self._cache=None;self._key=None;self._phase=0.;self._elapsed=0.;self._pointer=None;self._velocity=0.;self._pulse=0.;self._points=[]
        self._raster_phase=0.;self._path_key=None;self._path_cache=[]
        self.paint_count=0;self.render_count=0;self.raster_samples=deque(maxlen=600);self.paint_samples=deque(maxlen=600)
        rng=random.Random(103);self._particles=[(rng.random(),rng.random(),rng.uniform(.002,.007),rng.random()*math.tau) for _ in range(48)]
        self.resize(owner.size());self.show();self.lower();clock.subscribe(self,self.tick)
        theme.changed.connect(self.invalidate);policy.changed.connect(self.invalidate)
        if model:model.changed.connect(self.state_changed)

    def state_changed(self,snapshot):
        # RMS changes belong to the Core; do not rerasterize the field at audio Hz.
        key=snapshot.state
        if key != getattr(self,'_state',None):self._state=key;self.invalidate()

    def invalidate(self,*_):
        self._cache=None;self._key=None;self._path_key=None
        if not self.policy.budget.decorative_motion or not self.policy.budget.particle_count:self._points=[];self._pulse=0.
        self.update();self.clock.request()

    def pointer_changed(self,event):
        if event is None:self._pointer=None;self._velocity=0.;self._pulse=0.;return
        if not self.theme.profile.cursor_light or self.theme.profile.high_contrast:return
        point=event['point'];normalized=QPointF(point.x()/max(1,self.width()),point.y()/max(1,self.height()))
        if self._pointer is not None and self.policy.budget.decorative_motion:
            self._velocity=min(.04,math.hypot(normalized.x()-self._pointer.x(),normalized.y()-self._pointer.y()))
        self._pointer=normalized
        if event.get('pressed') and self.policy.budget.decorative_motion:self._pulse=1.
        self._elapsed=1.;self.clock.request()

    def resizeEvent(self,event):self._cache=None;self._key=None;self._path_key=None;super().resizeEvent(event)

    @staticmethod
    def dirty(point):return QRect(round(point[0])-5,round(point[1])-5,11,11)

    def _moving(self):
        p=self.theme.profile
        return p.background_effects and p.field_motion > 0 and p.field_intensity > 0 and not p.high_contrast and self.policy.budget.decorative_motion and self.owner.isActiveWindow() and self.owner.isVisible() and not self.owner.isMinimized()

    def tick(self,delta):
        budget=self.policy.budget;moving=self._moving();fps=FIELD_BUDGETS[budget.effective][2]
        if moving:
            profile=self.theme.profile
            self._phase=(self._phase+delta*profile.motion_speed*(.4+1.4*profile.field_motion)*profile.motion_strength)%LOOP_SECONDS
            self._pulse=max(0.,self._pulse-delta*2);self._velocity*=math.exp(-delta*5)
            self._elapsed+=delta
            if self._elapsed >= 1/max(1,fps):
                self._elapsed%=1/max(1,fps);self._raster_phase=self._phase
                self._cache=None;self._key=None
            # Crisp contours follow every shared-clock frame. Only the diffuse
            # light raster uses the lower cadence; its pixels never form lines.
            self.update()
        if budget.decorative_motion and budget.particle_count and self.theme.profile.background_effects and not self.theme.profile.high_contrast and self.owner.isActiveWindow() and self.owner.isVisible() and not self.owner.isMinimized():
            old=self._points
            self._points=[(x*self.width(),y*self.height()) for x,y in (particle_position(seed,loop_angle(self._phase)) for seed in self._particles[:budget.particle_count])]
            for point in old+self._points:self.update(self.dirty(point))
            moving=True
        return moving

    def _colors(self):
        profile=self.theme.profile;snapshot=self.model.snapshot if self.model else CoreSnapshot()
        color=core_color(snapshot,self.theme.tokens) if profile.field_palette=='STATE' else QColor(self.theme.tokens['accent_secondary'] if profile.field_palette=='VIOLET' else '#79d7f3' if profile.field_palette=='CYAN' else self.theme.tokens['accent_primary'])
        return color,QColor(self.theme.tokens['accent_secondary'])

    def _native_paths(self,layers):
        key=(self.theme.profile.preset,layers,self.width(),self.height())
        if key==self._path_key:return self._path_cache
        paths=[];preset=self.theme.profile.preset
        angular=preset in {'GLASS','OBSIDIAN','NEON','MONOCHROME'}
        for layer in range(layers):
            points=[]
            for x,y in scene_points(preset,layer,layers,0.):
                points.append(QPointF(x*self.width(),y*self.height()))
            path=QPainterPath(points[0])
            if angular:
                for point in points[1:]:path.lineTo(point)
            else:
                # Catmull-Rom to cubic splines: smooth native-resolution curves,
                # including tangent continuity across closed path endpoints.
                closed=preset!='ARCTIC';knots=points[:-1] if closed else points
                count=len(knots);segments=count if closed else count-1
                for index in range(segments):
                    first=knots[index];second=knots[(index+1)%count]
                    previous=knots[(index-1)%count] if closed else knots[max(0,index-1)]
                    following=knots[(index+2)%count] if closed else knots[min(count-1,index+2)]
                    path.cubicTo(first+(second-previous)/6,second-(following-first)/6,second)
                if closed:path.closeSubpath()
            paths.append((path,points))
        self._path_key=key;self._path_cache=paths;return paths

    def _pose(self,phase,layer):
        """Closed per-theme transforms over cached native curve geometry."""
        preset=self.theme.profile.preset;offset=layer*.61;direction=-1 if layer%2 else 1
        turn=phase*direction;lift=.018*math.sin(phase*2+offset)
        sx=1+.035*math.sin(phase+offset);sy=1+.055*math.cos(phase+offset);shear=0.
        if preset=='GLASS':turn+=.35*math.sin(phase+offset);lift=.035*math.sin(phase+offset);sx=sy=1+.025*math.cos(phase*2+offset)
        elif preset=='OBSIDIAN':turn=-phase*direction;lift=.012*math.sin(phase*3+offset);sx=1+.02*math.sin(phase*2+offset);sy=1+.02*math.cos(phase*3+offset)
        elif preset=='ARCTIC':turn=.045*math.sin(phase+offset);lift=.035*math.sin(phase*2+offset);shear=.08*math.sin(phase+offset)
        elif preset=='ICE':sx=sy=.94+.065*math.cos(phase+offset)
        elif preset=='AMETHYST':turn=.4*math.sin(phase+offset);sx=sy=.94+.09*math.sin(phase*2+offset)
        elif preset=='MIDNIGHT':sy=1+.15*math.sin(phase+offset)
        elif preset=='NEON':turn=0.;sx=1+.02*math.sin(phase+offset);sy=1+.02*math.cos(phase+offset)
        elif preset=='MONOCHROME':turn=.14*math.sin(phase+offset);shear=.05*math.cos(phase+offset)
        elif preset=='CUSTOM':sx=1+.12*math.sin(phase+offset);sy=1+.12*math.cos(phase*2+offset)
        elif preset=='SOLAR':sx=sy=.96+.06*math.sin(phase*2+offset)
        elif preset=='CRIMSON':turn=0.;lift=0.;sx=sy=.94+.08*math.sin(phase*2+offset)+.015*math.sin(phase)
        dx=0.;dy=lift*self.height()
        if self._pointer is not None and self.policy.budget.decorative_motion:
            dx=(self._pointer.x()-.5)*self.width()*.012*math.cos(offset)
            dy+=(self._pointer.y()-.5)*self.height()*.012*math.sin(offset)
        transform=QTransform();transform.translate(self.width()*.5+dx,self.height()*.5+dy)
        transform.rotate(math.degrees(turn));transform.shear(shear,0.);transform.scale(sx,sy);transform.translate(-self.width()*.5,-self.height()*.5)
        return transform

    def draw_contours(self,painter):
        profile=self.theme.profile
        if not profile.background_effects or profile.high_contrast or profile.field_intensity==0:return
        painter.setRenderHint(QPainter.Antialiasing)
        phase=loop_angle(self._phase) if self.policy.budget.decorative_motion else 0.
        color,secondary=self._colors();intensity=profile.field_intensity
        layers=FIELD_BUDGETS[self.policy.budget.effective][3]
        for layer,(path,points) in enumerate(self._native_paths(layers)):
            painter.save();painter.setTransform(self._pose(phase,layer),True)
            shade=color if layer%3 else secondary
            painter.setBrush(with_alpha(shade,28*intensity) if profile.preset=='GLASS' else Qt.NoBrush)
            painter.setPen(QPen(with_alpha(shade,(120+30*math.sin(layer*.7))*intensity),1.05,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));painter.drawPath(path)
            if profile.preset in {'MIDNIGHT','NEON','SOLAR'}:
                painter.setPen(Qt.NoPen);painter.setBrush(with_alpha(shade,210*intensity))
                if profile.preset=='MIDNIGHT':
                    for index in range(layer%5,96,16):painter.drawEllipse(points[index],2.,2.)
                else:painter.drawEllipse(path.pointAtPercent((phase/math.tau+layer*.13)%1),2.,2.)
            painter.restore()
        if self._pointer is not None and self._pulse and self.policy.budget.decorative_motion:
            center=QPointF(self._pointer.x()*self.width(),self._pointer.y()*self.height());radius=self.width()*.07*(1-self._pulse)
            painter.setBrush(Qt.NoBrush);painter.setPen(QPen(with_alpha(color,90*intensity*self._pulse),1.));painter.drawEllipse(center,radius,radius)

    def material(self):
        profile=self.theme.profile
        if not profile.background_effects or profile.high_contrast or profile.field_intensity == 0:return None
        width,height,_,layers=FIELD_BUDGETS[self.policy.budget.effective]
        key=(id(self.theme.tokens),self.policy.budget.effective,self.width(),self.height(),self._raster_phase,self._state if hasattr(self,'_state') else None)
        if self._cache is not None and key==self._key:return self._cache
        started=time.perf_counter();image=QImage(width,height,QImage.Format_ARGB32_Premultiplied);image.fill(Qt.transparent)
        p=QPainter(image);p.setRenderHint(QPainter.Antialiasing)
        color,secondary=self._colors();intensity=profile.field_intensity
        phase=loop_angle(self._raster_phase) if self.policy.budget.decorative_motion else 0.
        for x,y,r,shade in ((.14,.34,.64,color),(.86,.74,.7,secondary),(.5,.5,.48,color)):
            center=QPointF(width*(x+.035*math.sin(phase+x)),height*(y+.035*math.cos(phase+y)));radius=height*r;gradient=QRadialGradient(center,radius)
            gradient.setColorAt(0,with_alpha(shade,105*intensity));gradient.setColorAt(1,with_alpha(shade,0))
            p.setPen(Qt.NoPen);p.setBrush(QBrush(gradient));p.drawEllipse(center,radius,radius)
        if self._pointer is not None:
            center=QPointF(self._pointer.x()*width,self._pointer.y()*height);radius=width*.14
            gradient=QRadialGradient(center,radius);gradient.setColorAt(0,with_alpha(color,75*intensity));gradient.setColorAt(1,with_alpha(color,0))
            p.setPen(Qt.NoPen);p.setBrush(QBrush(gradient));p.drawEllipse(center,radius,radius)
        p.end()
        if profile.preset=='GLASS' and profile.blur>0:
            # Cached raster resampling diffuses our own light field only.
            factor=1+profile.blur*2
            image=image.scaled(round(width/factor),round(height/factor),Qt.IgnoreAspectRatio,Qt.SmoothTransformation).scaled(width,height,Qt.IgnoreAspectRatio,Qt.SmoothTransformation)
        self._cache=QPixmap.fromImage(image);self._key=key;self.render_count+=1;self.raster_samples.append((time.perf_counter()-started)*1000)
        return self._cache

    def paintEvent(self,event):
        started=time.perf_counter();self.paint_count+=1;p=QPainter(self);p.setClipRegion(event.region());p.setRenderHint(QPainter.SmoothPixmapTransform)
        image=self.material()
        if image is not None:p.drawPixmap(self.rect(),image)
        self.draw_contours(p)
        if self.policy.budget.decorative_motion and not self.theme.profile.high_contrast:
            p.setPen(Qt.NoPen);p.setBrush(with_alpha(QColor(self.theme.tokens['accent_primary']),24*self.policy.budget.glow_factor))
            for x,y in self._points:p.drawEllipse(QPointF(x,y),1.2,1.2)
        p.end();self.paint_samples.append((time.perf_counter()-started)*1000)

    def showEvent(self,event):self.clock.request();super().showEvent(event)

    def close(self):self.clock.unsubscribe_id(id(self));self._cache=None;self._points=[];self._path_cache=[];return super().close()

    def diagnostics(self):
        return {'scene':SCENES[self.theme.profile.preset][0], 'contour_renderer':'native_antialiased_vector','contour_size':[self.width(),self.height()], 'loop_seconds':LOOP_SECONDS, 'raster_size':list(FIELD_BUDGETS[self.policy.budget.effective][:2]),'raster_count':self.render_count,
            'paints':self.paint_count,'moving':self._moving(),'samples':len(self.raster_samples),'scope':'Software raster and widget paint CPU time; excludes compositor presentation.'}

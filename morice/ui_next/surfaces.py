"""Frosted application surfaces; sample only MORICE's procedural raster."""
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QPen
from PySide6.QtWidgets import QFrame

class MaterialSurface(QFrame):
    def paintEvent(self, event):
        super().paintEvent(event)
        owner=self.window();theme=getattr(owner,'theme_engine',None)
        if theme is None or theme.profile.high_contrast:return
        profile=theme.profile
        if profile.preset!='GLASS':return
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        path=QPainterPath();path.addRoundedRect(rect,theme.tokens.radius_medium,theme.tokens.radius_medium);painter.setClipPath(path)
        field=getattr(owner,'material_backdrop',None)
        if field is not None and field.isVisible() and profile.glass>0:
            raster=field.material()
            if raster is not None:
                top=self.mapTo(owner,QPoint())
                source=QRectF(top.x()/max(1,owner.width())*raster.width(), top.y()/max(1,owner.height())*raster.height(),
                    self.width()/max(1,owner.width())*raster.width(), self.height()/max(1,owner.height())*raster.height())
                painter.setOpacity(.3*profile.glass);painter.setRenderHint(QPainter.SmoothPixmapTransform);painter.drawPixmap(rect,raster,source);painter.setOpacity(1)
        sheen=QLinearGradient(rect.topLeft(),rect.bottomRight())
        sheen.setColorAt(0,QColor(225,245,255,round(35*profile.glass)))
        sheen.setColorAt(.45,QColor(190,218,255,round(6*profile.glass)))
        sheen.setColorAt(1,QColor(200,185,255,round(18*profile.glass)))
        painter.fillPath(path,sheen);painter.setPen(QPen(QColor(200,233,255,round(80*profile.glass)),1));painter.drawPath(path);painter.end()

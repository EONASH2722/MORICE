"""Reference-sized top-edge panel: production orb, transcript, Pause/Play."""
from __future__ import annotations

from PySide6.QtCore import Qt,QPoint,Signal,QPropertyAnimation,QEasingCurve,QRectF,QSize
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen,QPixmap,QImage,QShortcut,QKeySequence,QCursor,QIcon
from PySide6.QtWidgets import QWidget,QLabel,QVBoxLayout,QHBoxLayout,QPushButton,QLineEdit,QTextBrowser,QApplication,QLayout
from shiboken6 import isValid
from ..orb_pet import OrbPresentation,appearance_directory
from .themes import ThemeEngine
from .motion import EffectPolicy,EffectClock
from .globe_renderer import HolographicGlobe
from .globe_state import GlobeBoot
from .window_material import apply_backdrop


class PopupOrb(QWidget):
    """Existing globe rendered into a tiny image, outside the glass surface.

    No onscreen GL child: avoids an opaque GL tile and native GL-window churn
    when the glass popup appears. No cursor API or additional renderer.
    """
    def __init__(self,parent=None):
        super().__init__(parent);self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.theme=ThemeEngine(appearance_directory());self.policy=EffectPolicy(self.theme)
        self.clock=EffectClock(self.policy,self);self.model=OrbPresentation(self)
        self.canvas=HolographicGlobe(self.model,self.theme,self.policy,self.clock,
            boot=GlobeBoot(ready=True,skipped=True),transparent_pet=True)
        self.canvas.setAttribute(Qt.WA_DontShowOnScreen);self.canvas.setMinimumSize(1,1)
        self.canvas.resize(64,64);self.canvas._center=self.canvas._center_target=(.5,.5)
        self.setFixedSize(18,18);self.level=0.;self.level_source=None;self._state='IDLE'
        self._image=QImage();self._elapsed=1.;self._disposed=False;self.clock.subscribe(self,self.tick)

    @property
    def state(self):return self._state
    @state.setter
    def state(self,value):
        self._state=getattr(value,'value',value);self._present();self.clock.request()

    def _present(self):
        self.level=self.level_source() if self.level_source else 0.
        state=self._state if self._state in {'IDLE','LISTENING','UNDERSTANDING','WORKING','SPEAKING','ERROR','SUCCESS'} else 'WORKING'
        self.model.present({'state':state,'level':max(0.,min(1.,self.level/100))})

    def tick(self,delta):
        if self._disposed or not self.isVisible():return False
        self._present();self.canvas.tick(delta);self._elapsed+=delta
        if self._elapsed>=.05:
            self._elapsed=0.
            if QApplication.platformName() not in {'offscreen','minimal'}:self._image=self.canvas.grabFramebuffer()
            self.update()
        return not self.theme.profile.reduced_motion or self._state in {'LISTENING','SPEAKING'}

    def paintEvent(self,event):
        if self._image.isNull():return
        painter=QPainter(self);painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(self.rect(),self._image);painter.end()

    def reload(self,reduced=False):
        profile=self.theme.store.load()
        if profile!=self.theme.profile:self.theme.apply_profile(profile,persist=False)
        if reduced!=self.theme.profile.reduced_motion:self.theme.update(reduced_motion=reduced,persist=False)
        self.clock.request()

    def dispose(self):
        if self._disposed:return
        self._disposed=True;self.canvas.dispose();self.canvas.deleteLater();self.clock.close();self._image=QImage()


class TopAssistantPopup(QWidget):
    cancelled=Signal();reviewed_command=Signal();submitted=Signal(str)
    microphone=Signal();open_main=Signal();dismissed=Signal();pause_requested=Signal(bool)

    def __init__(self):
        super().__init__(None,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint)
        self.setWindowTitle('MORICE Background Helper');self.setObjectName('BackgroundHelperPopup')
        self.setAttribute(Qt.WA_ShowWithoutActivating);self.setAttribute(Qt.WA_QuitOnClose,False)
        self.setAttribute(Qt.WA_TranslucentBackground);self.setAutoFillBackground(False)
        self.material='glass';self.backdrop='pending';self._paused=False;self._screen=None;self._closing=False
        self.phase='HIDDEN';self.animate=True;self.transitions=[];self.interaction_state='RESULT_VISIBLE'
        self.setStyleSheet('''
            QLabel {color:#f5f4f8;background:transparent;border:0;}
            QPushButton {color:#c3c0ca;background:transparent;border:0;border-radius:5px;padding:0;font-size:13px;}
            QPushButton:hover {color:white;background:rgba(255,255,255,20);}
            QLineEdit {background:transparent;color:#f7f6fb;border:0;padding:5px 0;font-size:12px;selection-background-color:#74529b;}
            QTextBrowser {background:transparent;color:#f2f0f5;border:0;font-size:12px;}
            QScrollBar:vertical {width:4px;background:transparent;} QScrollBar::handle:vertical {background:#77717f;border-radius:2px;}
        ''')
        self.root=QVBoxLayout(self);self.root.setContentsMargins(18,10,18,11);self.root.setSpacing(10)
        self.root.setSizeConstraint(QLayout.SetNoConstraint)
        row=QHBoxLayout();row.setContentsMargins(0,0,0,0);self.orb=PopupOrb(self);row.addWidget(self.orb)
        self.state_label=QLabel('MORICE');self.state_label.setStyleSheet('font-size:10px;color:#a6a1ad;')
        row.addWidget(self.state_label);row.addStretch()
        self.state_label.hide()
        self.pause=QPushButton();self.pause.setFixedSize(24,24);self.pause.setIconSize(QSize(16,16));self.pause.setAccessibleName('Pause helper');self.pause.setToolTip('Pause listening and response')
        self.pause.clicked.connect(lambda:self.pause_requested.emit(not self._paused));row.addWidget(self.pause);self.root.addLayout(row)
        self.preview=QLabel();self.preview.hide();self.root.addWidget(self.preview)
        self.transcript=QLabel();self.transcript.setTextFormat(Qt.PlainText);self.transcript.setWordWrap(True);self.transcript.setMaximumHeight(48)
        self.transcript.setStyleSheet('font-size:12px;');self.root.addWidget(self.transcript)
        self.answer=QTextBrowser();self.answer.setOpenExternalLinks(False);self.answer.setMinimumHeight(48);self.answer.setMaximumHeight(155);self.answer.hide();self.root.addWidget(self.answer,1)
        self.sources=QLabel();self.sources.setTextFormat(Qt.PlainText);self.sources.setWordWrap(True);self.sources.setMaximumHeight(36);self.sources.hide();self.root.addWidget(self.sources)
        row=QHBoxLayout();self.entry=QLineEdit();self.entry.setPlaceholderText('Type a question, or speak to MORICE');self.entry.setAccessibleName('Ask Background Helper')
        self.entry.returnPressed.connect(self.send);row.addWidget(self.entry,1)
        self.mic=QPushButton('●');self.mic.setFixedSize(22,22);self.mic.setAccessibleName('Ask by voice');self.mic.setToolTip('Speak a question');self.mic.clicked.connect(self.microphone)
        from .icons import icon
        self.mic.setText('');self.mic.setIcon(icon('voice',self.orb.theme))
        row.addWidget(self.mic);self.root.addLayout(row)
        self.run=QPushButton('Send transcript');self.run.clicked.connect(self.reviewed_command);self.run.hide();self.root.addWidget(self.run)
        self.cancel=QPushButton();self.cancel.hide()
        QShortcut(QKeySequence('Esc'),self,activated=self.cancelled.emit)
        QShortcut(QKeySequence('Ctrl+Shift+C'),self,activated=lambda:QApplication.clipboard().setText(self.answer.toPlainText()))
        self.animation=QPropertyAnimation(self,b'pos',self);self.animation.setDuration(190);self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.finished.connect(self._animation_finished)
        self.set_paused(False)

    def configure_material(self,material):
        if material not in {'dark','glass'}:raise ValueError('Unknown popup material.')
        self.material=material
        if self.isVisible():self.backdrop=apply_backdrop(self,material=='glass')
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        path=QPainterPath();path.addRoundedRect(QRectF(self.rect()).adjusted(.5,-14,-.5,-.5),24,24)
        painter.fillPath(path,QColor(5,5,7,100 if self.material=='glass' else 249))
        painter.setPen(QPen(QColor(255,255,255,35 if self.material=='glass' else 18),.7));painter.drawPath(path);painter.end()

    def set_paused(self,value):
        self._paused=bool(value)
        pixmap=QPixmap(32,32);pixmap.fill(Qt.transparent);painter=QPainter(pixmap);painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen);painter.setBrush(QColor('#f4f2f7'))
        if value:
            triangle=QPainterPath();triangle.moveTo(10,6);triangle.lineTo(26,16);triangle.lineTo(10,26);triangle.closeSubpath();painter.drawPath(triangle)
        else:
            painter.drawRoundedRect(QRectF(8,6,5,20),1.5,1.5);painter.drawRoundedRect(QRectF(19,6,5,20),1.5,1.5)
        painter.end();self.pause.setIcon(QIcon(pixmap))
        self.pause.setAccessibleName('Resume helper' if value else 'Pause helper');self.pause.setToolTip('Resume listening' if value else 'Pause listening and response')

    def send(self):
        text=self.entry.text().strip()
        if text:self.entry.clear();self.submitted.emit(text)

    def place(self,preferences=None,screen=None):
        if screen is not None and not isValid(screen):screen=None
        if self._screen is not None and not isValid(self._screen):self._screen=None
        self._screen=screen or self._screen or QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if self._screen is None:return
        area=self._screen.geometry();width=min(460,max(240,area.width()-40));limit=max(150,int(area.height()*.44))
        self.setFixedWidth(width);self.setMaximumHeight(limit)
        if self.animation.state()!=QPropertyAnimation.Running:self.resize(width,max(110,min(limit,self.root.sizeHint().height())))
        self._target=QPoint(area.center().x()-width//2,area.top())
        if not self.isVisible():self.move(self._target.x(),area.top()-self.height()-1)
        elif self.animation.state()!=QPropertyAnimation.Running and not self._closing:self.move(self._target)

    def _phase(self,value):
        if self.phase!=value:self.transitions.append(value)
        self.phase=value;self.transitions=self.transitions[-80:]

    def interaction(self,state):
        self.interaction_state=state
        if self.phase not in {'SLIDING_DOWN','SLIDING_UP'}:self._phase(state)

    def show(self):
        if self.isVisible() and not self._closing:return
        self._closing=False;self.animation.stop();self.place(screen=self._screen)
        super().show();self.backdrop=apply_backdrop(self,self.material=='glass');self.orb.clock.request();self._phase('SLIDING_DOWN')
        if self.animate:self.animation.setStartValue(self.pos());self.animation.setEndValue(self._target);self.animation.start()
        else:self.move(self._target);self._phase(self.interaction_state)

    def dismiss(self):
        if not self.isVisible():self._phase('HIDDEN');self.dismissed.emit();return
        self._closing=True;self.animation.stop();self._phase('SLIDING_UP')
        if self.animate and self._screen is not None and isValid(self._screen):
            self.animation.setStartValue(self.pos());self.animation.setEndValue(QPoint(self.x(),self._screen.geometry().top()-self.height()-1));self.animation.start()
        else:self._animation_finished()

    def _animation_finished(self):
        if self._closing:self.hide();self._closing=False;self._phase('HIDDEN');self.dismissed.emit()
        else:self.move(self._target);self._phase(self.interaction_state);self.place(screen=self._screen)

    def set_selection(self,png):
        if png:
            pixmap=QPixmap();pixmap.loadFromData(png);self.preview.setPixmap(pixmap.scaled(max(200,self.width()-36),78,Qt.KeepAspectRatio,Qt.SmoothTransformation));self.preview.show()
        else:self.preview.clear();self.preview.hide()
        self.place(screen=self._screen)

    def response(self,text,*,streaming=False):
        self.answer.setPlainText(str(text));self.answer.show();self.answer.verticalScrollBar().setValue(self.answer.verticalScrollBar().maximum())
        document=self.answer.document();document.setTextWidth(max(200,self.width()-36))
        self.answer.setFixedHeight(max(42,min(155,round(document.size().height()+8))))
        self.interaction('STREAMING_REPLY' if streaming else 'RESULT_VISIBLE');self.place(screen=self._screen)

    def reset(self):
        self.answer.clear();self.answer.hide();self.transcript.clear();self.sources.clear();self.sources.hide();self.run.hide();self.entry.clear()
        self.preview.clear();self.preview.hide();self.set_paused(False)

    def closeEvent(self,event):event.ignore();self.cancelled.emit()
    def dispose(self):self.animation.stop();self.hide();self.orb.dispose()

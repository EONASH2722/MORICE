"""Actual artifact collections and lazy existing native preview renderers."""
from __future__ import annotations

from pathlib import Path
import hashlib
import re
from xml.etree import ElementTree

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QFrame,QSlider
from PySide6.QtCore import Qt

from .rich_primitives import plain,display
from .media_view import ArtifactViewer,decoded_image


class ArtifactPreview(QWidget):
    def __init__(self,artifact,context):
        super().__init__();self.artifact=artifact;self.context=context;self.player=None;self.preview=None;self.image=None;self._disposed=False;self._decoded_frames=0
        self.body=QVBoxLayout(self);self.status=plain('Reading the actual verified file…');self.body.addWidget(self.status)
        if not artifact.available:self.status.setText(artifact.reason);return
        extension=artifact.path.suffix.casefold()
        if extension in {'.png','.jpg','.jpeg','.webp','.bmp','.gif'}:
            self.image=ArtifactViewer();self.body.addWidget(self.image)
            context.submit(self,'Decode actual image',lambda:decoded_image(artifact.path,artifact.sha256),self.image_ready,self.failed)
        elif extension in {'.mp4','.webm','.mov','.mkv','.avi','.wav','.mp3','.flac','.m4a'}:
            self.video(extension)
        elif extension=='.svg':
            context.submit(self,'Validate actual SVG preview',lambda:self.safe_svg(artifact.path,artifact.sha256),self.svg_ready,self.failed)
        elif extension in {'.pdf','.txt','.md','.py','.js','.json','.csv','.log','.yaml','.yml','.toml','.html','.css','.xml','.stl','.step','.stp'}:
            if extension in {'.stl','.step','.stp'}:
                self.status.setText('Use the actual STL viewer for mesh geometry. STEP preview is unavailable until a tested CAD backend is installed.');return
            if artifact.size>8*1024**2:self.status.setText('Inline document preview is limited to 8 MiB; the actual file remains available for export.');return
            from ..ui_workspace import FilePreview
            self.preview=FilePreview();self.preview.open_external.hide();self.preview.setMinimumHeight(240);self.preview.setMaximumHeight(460)
            self.body.addWidget(self.preview);okay,message=self.preview.show_file(str(artifact.path));self.status.setText(message)
            from ..media_lab.storage import file_hash
            if file_hash(artifact.path)!=artifact.sha256:self.preview.clear('File changed before preview; reload its source.');self.status.setText('Preview source changed.');self.preview.pdf_document.close() if self.preview.pdf_document else None
        else:self.status.setText('No inline renderer is registered for this file type. Its verified file can be exported.')

    def image_ready(self,value):
        if self._disposed:return
        self.image.set_image(value);self.status.setText('Actual verified image · '+self.artifact.name)

    @staticmethod
    def safe_svg(path,expected_hash=None):
        raw=Path(path).read_bytes()
        if expected_hash is not None and hashlib.sha256(raw).hexdigest()!=expected_hash:raise ValueError('SVG hash changed before preview.')
        if len(raw)>2*1024**2 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('SVG exceeds safe preview limits.')
        root=ElementTree.fromstring(raw)
        for node in root.iter():
            tag=node.tag.rsplit('}',1)[-1].casefold()
            if tag in {'script','foreignobject','style'}:raise ValueError('This SVG contains content unavailable in the native preview.')
            for key,value in node.attrib.items():
                if key.rsplit('}',1)[-1].casefold() in {'href','src'} and not value.startswith('#'):
                    raise ValueError('SVG preview cannot load external resources.')
                if re.search(r'(?:https?:|file:|data:|url\s*\()',value,re.I):raise ValueError('SVG preview cannot load external resources.')
        return ElementTree.tostring(root)

    def svg_ready(self,data):
        if self._disposed:return
        try:
            from PySide6.QtSvgWidgets import QSvgWidget
            self.preview=QSvgWidget();self.preview.load(data);self.preview.setMinimumHeight(250);self.preview.setMaximumHeight(420)
            self.body.addWidget(self.preview);self.status.setText('Actual verified SVG · '+self.artifact.name)
        except ImportError:self.status.setText('Native SVG renderer is unavailable; the actual file can still be exported.')

    def video(self,extension):
        try:
            from PySide6.QtMultimedia import QMediaPlayer,QAudioOutput
            from PySide6.QtMultimediaWidgets import QVideoWidget
        except ImportError:self.status.setText('Native media playback is unavailable in this build.');return
        self.player=QMediaPlayer(self);self.audio=QAudioOutput(self);self.player.setAudioOutput(self.audio)
        if extension not in {'.wav','.mp3','.flac','.m4a'}:
            self.preview=QVideoWidget();self.preview.setMinimumHeight(230);self.preview.setMaximumHeight(420)
            self.body.addWidget(self.preview);self.player.setVideoOutput(self.preview)
            self.preview.videoSink().videoFrameChanged.connect(self.frame)
        controls=QHBoxLayout();play=QPushButton('Play');pause=QPushButton('Pause');stop=QPushButton('Stop')
        play.clicked.connect(self.play_verified);pause.clicked.connect(self.player.pause);stop.clicked.connect(self.player.stop)
        for button in (play,pause,stop):controls.addWidget(button)
        self.body.addLayout(controls);self.seek=QSlider(Qt.Horizontal);self.seek.setAccessibleName('Actual media playback position')
        self.seek.sliderMoved.connect(self.player.setPosition);self.body.addWidget(self.seek)
        self.player.durationChanged.connect(lambda duration:self.seek.setRange(0,duration))
        self.player.positionChanged.connect(self.seek.setValue)
        self.player.errorOccurred.connect(lambda error,description:self.failed('Playback unavailable: '+description))
        self.player.setSource(QUrl.fromLocalFile(str(self.artifact.path)));self.status.setText('Actual media file ready. Choose Play to start playback.')

    def play_verified(self):
        def ready(snapshot):
            actual=next((item for item in snapshot.artifacts if item.id==self.artifact.id),None)
            if actual is None or not actual.available or actual.sha256!=self.artifact.sha256:self.failed('Media source changed before playback.');return
            self.player.play();self.status.setText('Playing the actual verified local file.')
        self.context.submit(self,'Recheck media before playback',lambda:self.context.sources.resolve(self.context.component.source),ready,self.failed)

    def frame(self,value):
        if value.isValid():self._decoded_frames+=1

    def failed(self,error):
        if not self._disposed:self.status.setText(str(error))

    def dispose(self):
        self._disposed=True
        if self.player is not None:self.player.stop();self.player.setSource(QUrl())
        if self.preview is not None and getattr(self.preview,'pdf_document',None) is not None:self.preview.pdf_document.close()
        if self.image is not None:self.image.scene_owner.clear()


class FilesView(QWidget):
    def __init__(self,component,context):
        super().__init__();self.component=component;self.context=context;self.preview=None;self._disposed=False;self._preview_revision=0
        self.body=QVBoxLayout(self);files=context.snapshot.artifacts
        formats=component.config.get('formats',[])
        if formats:files=[a for a in files if a.path.suffix.casefold().lstrip('.') in {f.casefold().lstrip('.') for f in formats}]
        verified=sum(a.available for a in files)
        self.status=plain(f'{verified} / {len(files)} actual file entries currently available.' if files else 'No actual artifact files are available for this source.')
        self.body.addWidget(self.status)
        for artifact in files[:100]:
            card=QFrame();card.setProperty('role','surface');box=QVBoxLayout(card);box.addWidget(plain(artifact.name))
            box.addWidget(plain(display(artifact.size/1024)+' KiB · SHA-256 '+artifact.sha256[:16]+'…',role='secondary'))
            row=QHBoxLayout();preview=QPushButton('Preview');export=QPushButton('Export file…');row.addWidget(preview);row.addWidget(export);box.addLayout(row)
            preview.clicked.connect(lambda _=False,item=artifact:self.open_preview(item))
            export.clicked.connect(lambda _=False,item=artifact:self.export(item));self.body.addWidget(card)
            if not artifact.available:
                preview.setEnabled(False);export.setEnabled(False);box.addWidget(plain(artifact.reason,role='secondary'))

    def open_preview(self,artifact):
        self._preview_revision+=1;revision=self._preview_revision
        if self.preview is not None:self.preview.dispose();self.body.removeWidget(self.preview);self.preview.deleteLater()
        # Reload source/hash before decoding; missing/stale data cannot become a substitute preview.
        def ready(snapshot):
            if self._disposed or revision!=self._preview_revision:return
            current=next((a for a in snapshot.artifacts if a.id==artifact.id),None)
            if current is None or not current.available:self.status.setText(current.reason if current else 'That file is no longer available.');return
            self.preview=ArtifactPreview(current,self.context);self.body.addWidget(self.preview)
        self.context.submit(self,'Recheck preview source',lambda:self.context.sources.resolve(self.component.source),ready,lambda error:self.status.setText(str(error)))

    def export(self,artifact):
        def done(result):
            verified=result.success and result.verification and result.verification.status.value=='verified'
            self.status.setText('File exported and its actual destination hash verified.' if verified else '; '.join(error.message for error in result.errors) or 'Export did not verify.')
        self.context.action(self,'export',{'artifact':artifact.id},done=done,failed=lambda error:self.status.setText(str(error)))

    def dispose(self):
        self._disposed=True
        if self.preview is not None:self.preview.dispose()


class MediaView(QWidget):
    def __init__(self,component,context):
        super().__init__();self.previews=[];layout=QVBoxLayout(self)
        indices=component.config.get('indices',[0]);artifacts=context.snapshot.artifacts
        for index in indices[:4]:
            if not 0<=index<len(artifacts):continue
            preview=ArtifactPreview(artifacts[index],context);layout.addWidget(preview);self.previews.append(preview)
        if not self.previews:layout.addWidget(plain('No completed verified media artifact is available.'))
    def dispose(self):
        for preview in self.previews:preview.dispose()
        self.previews=[]


class PreviewView(QWidget):
    def __init__(self,component,context):
        super().__init__();layout=QVBoxLayout(self);self.preview=None
        artifacts=context.snapshot.artifacts;identifier=component.config.get('artifact')
        artifact=next((a for a in artifacts if a.id==identifier),None) if identifier else next(iter(artifacts),None)
        if artifact is None:layout.addWidget(plain('No actual file matches this preview reference.'));return
        self.preview=ArtifactPreview(artifact,context);layout.addWidget(self.preview)
    def dispose(self):
        if self.preview:self.preview.dispose()

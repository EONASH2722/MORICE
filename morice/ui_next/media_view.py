"""Media Lab presentation over the existing asynchronous scheduler and verifier."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QPainter
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QFormLayout, QComboBox, QSpinBox, QDoubleSpinBox,
    QLineEdit, QPlainTextEdit, QListWidget, QListWidgetItem, QFileDialog,
    QGraphicsView, QGraphicsScene, QSplitter, QScrollArea)

from ..kernel import ExecutionContext
from ..kernel.contracts import VerificationStatus
from ..media_lab.contracts import ImageRequest, VideoRequest
from ..media_lab.artifacts import verify_image
from .file_access import require_selected_file


class ArtifactViewer(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent); self.scene_owner = QGraphicsScene(self); self.setScene(self.scene_owner)
        self.setRenderHint(QPainter.SmoothPixmapTransform); self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setAccessibleName('Verified image viewer. Mouse wheel zooms; drag pans.'); self._has_image = False
        self.setMinimumHeight(220); self._zoom = 1.

    def set_image(self, data):
        image = QImage(data['rgba'], data['preview_width'], data['preview_height'], QImage.Format_RGBA8888).copy()
        self.scene_owner.clear(); self.scene_owner.addPixmap(QPixmap.fromImage(image)); self.scene_owner.setSceneRect(self.scene_owner.itemsBoundingRect())
        self._has_image = True; self.fit()

    def fit(self):
        if self._has_image: self.resetTransform(); self.fitInView(self.scene_owner.sceneRect(), Qt.KeepAspectRatio); self._zoom = 1.

    def wheelEvent(self, event):
        if not self._has_image: return super().wheelEvent(event)
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        if .2 <= self._zoom * factor <= 16: self.scale(factor, factor); self._zoom *= factor
        event.accept()


def decoded_image(path, expected_hash=None):
    from PIL import Image
    from io import BytesIO
    import hashlib
    metadata = verify_image(path, allow_constant=True)
    if expected_hash and metadata['sha256'] != expected_hash: raise ValueError('Verified artifact hash changed before display.')
    with open(path, 'rb') as source: data = source.read(64*1024*1024+1)
    if len(data) > 64*1024*1024 or hashlib.sha256(data).hexdigest() != metadata['sha256']:
        raise ValueError('Image changed between verification and preview; reload the selected artifact.')
    with Image.open(BytesIO(data)) as image:
        image.thumbnail((1600, 1600)); image = image.convert('RGBA')
        return {'metadata': metadata, 'rgba': image.tobytes(), 'preview_width': image.width, 'preview_height': image.height}


class MediaWorkspace(QWidget):
    def __init__(self, runtime, bridge, policy, parent=None):
        super().__init__(parent); self.runtime = runtime; self.bridge = bridge; self.policy = policy
        self.lab = runtime.media; self._refreshing = False; self._refresh_again = False; self._snapshot = {}; self.references = []; self.mask_path = ''
        self.current_generation = ''; self.reference_metadata = None
        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 20)
        title = QLabel('Media Lab'); title.setProperty('role', 'title'); root.addWidget(title)
        self.status = QLabel('Local models stay unloaded until an explicit request.'); self.status.setWordWrap(True); root.addWidget(self.status)
        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        self.generate_page = QWidget(); self.tabs.addTab(self.generate_page, 'Create / edit'); generate = QVBoxLayout(self.generate_page)
        split = QSplitter(); generate.addWidget(split, 1); form_scroll = QScrollArea(); form_scroll.setWidgetResizable(True)
        form_host = QWidget(); form = QFormLayout(form_host); form.setRowWrapPolicy(QFormLayout.WrapAllRows); form_scroll.setWidget(form_host)
        form_scroll.setMinimumWidth(300); form_scroll.setMaximumWidth(520); split.addWidget(form_scroll)
        self.prompt = QPlainTextEdit(); self.prompt.setPlaceholderText('Describe the image or edit…'); self.prompt.setMaximumHeight(120); form.addRow('Prompt', self.prompt)
        self.negative = QLineEdit(); form.addRow('Negative prompt', self.negative)
        self.model = QComboBox(); form.addRow('Inspected model', self.model)
        self.intent = QComboBox()
        for label, value in (('Generate image', 'TEXT_TO_IMAGE'), ('Edit reference', 'IMAGE_TO_IMAGE'), ('Inpaint', 'INPAINT'), ('Outpaint', 'OUTPAINT'), ('Upscale', 'IMAGE_UPSCALE'), ('Text to video', 'TEXT_TO_VIDEO'), ('Image to video', 'IMAGE_TO_VIDEO')): self.intent.addItem(label, value)
        self.intent.currentIndexChanged.connect(self.availability); form.addRow('Workflow', self.intent)
        self.quality = QComboBox()
        for label, value in (('FAST', 'FAST'), ('BALANCED', 'BALANCED'), ('HIGH', 'QUALITY'), ('MAX that fits', 'MAXIMUM_THAT_FITS')): self.quality.addItem(label, value)
        self.quality.setCurrentIndex(1); form.addRow('Quality', self.quality)
        self.width_input = self.integer(form, 'Width', 64, 4096, 512); self.height_input = self.integer(form, 'Height', 64, 4096, 512)
        self.steps = self.integer(form, 'Steps (0: model default)', 0, 100, 0)
        self.seed = QLineEdit('0'); form.addRow('Seed', self.seed); self.count = self.integer(form, 'Variations', 1, 8, 1)
        self.guidance = QDoubleSpinBox(); self.guidance.setRange(0, 30); self.guidance.setValue(0); form.addRow('Guidance', self.guidance)
        self.strength = QDoubleSpinBox(); self.strength.setRange(.01, 1); self.strength.setSingleStep(.05); self.strength.setValue(.5); form.addRow('Edit strength', self.strength)
        self.output_format = QComboBox(); self.output_format.addItems(['PNG', 'JPEG', 'WEBP']); form.addRow('Image format', self.output_format)
        self.frames = self.integer(form, 'Video frames', 1, 16, 8); self.fps = self.integer(form, 'Video FPS', 1, 60, 8)
        reference = QPushButton('Choose reference image'); reference.clicked.connect(self.import_reference); form.addRow(reference)
        mask = QPushButton('Choose mask'); mask.clicked.connect(self.import_mask); form.addRow(mask)
        self.reference_label = QLabel('No supplied reference.'); self.reference_label.setWordWrap(True); form.addRow(self.reference_label)
        self.run = QPushButton('Generate'); self.run.setProperty('role', 'primary'); self.run.clicked.connect(self.submit); form.addRow(self.run)
        self.viewer = ArtifactViewer(); self.viewer.setMinimumWidth(220); split.addWidget(self.viewer); split.setStretchFactor(1, 1); split.setSizes([420, 700])
        self.queue_page = QWidget(); self.tabs.addTab(self.queue_page, 'Queue'); queue_layout = QVBoxLayout(self.queue_page)
        self.queue = QListWidget(); queue_layout.addWidget(self.queue, 1); cancel = QPushButton('Cancel selected job'); cancel.clicked.connect(self.cancel); queue_layout.addWidget(cancel)
        self.history_page = QWidget(); self.tabs.addTab(self.history_page, 'History'); history = QVBoxLayout(self.history_page)
        self.history = QListWidget(); self.history.itemActivated.connect(self.open_history); history.addWidget(self.history, 1)
        actions = QHBoxLayout()
        for label, callback in (('Open verified artifact', self.open_history), ('Export selected artifact', self.export), ('Fit preview', self.viewer.fit)):
            button = QPushButton(label); button.clicked.connect(callback); actions.addWidget(button)
        history.addLayout(actions)
        self.models_page = QWidget(); self.tabs.addTab(self.models_page, 'Models / resources'); models = QVBoxLayout(self.models_page)
        self.models = QListWidget(); models.addWidget(self.models, 1); actions = QHBoxLayout()
        for label, callback in (('Discover local models', self.discover), ('Inspect selected model', self.inspect), ('Refresh resources', self.refresh_resources)):
            button = QPushButton(label); button.clicked.connect(callback); actions.addWidget(button)
        models.addLayout(actions); self.details = QPlainTextEdit(); self.details.setReadOnly(True); models.addWidget(self.details, 1)
        self.timer = QTimer(self); self.timer.setInterval(1500); self.timer.timeout.connect(self.refresh)
        self.bridge.event_arrived.connect(self.runtime_event); self.refresh()

    @staticmethod
    def integer(form, label, minimum, maximum, value):
        field = QSpinBox(); field.setRange(minimum, maximum); field.setValue(value); field.setAccessibleName(label); form.addRow(label, field); return field

    def action(self, title, operation, completed=None, *, priority='interactive'):
        def done(envelope):
            if not envelope['ok']: self.status.setText(envelope['error']); return
            if completed: completed(envelope['value'])
            self.refresh()
        try: return self.bridge.submit(title, operation, done, priority=priority)
        except (ValueError, RuntimeError) as exc: self.status.setText(str(exc))

    def refresh(self):
        if self._refreshing: self._refresh_again = True; return
        self._refreshing = True
        def done(envelope):
            self._refreshing = False
            if not envelope['ok']: self.status.setText(envelope['error']); return
            self._snapshot = envelope['value']; self.apply_snapshot()
            if self._refresh_again and self.isVisible(): self._refresh_again = False; self.refresh()
        try: self.bridge.submit('media-read-state', self.lab.status, done)
        except (ValueError, RuntimeError) as exc: self._refreshing = False; self.status.setText(str(exc))

    def apply_snapshot(self):
        selected = self.model.currentData(); self.model.blockSignals(True); self.model.clear(); self.models.clear()
        for model in self._snapshot['models']:
            self.model.addItem(model['display_name'] + ' · ' + model['health'], model['model_id'])
            item = QListWidgetItem(model['display_name'] + '\n' + model['health'] + ' · ' + model['health_reason']); item.setData(Qt.UserRole, model['model_id']); self.models.addItem(item)
        self.model.setCurrentIndex(max(0, self.model.findData(selected))); self.model.blockSignals(False)
        for widget, values in ((self.queue, self._snapshot['queue']), (self.history, self._snapshot['history'])):
            selected_id = widget.currentItem().data(Qt.UserRole) if widget.currentItem() else None; widget.clear()
            for row in values:
                identifier = row.get('generation_id') or row.get('id')
                item = QListWidgetItem(f"{row.get('status', '')} · {str(identifier)[:12]}\n{row.get('request', {}).get('prompt', '')[:100]}")
                item.setData(Qt.UserRole, identifier); widget.addItem(item)
                if identifier == selected_id: widget.setCurrentItem(item)
        self.details.setPlainText(json.dumps({key: self._snapshot[key] for key in ('hardware', 'settings', 'diagnostics', 'load_state')}, indent=2))
        self.policy.set_load(self._snapshot['load_state']); self.availability()

    def availability(self, *_):
        selected = next((row for row in self._snapshot.get('models', []) if row['model_id'] == self.model.currentData()), None)
        available = selected is not None and selected['enabled'] and self.intent.currentData() in selected['capabilities'] and selected['health'] in {'AVAILABLE', 'UNBENCHMARKED', 'DEGRADED'}
        self.run.setEnabled(available)
        self.run.setToolTip('' if available else 'Inspect a compatible local model. This workflow is unavailable without one.')

    def submit(self):
        try:
            common = dict(prompt=self.prompt.toPlainText().strip(), negative_prompt=self.negative.text(), model_id=self.model.currentData() or '',
                intent=self.intent.currentData(), width=self.width_input.value(), height=self.height_input.value(), steps=self.steps.value() or None,
                guidance=self.guidance.value(), seed=int(self.seed.text()), count=self.count.value(), quality=self.quality.currentData(),
                reference_images=tuple(self.references), mask=self.mask_path, strength=self.strength.value())
            video = self.intent.currentData() in {'TEXT_TO_VIDEO', 'IMAGE_TO_VIDEO'}
            request = VideoRequest(**common, frames=self.frames.value(), fps=self.fps.value()) if video else ImageRequest(**common, output_format=self.output_format.currentText())
            context = ExecutionContext(active_files=tuple(self.references + ([self.mask_path] if self.mask_path else [])))
        except (ValueError, TypeError) as exc: self.status.setText(str(exc)); return
        def submitted(value):
            self.current_generation = value; self.status.setText('Submitted to the existing media scheduler: ' + value[:12]); self.tabs.setCurrentIndex(1)
        # submit returns its future immediately; never wait for generation in a
        # general UI worker slot. MediaLab owns scheduling and resource waits.
        self.action('media-submit-request', lambda: self.lab.submit(request, context)[0], submitted)

    def cancel(self):
        item = self.queue.currentItem()
        if item:
            identifier = item.data(Qt.UserRole); self.action('media-cancel-request', lambda: self.lab.cancel(identifier))

    def import_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose reference', '', 'Images (*.png *.jpg *.jpeg *.webp)')
        if path: self.load_reference(path)

    def load_reference(self, path):
        try: require_selected_file(self.runtime, 'file_read')
        except PermissionError as exc: self.status.setText(str(exc)); return
        def ready(value):
            self.references = [str(Path(path).resolve())]; self.reference_metadata = value['metadata']; self.viewer.set_image(value)
            self.reference_label.setText(f"{Path(path).name} · {value['metadata']['width']} × {value['metadata']['height']}\nSupplied reference · SHA256 {value['metadata']['sha256'][:16]}")
        self.action('media-verify-reference', lambda: decoded_image(path), ready)

    def import_mask(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose inpaint mask', '', 'Images (*.png)')
        if not path: return
        try: require_selected_file(self.runtime, 'file_read')
        except PermissionError as exc: self.status.setText(str(exc)); return
        self.action('media-verify-mask', lambda: verify_image(path, allow_constant=True), lambda value: setattr(self, 'mask_path', value['path']))

    def open_history(self, item=None):
        if not isinstance(item, QListWidgetItem): item = self.history.currentItem()
        if item is None: return
        identifier = item.data(Qt.UserRole)
        def decode():
            artifact = self.lab.artifact(identifier)
            if artifact.get('frames'): raise ValueError('Use Tools → Media for local video playback; video generation requires an inspected provider.')
            return decoded_image(artifact['path'], artifact['sha256'])
        self.action('media-verified-preview', decode, lambda value: (self.viewer.set_image(value), self.tabs.setCurrentIndex(0), self.status.setText('Verified artifact · ' + identifier[:12])))

    def export(self):
        item = self.history.currentItem()
        if item is None: return
        identifier = item.data(Qt.UserRole); path, _ = QFileDialog.getSaveFileName(self, 'Export verified artifact')
        if path: self.action('media-export', lambda: self.lab.export(identifier, path, ExecutionContext(active_files=(str(Path(path).resolve()),))),
            self.export_completed)

    def export_completed(self, value):
        verified = value.success and value.verification is not None and value.verification.status == VerificationStatus.VERIFIED
        self.status.setText('Verified export completed.' if verified else '; '.join(error.message for error in value.errors) or 'Export was not authorized or verified.')

    def discover(self): self.action('media-discover-models', self.lab.discover)

    def inspect(self):
        item = self.models.currentItem()
        if item:
            identifier = item.data(Qt.UserRole); self.action('media-inspect-model', lambda: self.lab.inspect_model(identifier))

    def refresh_resources(self):
        self.action('media-read-hardware', lambda: (self.lab.hardware(refresh=True), self.lab.probe_encoder_tools()), priority='background')

    def runtime_event(self, event):
        if self.isVisible() and event['type'].startswith('media_'): self.refresh()

    def showEvent(self, event):
        self.refresh(); self.timer.start(); super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop(); super().hideEvent(event)

    def dispose(self): self.timer.stop()

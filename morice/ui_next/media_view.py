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
        self.current_generation = ''; self.reference_metadata = None; self._submitting = False
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
        self.model.currentIndexChanged.connect(self.availability); self.prompt.textChanged.connect(self.availability)
        self.generation_hint = QLabel(); self.generation_hint.setWordWrap(True); form.addRow(self.generation_hint)
        self.run = QPushButton('Generate'); self.run.setProperty('role', 'primary'); self.run.clicked.connect(self.submit); form.addRow(self.run)
        find_models = QPushButton('Find local models'); find_models.clicked.connect(self.discover); form.addRow(find_models)
        self.advanced_toggle = QPushButton('Advanced image / video settings'); self.advanced_toggle.setCheckable(True); form.addRow(self.advanced_toggle)
        self.advanced_settings = QWidget(); form.addRow(self.advanced_settings); self.advanced_settings.hide()
        self.advanced_toggle.toggled.connect(self.advanced_settings.setVisible)
        main_form = form; form = QFormLayout(self.advanced_settings); form.setContentsMargins(0, 0, 0, 0); form.setRowWrapPolicy(QFormLayout.WrapAllRows)
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
        form = main_form
        self.edit_options = QPushButton('Reference / edit options (optional)'); self.edit_options.setCheckable(True); form.addRow(self.edit_options)
        self.reference_options = QWidget(); reference_form = QVBoxLayout(self.reference_options); reference_form.setContentsMargins(0, 0, 0, 0)
        self.reference_button = QPushButton('Choose reference image (optional for creating images)'); self.reference_button.clicked.connect(self.import_reference); reference_form.addWidget(self.reference_button)
        self.mask_button = QPushButton('Choose mask (inpainting only)'); self.mask_button.clicked.connect(self.import_mask); reference_form.addWidget(self.mask_button)
        clear = QPushButton('Clear reference and mask'); clear.clicked.connect(self.clear_reference); reference_form.addWidget(clear)
        form.addRow(self.reference_options); self.reference_options.hide()
        self.edit_options.toggled.connect(self.reference_options.setVisible)
        self.reference_label = QLabel('Create an image from your prompt. No reference image or mask is required.'); self.reference_label.setWordWrap(True); form.addRow(self.reference_label)
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
        selected = getattr(self, '_preferred_model', '') or self.model.currentData(); self._preferred_model = ''
        self.model.blockSignals(True); self.model.clear(); self.models.clear()
        for model in self._snapshot['models']:
            self.model.addItem(model['display_name'] + ' · ' + model['health'], model['model_id'])
            item = QListWidgetItem(model['display_name'] + '\n' + model['health'] + ' · ' + model['health_reason']); item.setData(Qt.UserRole, model['model_id']); self.models.addItem(item)
        index = self.model.findData(selected)
        if index < 0:
            compatible = [row for row in self._snapshot['models'] if row['enabled'] and self.intent.currentData() in row['capabilities']]
            compatible.sort(key=lambda row: row['health'] not in {'AVAILABLE','UNBENCHMARKED','DEGRADED'})
            index = self.model.findData(compatible[0]['model_id']) if compatible else 0
        self.model.setCurrentIndex(index); self.model.blockSignals(False)
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
        if not hasattr(self, 'run'): return
        selected = next((row for row in self._snapshot.get('models', []) if row['model_id'] == self.model.currentData()), None)
        intent = self.intent.currentData(); edit = intent in {'IMAGE_TO_IMAGE','INPAINT','OUTPAINT','IMAGE_UPSCALE','IMAGE_TO_VIDEO'}
        if edit: self.edit_options.setChecked(True)
        self.mask_button.setVisible(intent == 'INPAINT')
        if self._submitting: reason = 'Checking model files and submitting this request…'
        elif not selected: reason = 'Choose Find local models. Generation needs installed model weights, not a reference image.' if intent == 'TEXT_TO_IMAGE' else 'This workflow is unavailable until a compatible model is installed and selected. Choose Find local models.'
        elif not selected['enabled']: reason = 'This model is disabled. Enable a compatible model in Models / resources.'
        elif intent not in selected['capabilities']: reason = 'Choose an image model supporting prompt-to-image.' if intent == 'TEXT_TO_IMAGE' else 'This model does not support this workflow. Select a compatible model.'
        elif selected['health'] not in {'AVAILABLE','UNBENCHMARKED','DEGRADED','DISCOVERED'}: reason = selected.get('health_reason') or 'Inspect a compatible model in Models / resources.'
        elif not self.prompt.toPlainText().strip(): reason = 'Describe an image and press Generate. No reference or mask is needed.' if intent == 'TEXT_TO_IMAGE' else 'Enter a prompt for this workflow.'
        elif edit and not self.references: reason = 'This edit workflow needs an existing image. Choose Generate image to create from a prompt alone.'
        elif intent == 'INPAINT' and not self.mask_path: reason = 'Choose a mask for inpainting, or Generate image to create without one.'
        else: reason = ''
        self.run.setEnabled(not reason); self.run.setToolTip(reason)
        self.generation_hint.setText(reason or ('Ready: prompt only. Model files are checked before generation.' if intent == 'TEXT_TO_IMAGE' else 'Ready to submit this workflow.'))
        self.reference_label.setVisible(edit)
        if not edit: self.reference_label.setText('Prompt-only generation: reference image and mask are not used.')

    def submit(self):
        if self._submitting: return
        try:
            common = dict(prompt=self.prompt.toPlainText().strip(), negative_prompt=self.negative.text(), model_id=self.model.currentData() or '',
                intent=self.intent.currentData(), width=self.width_input.value(), height=self.height_input.value(), steps=self.steps.value() or None,
                guidance=self.guidance.value(), seed=int(self.seed.text()), count=self.count.value(), quality=self.quality.currentData(),
                reference_images=tuple(self.references) if self.intent.currentData() not in {'TEXT_TO_IMAGE','TEXT_TO_VIDEO'} else (),
                mask=self.mask_path if self.intent.currentData() == 'INPAINT' else '', strength=self.strength.value())
            video = self.intent.currentData() in {'TEXT_TO_VIDEO', 'IMAGE_TO_VIDEO'}
            request = VideoRequest(**common, frames=self.frames.value(), fps=self.fps.value()) if video else ImageRequest(**common, output_format=self.output_format.currentText())
            context = ExecutionContext(active_files=tuple(request.reference_images) + ((request.mask,) if request.mask else ()))
        except (ValueError, TypeError) as exc: self.status.setText(str(exc)); return
        def submitted(value):
            self.current_generation = value; self.status.setText('Submitted to the existing media scheduler: ' + value[:12]); self.tabs.setCurrentIndex(1)
        # submit returns its future immediately; never wait for generation in a
        # general UI worker slot. MediaLab owns scheduling and resource waits.
        def prepare_and_submit():
            model = self.lab.models.get(request.model_id) if request.model_id else self.lab.select_model(request)
            if str(getattr(model.health, 'value', model.health)) == 'DISCOVERED':
                model = self.lab.inspect_model(model.model_id)
                if str(getattr(model.health, 'value', model.health)) not in {'AVAILABLE','UNBENCHMARKED','DEGRADED'}:
                    raise ValueError(model.health_reason or 'Model inspection did not pass.')
            return self.lab.submit(request, context)[0]
        def finished(envelope):
            self._submitting = False
            if envelope['ok']: submitted(envelope['value'])
            else: self.status.setText(envelope['error'])
            self.refresh(); self.availability()
        self._submitting = True; self.availability()
        try: self.bridge.submit('media-submit-request', prepare_and_submit, finished)
        except (ValueError, RuntimeError) as exc:
            self._submitting = False; self.status.setText(str(exc)); self.availability()

    def clear_reference(self):
        self.references = []; self.mask_path = ''; self.reference_metadata = None
        self.reference_label.setText('No reference selected. Generate image works from the prompt alone.')
        self.intent.setCurrentIndex(self.intent.findData('TEXT_TO_IMAGE')); self.edit_options.setChecked(False); self.availability()

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
            if self.intent.currentData() == 'TEXT_TO_IMAGE': self.intent.setCurrentIndex(self.intent.findData('IMAGE_TO_IMAGE'))
            self.reference_label.setText(f"{Path(path).name} · {value['metadata']['width']} × {value['metadata']['height']}\nSupplied reference · SHA256 {value['metadata']['sha256'][:16]}")
            self.availability()
        self.action('media-verify-reference', lambda: decoded_image(path), ready)

    def import_mask(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose inpaint mask', '', 'Images (*.png)')
        if not path: return
        try: require_selected_file(self.runtime, 'file_read')
        except PermissionError as exc: self.status.setText(str(exc)); return
        def ready(value):
            self.mask_path = value['path']; self.availability()
        self.action('media-verify-mask', lambda: verify_image(path, allow_constant=True), ready)

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

    def discover(self):
        def found(models):
            eligible = [model for model in models if 'TEXT_TO_IMAGE' in model.capabilities]
            if eligible: self._preferred_model = eligible[0].model_id
            self.status.setText(f'Found {len(models)} model bundle(s). Select a compatible model; no reference image is required for Generate image.')
        self.action('media-discover-models', self.lab.discover, found)

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

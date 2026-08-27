from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .live_camera import CameraOption


class CameraPreview(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._image = QImage()
        self._regions: tuple[object, ...] = ()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(480, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setText("Camera off\nPress Turn camera on when you want MORICE to see.")
        self.setObjectName("LiveCameraPreview")

    def set_frame(self, image: QImage) -> None:
        self._image = image.copy()
        self._render()

    def clear_frame(self, message: str) -> None:
        self._image = QImage()
        self._regions = ()
        self.clear()
        self.setText(message)

    def set_regions(self, regions: tuple[object, ...]) -> None:
        self._regions = tuple(regions or ())
        self._render()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._render()

    def _render(self) -> None:
        if self._image.isNull():
            return
        pixmap = QPixmap.fromImage(self._image)
        rendered = pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        if self._regions:
            painter = QPainter(rendered)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(QPen(QColor("#62f5d2"), 3))
            painter.setBrush(QColor(98, 245, 210, 28))
            for region in self._regions:
                try:
                    x = float(getattr(region, "x")) * rendered.width()
                    y = float(getattr(region, "y")) * rendered.height()
                    width = float(getattr(region, "width")) * rendered.width()
                    height = float(getattr(region, "height")) * rendered.height()
                    label = str(getattr(region, "label", ""))
                except (TypeError, ValueError):
                    continue
                painter.drawRoundedRect(int(x), int(y), int(width), int(height), 6, 6)
                if label:
                    painter.fillRect(int(x), max(0, int(y) - 23), max(70, len(label) * 8), 23, QColor(5, 30, 32, 220))
                    painter.drawText(int(x) + 6, max(17, int(y) - 6), label[:60])
            painter.end()
        self.setPixmap(rendered)


class GlassResponseOverlay(QFrame):
    copyRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("LiveGlassOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._pinned = False
        self._streaming = False
        self._text = ""
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._animation = QPropertyAnimation(self._opacity, b"opacity", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.state_label = QLabel("MORICE · READY")
        self.state_label.setObjectName("LiveGlassState")
        self.pin_button = QPushButton("Pin")
        self.pin_button.setObjectName("LiveGlassButton")
        self.pin_button.setCheckable(True)
        self.pin_button.toggled.connect(self._set_pinned)
        self.copy_button = QPushButton("Copy")
        self.copy_button.setObjectName("LiveGlassButton")
        self.copy_button.clicked.connect(lambda: self.copyRequested.emit(self._text))
        header.addWidget(self.state_label, stretch=1)
        header.addWidget(self.copy_button)
        header.addWidget(self.pin_button)
        self.response_label = QLabel("Live Action is ready.")
        self.response_label.setObjectName("LiveGlassResponse")
        self.response_label.setWordWrap(True)
        self.response_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addLayout(header)
        layout.addWidget(self.response_label)
        self.setVisible(False)

    @property
    def pinned(self) -> bool:
        return self._pinned

    def set_response(self, text: str, *, streaming: bool = False, state: str = "MORICE") -> None:
        clean = str(text or "").strip()
        self._text = clean
        self._streaming = bool(streaming)
        self.state_label.setText(f"{state.upper()} · {'RESPONDING' if streaming else 'READY'}")
        self.response_label.setText(clean or "…")
        self._show_animated()

    def set_status(self, text: str, *, state: str = "VISION") -> None:
        self.set_response(text, streaming=True, state=state)

    def finish_stream(self, text: str = "") -> None:
        if text.strip():
            self._text = text.strip()
            self.response_label.setText(self._text)
        self._streaming = False
        self.state_label.setText("MORICE · READY")

    def dismiss(self) -> None:
        if self._pinned:
            return
        self._animation.stop()
        self._animation.setStartValue(self._opacity.opacity())
        self._animation.setEndValue(0.0)
        self._animation.finished.connect(self._hide_after_fade)
        self._animation.start()

    def _show_animated(self) -> None:
        self.setVisible(True)
        self.raise_()
        self._animation.stop()
        self._animation.setStartValue(self._opacity.opacity())
        self._animation.setEndValue(1.0)
        self._animation.start()

    def _hide_after_fade(self) -> None:
        if self._opacity.opacity() <= 0.01 and not self._pinned:
            self.setVisible(False)

    def _set_pinned(self, pinned: bool) -> None:
        self._pinned = bool(pinned)
        self.pin_button.setText("Pinned" if pinned else "Pin")


class LiveActionWorkspace(QWidget):
    cameraRequested = Signal(bool)
    cameraConfigurationChanged = Signal(str, str, float, bool)
    awarenessRequested = Signal(bool)
    microphoneRequested = Signal(bool)
    textSubmitted = Signal(str)
    analyzeRequested = Signal()
    exitRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("LiveActionWorkspace")
        self._camera_active = False
        self._microphone_active = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("LIVE ACTION")
        title.setObjectName("LiveActionTitle")
        subtitle = QLabel("Voice + vision + tools + project capabilities")
        subtitle.setObjectName("LiveActionSubtitle")
        self.privacy_label = QLabel("● CAMERA OFF · no frames stored")
        self.privacy_label.setObjectName("LivePrivacyStatus")
        exit_button = QPushButton("Exit Live Action")
        exit_button.setObjectName("LiveExitButton")
        exit_button.clicked.connect(self.exitRequested)
        title_row.addWidget(title)
        title_row.addWidget(subtitle, stretch=1)
        title_row.addWidget(self.privacy_label)
        title_row.addWidget(exit_button)
        root.addLayout(title_row)

        control_row = QHBoxLayout()
        control_row.setSpacing(8)
        self.device_select = QComboBox()
        self.device_select.setObjectName("LiveControl")
        self.device_select.setMinimumWidth(180)
        self.resolution_select = QComboBox()
        self.resolution_select.setObjectName("LiveControl")
        self.fps_select = QComboBox()
        self.fps_select.setObjectName("LiveControl")
        for fps in (15, 24, 30, 60):
            self.fps_select.addItem(f"{fps} FPS", fps)
        self.fps_select.setCurrentIndex(2)
        self.mirror_check = QCheckBox("Mirror")
        self.mirror_check.setChecked(True)
        self.mirror_check.setObjectName("LiveMirror")
        self.awareness_check = QCheckBox("Scene awareness")
        self.awareness_check.setChecked(False)
        self.awareness_check.setToolTip(
            "Track lightweight scene changes in memory; this does not run the visual LLM continuously."
        )
        self.awareness_check.setObjectName("LiveMirror")
        self.awareness_check.toggled.connect(self.awarenessRequested)
        self.camera_button = QPushButton("Turn camera on")
        self.camera_button.setObjectName("LivePrimaryControl")
        self.camera_button.clicked.connect(self._toggle_camera)
        self.mic_button = QPushButton("Pause microphone")
        self.mic_button.setObjectName("LiveControl")
        self.mic_button.clicked.connect(self._toggle_microphone)
        analyze_button = QPushButton("Analyze view")
        analyze_button.setObjectName("LiveControl")
        analyze_button.clicked.connect(self.analyzeRequested)
        for widget in (self.device_select, self.resolution_select, self.fps_select):
            widget.currentIndexChanged.connect(self._configuration_changed)
        self.mirror_check.toggled.connect(self._configuration_changed)
        control_row.addWidget(self.device_select, stretch=1)
        control_row.addWidget(self.resolution_select)
        control_row.addWidget(self.fps_select)
        control_row.addWidget(self.mirror_check)
        control_row.addWidget(self.awareness_check)
        control_row.addWidget(self.camera_button)
        control_row.addWidget(self.mic_button)
        control_row.addWidget(analyze_button)
        root.addLayout(control_row)

        self.stage = QFrame()
        self.stage.setObjectName("LiveCameraStage")
        self.stage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        stage_layout = QVBoxLayout(self.stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        self.preview = CameraPreview()
        stage_layout.addWidget(self.preview)
        self.overlay = GlassResponseOverlay(self.stage)
        self.overlay.copyRequested.connect(self.copyRequested)
        root.addWidget(self.stage, stretch=1)

        self.transcript_label = QLabel("Listening for your voice…")
        self.transcript_label.setObjectName("LiveTranscript")
        self.transcript_label.setWordWrap(True)
        root.addWidget(self.transcript_label)

        composer_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setObjectName("LiveActionInput")
        self.input.setPlaceholderText("Type here too — all normal chat and project features remain available")
        self.input.returnPressed.connect(self._submit_text)
        send_button = QPushButton("Send")
        send_button.setObjectName("LivePrimaryControl")
        send_button.clicked.connect(self._submit_text)
        composer_row.addWidget(self.input, stretch=1)
        composer_row.addWidget(send_button)
        root.addLayout(composer_row)
        self.setStyleSheet(self._stylesheet())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        margin = 22
        width = max(300, min(self.stage.width() - margin * 2, 860))
        height = max(120, min(240, self.overlay.sizeHint().height()))
        self.overlay.setGeometry(
            max(margin, (self.stage.width() - width) // 2),
            max(margin, self.stage.height() - height - margin),
            width,
            height,
        )

    def set_devices(self, options: tuple[CameraOption, ...]) -> None:
        selected = self.device_select.currentData()
        self.device_select.blockSignals(True)
        self.device_select.clear()
        for option in options:
            label = option.description + (" · Default" if option.is_default else "")
            self.device_select.addItem(label, option.device_id)
            self.device_select.setItemData(self.device_select.count() - 1, option, Qt.UserRole + 1)
        if selected:
            index = self.device_select.findData(selected)
            if index >= 0:
                self.device_select.setCurrentIndex(index)
        self.device_select.blockSignals(False)
        self._refresh_resolutions()

    def selected_configuration(self) -> tuple[str, str, float, bool]:
        resolution = str(self.resolution_select.currentData() or "1280x720")
        return (
            str(self.device_select.currentData() or ""),
            resolution,
            float(self.fps_select.currentData() or 30),
            self.mirror_check.isChecked(),
        )

    def apply_preferences(
        self,
        *,
        device_id: str = "",
        resolution: str = "1280x720",
        fps: float = 30.0,
        mirror: bool = True,
        continuous_awareness: bool = False,
    ) -> None:
        self.device_select.blockSignals(True)
        if device_id:
            index = self.device_select.findData(device_id)
            if index >= 0:
                self.device_select.setCurrentIndex(index)
        self.device_select.blockSignals(False)
        self._refresh_resolutions()
        resolution_index = self.resolution_select.findData(str(resolution))
        if resolution_index >= 0:
            self.resolution_select.setCurrentIndex(resolution_index)
        fps_index = self.fps_select.findData(int(round(float(fps))))
        if fps_index >= 0:
            self.fps_select.setCurrentIndex(fps_index)
        self.mirror_check.setChecked(bool(mirror))
        self.awareness_check.setChecked(bool(continuous_awareness))

    def set_camera_state(self, state: str, message: str) -> None:
        active = state == "active"
        self._camera_active = active
        self.camera_button.setText("Turn camera off" if active else "Turn camera on")
        self.privacy_label.setText(
            "● CAMERA LIVE · memory only" if active else "● CAMERA OFF · no frames stored"
        )
        if not active and state in {"off", "unavailable", "error"}:
            self.preview.clear_frame(message)
        if state in {"unavailable", "error"}:
            self.overlay.set_status(message, state="camera")

    def set_microphone_state(self, active: bool, message: str = "") -> None:
        self._microphone_active = bool(active)
        self.mic_button.setText("Pause microphone" if active else "Resume microphone")
        if message:
            self.transcript_label.setText(message)

    def set_transcript(self, text: str, *, partial: bool = False) -> None:
        clean = str(text or "").strip()
        if clean:
            prefix = "Hearing" if partial else "You said"
            self.transcript_label.setText(f"{prefix}: {clean}")

    def show_response(self, text: str, *, streaming: bool = False, state: str = "MORICE") -> None:
        self.overlay.set_response(text, streaming=streaming, state=state)
        margin = 22
        width = max(300, min(self.stage.width() - margin * 2, 860))
        height = max(120, min(240, self.overlay.sizeHint().height()))
        self.overlay.setGeometry(
            max(margin, (self.stage.width() - width) // 2),
            max(margin, self.stage.height() - height - margin),
            width,
            height,
        )

    def finish_response(self, text: str = "") -> None:
        self.overlay.finish_stream(text)

    def set_regions(self, regions: tuple[object, ...]) -> None:
        self.preview.set_regions(regions)

    def copyRequested(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(str(text or ""))

    def _toggle_camera(self) -> None:
        self.cameraRequested.emit(not self._camera_active)

    def _toggle_microphone(self) -> None:
        self.microphoneRequested.emit(not self._microphone_active)

    def _configuration_changed(self, *_args: object) -> None:
        if self.sender() is self.device_select:
            self._refresh_resolutions()
        self.cameraConfigurationChanged.emit(*self.selected_configuration())

    def _refresh_resolutions(self) -> None:
        option = self.device_select.currentData(Qt.UserRole + 1)
        selected = str(self.resolution_select.currentData() or "1280x720")
        values: set[str] = set()
        if isinstance(option, CameraOption):
            values = {f"{width}x{height}" for width, height, _minimum, _maximum in option.formats}
        if not values:
            values = {"640x480", "1280x720", "1920x1080"}
        ordered = sorted(values, key=lambda value: int(value.split("x")[0]) * int(value.split("x")[1]))
        self.resolution_select.blockSignals(True)
        self.resolution_select.clear()
        for value in ordered:
            self.resolution_select.addItem(value, value)
        index = self.resolution_select.findData(selected)
        if index < 0:
            index = self.resolution_select.findData("1280x720")
        self.resolution_select.setCurrentIndex(max(0, index))
        self.resolution_select.blockSignals(False)

    def _submit_text(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.textSubmitted.emit(text)

    @staticmethod
    def _stylesheet() -> str:
        return """
        #LiveActionWorkspace { background: rgba(5, 13, 23, 220); border-radius: 16px; }
        #LiveActionTitle { color: #62f5d2; font-size: 17px; font-weight: 800; letter-spacing: 2px; }
        #LiveActionSubtitle, #LivePrivacyStatus { color: #9fb2c6; }
        #LiveCameraStage { background: #030912; border: 1px solid rgba(92, 236, 204, 90); border-radius: 18px; }
        #LiveCameraPreview { color: #8fa4b8; font-size: 16px; background: #02070d; border-radius: 18px; }
        #LiveGlassOverlay { background: rgba(10, 25, 39, 220); border: 1px solid rgba(99, 246, 215, 160); border-radius: 18px; }
        #LiveGlassState { color: #62f5d2; font-weight: 800; letter-spacing: 1px; }
        #LiveGlassResponse { color: #f3f8fb; font-size: 16px; }
        #LiveGlassButton, #LiveControl, #LiveExitButton, #LiveMirror { color: #d8e7ef; background: rgba(24, 48, 67, 210); border: 1px solid #355873; border-radius: 9px; padding: 7px 10px; }
        #LivePrimaryControl { color: #06130f; background: #62f5d2; border: none; border-radius: 9px; padding: 8px 13px; font-weight: 800; }
        #LiveTranscript { color: #b8c9d8; background: rgba(13, 31, 46, 180); border-radius: 10px; padding: 8px 12px; }
        #LiveActionInput { color: #eef7fb; background: rgba(10, 25, 39, 230); border: 1px solid #31536d; border-radius: 11px; padding: 11px 13px; }
        """

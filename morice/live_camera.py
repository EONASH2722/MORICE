from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import (
    QCamera,
    QCameraDevice,
    QCameraFormat,
    QMediaCaptureSession,
    QMediaDevices,
    QVideoFrame,
    QVideoSink,
)


@dataclass(frozen=True)
class CameraOption:
    device_id: str
    description: str
    is_default: bool
    formats: tuple[tuple[int, int, float, float], ...]


def encode_device_id(device: QCameraDevice) -> str:
    return bytes(device.id().toBase64()).decode("ascii", errors="ignore")


def format_resolution(value: tuple[int, int]) -> str:
    return f"{max(0, int(value[0]))}x{max(0, int(value[1]))}"


def parse_resolution(value: str, *, fallback: tuple[int, int] = (1280, 720)) -> tuple[int, int]:
    try:
        width_text, height_text = str(value or "").casefold().replace(" ", "").split("x", 1)
        width = int(width_text)
        height = int(height_text)
    except (TypeError, ValueError):
        return fallback
    if width < 1 or height < 1:
        return fallback
    return width, height


def choose_camera_format(
    formats: list[QCameraFormat] | tuple[QCameraFormat, ...],
    resolution: tuple[int, int],
    fps: float,
) -> QCameraFormat | None:
    if not formats:
        return None
    target_width, target_height = resolution
    target_fps = max(1.0, float(fps))

    def score(camera_format: QCameraFormat) -> tuple[float, float, float]:
        size = camera_format.resolution()
        pixels = max(1, size.width() * size.height())
        target_pixels = max(1, target_width * target_height)
        resolution_error = abs(size.width() - target_width) + abs(size.height() - target_height)
        ratio_error = abs((size.width() / max(1, size.height())) - (target_width / max(1, target_height)))
        if camera_format.minFrameRate() <= target_fps <= camera_format.maxFrameRate():
            fps_error = 0.0
        else:
            fps_error = min(
                abs(camera_format.minFrameRate() - target_fps),
                abs(camera_format.maxFrameRate() - target_fps),
            )
        return (
            resolution_error + ratio_error * 1000.0,
            fps_error * 100.0,
            abs(pixels - target_pixels) / target_pixels,
        )

    return min(formats, key=score)


class LiveCameraController(QObject):
    """Own a permission-first, memory-only Qt camera preview."""

    frameReady = Signal(object)
    devicesChanged = Signal(object)
    stateChanged = Signal(str, str)
    diagnosticsChanged = Signal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._media_devices = QMediaDevices(self)
        self._media_devices.videoInputsChanged.connect(self.refresh_devices)
        self._capture_session: QMediaCaptureSession | None = None
        self._camera: QCamera | None = None
        self._sink: QVideoSink | None = None
        self._latest_image = QImage()
        self._desired_active = False
        self._mirror = True
        self._current_device_id = ""
        self._current_resolution = ""
        self._current_fps = 0.0
        self._frame_times: deque[float] = deque(maxlen=120)
        self._frames_received = 0
        self._conversion_failures = 0
        self._reconnect_attempts = 0
        self._state = "off"
        self._message = "Camera is off."
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._retry_start)
        self.refresh_devices()

    @property
    def active(self) -> bool:
        return bool(self._camera is not None and self._camera.isActive())

    @property
    def desired_active(self) -> bool:
        return self._desired_active

    def options(self) -> tuple[CameraOption, ...]:
        result: list[CameraOption] = []
        for device in QMediaDevices.videoInputs():
            formats: list[tuple[int, int, float, float]] = []
            for camera_format in device.videoFormats():
                size = camera_format.resolution()
                formats.append(
                    (
                        size.width(),
                        size.height(),
                        float(camera_format.minFrameRate()),
                        float(camera_format.maxFrameRate()),
                    )
                )
            result.append(
                CameraOption(
                    encode_device_id(device),
                    device.description(),
                    device.isDefault(),
                    tuple(formats),
                )
            )
        return tuple(result)

    def refresh_devices(self) -> None:
        options = self.options()
        self.devicesChanged.emit(options)
        if self._desired_active and self._current_device_id:
            available = {option.device_id for option in options}
            if self._current_device_id not in available:
                self._set_state("unavailable", "Selected camera is unavailable. Reconnecting…")
                self._schedule_reconnect()

    def start(
        self,
        *,
        device_id: str = "",
        resolution: str = "1280x720",
        fps: float = 30.0,
        mirror: bool = True,
    ) -> bool:
        self._desired_active = True
        self._mirror = bool(mirror)
        self._current_device_id = str(device_id or "")
        self._current_resolution = format_resolution(parse_resolution(resolution))
        self._current_fps = max(5.0, min(120.0, float(fps)))
        self._reconnect_timer.stop()
        self._teardown_camera(clear_desired=False)
        inputs = list(QMediaDevices.videoInputs())
        if not inputs:
            self._set_state("unavailable", "No camera was found. Check Windows camera privacy settings.")
            return False
        device = next(
            (item for item in inputs if encode_device_id(item) == self._current_device_id),
            next((item for item in inputs if item.isDefault()), inputs[0]),
        )
        self._current_device_id = encode_device_id(device)
        camera = QCamera(device, self)
        selected_format = choose_camera_format(
            list(device.videoFormats()),
            parse_resolution(self._current_resolution),
            self._current_fps,
        )
        if selected_format is not None:
            camera.setCameraFormat(selected_format)
            size = selected_format.resolution()
            self._current_resolution = f"{size.width()}x{size.height()}"
            self._current_fps = min(
                max(self._current_fps, selected_format.minFrameRate()),
                selected_format.maxFrameRate(),
            )
        session = QMediaCaptureSession(self)
        sink = QVideoSink(self)
        session.setCamera(camera)
        session.setVideoOutput(sink)
        sink.videoFrameChanged.connect(self._on_video_frame)
        camera.activeChanged.connect(self._on_active_changed)
        camera.errorOccurred.connect(self._on_camera_error)
        self._camera = camera
        self._capture_session = session
        self._sink = sink
        self._set_state("starting", f"Requesting access to {device.description()}…")
        camera.start()
        return True

    def update_mirror(self, enabled: bool) -> None:
        self._mirror = bool(enabled)
        if not self._latest_image.isNull():
            self.frameReady.emit(self.latest_image())

    def stop(self, reason: str = "Camera is off.") -> None:
        self._reconnect_timer.stop()
        self._teardown_camera(clear_desired=True)
        self._set_state("off", reason)

    def latest_image(self) -> QImage:
        if self._latest_image.isNull():
            return QImage()
        image = self._latest_image.copy()
        return image.mirrored(True, False) if self._mirror else image

    def snapshot_jpeg(self, *, quality: int = 88) -> tuple[bytes, dict[str, Any]] | None:
        image = self.latest_image()
        if image.isNull():
            return None
        payload = QByteArray()
        buffer = QBuffer(payload)
        if not buffer.open(QIODevice.WriteOnly):
            return None
        try:
            if not image.save(buffer, "JPG", max(50, min(95, int(quality)))):
                return None
        finally:
            buffer.close()
        return bytes(payload), {
            "width": image.width(),
            "height": image.height(),
            "camera_id": self._current_device_id,
            "mirrored": self._mirror,
        }

    def diagnostics(self) -> dict[str, Any]:
        now = time.monotonic()
        recent = [stamp for stamp in self._frame_times if now - stamp <= 1.0]
        return {
            "state": self._state,
            "message": self._message,
            "active": self.active,
            "permissionRequested": self._desired_active,
            "deviceId": self._current_device_id,
            "resolution": self._current_resolution,
            "targetFps": round(self._current_fps, 2),
            "previewFps": len(recent),
            "framesReceived": self._frames_received,
            "conversionFailures": self._conversion_failures,
            "reconnectAttempts": self._reconnect_attempts,
            "rawFramesStored": False,
        }

    def shutdown(self) -> None:
        self.stop("Camera shut down.")

    def _on_video_frame(self, frame: QVideoFrame) -> None:
        # QVideoSink can have a frame delivery queued while the camera is
        # being torn down.  Reject that late delivery so turning the camera
        # off cannot repopulate either the memory snapshot or the preview.
        if not self._desired_active or self.sender() is not self._sink:
            return
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            self._conversion_failures += 1
            return
        self._latest_image = image.copy()
        now = time.monotonic()
        self._frame_times.append(now)
        self._frames_received += 1
        self.frameReady.emit(self.latest_image())
        if self._frames_received % 15 == 0:
            self.diagnosticsChanged.emit(self.diagnostics())

    def _on_active_changed(self, active: bool) -> None:
        if self.sender() is not self._camera:
            return
        if active:
            self._reconnect_attempts = 0
            self._set_state("active", "Camera live · frames stay in memory only")
        elif self._desired_active:
            self._set_state("unavailable", "Camera stopped unexpectedly. Reconnecting…")
            self._schedule_reconnect()

    def _on_camera_error(self, *args: object) -> None:
        if self.sender() is not self._camera:
            return
        error_text = self._camera.errorString().strip() if self._camera is not None else ""
        self._set_state(
            "error",
            error_text or "Camera access failed. Check Windows camera privacy settings.",
        )
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        if not self._desired_active or self._reconnect_timer.isActive():
            return
        self._reconnect_attempts += 1
        delay = min(8000, 750 * (2 ** min(3, self._reconnect_attempts - 1)))
        self._reconnect_timer.start(delay)

    def _retry_start(self) -> None:
        if not self._desired_active:
            return
        self.start(
            device_id=self._current_device_id,
            resolution=self._current_resolution or "1280x720",
            fps=self._current_fps or 30.0,
            mirror=self._mirror,
        )

    def _teardown_camera(self, *, clear_desired: bool) -> None:
        if clear_desired:
            self._desired_active = False
        camera = self._camera
        sink = self._sink
        session = self._capture_session
        self._camera = None
        self._sink = None
        self._capture_session = None
        if camera is not None:
            try:
                camera.stop()
            except RuntimeError:
                pass
            camera.deleteLater()
        if sink is not None:
            sink.deleteLater()
        if session is not None:
            session.deleteLater()
        self._latest_image = QImage()
        self._frame_times.clear()

    def _set_state(self, state: str, message: str) -> None:
        self._state = str(state)
        self._message = str(message)
        self.stateChanged.emit(self._state, self._message)
        self.diagnosticsChanged.emit(self.diagnostics())

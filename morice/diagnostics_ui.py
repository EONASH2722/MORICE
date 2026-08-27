from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl

from .runtime_services import RuntimeServices, RuntimeSnapshot, StructuredLogRecord


class MetricsGraph(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DiagnosticsMetricsGraph")
        self.setMinimumHeight(220)
        self._samples: list[Any] = []

    def set_samples(self, samples: list[Any]) -> None:
        self._samples = list(samples)[-180:]
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(7, 12, 19, 235))
        bounds = self.rect().adjusted(42, 20, -18, -34)
        if bounds.width() <= 10 or bounds.height() <= 10:
            return
        grid_pen = QPen(QColor(100, 130, 160, 52), 1)
        painter.setPen(grid_pen)
        for index in range(5):
            y = bounds.top() + index * bounds.height() / 4
            painter.drawLine(bounds.left(), int(y), bounds.right(), int(y))
        painter.setPen(QColor(174, 196, 220))
        painter.drawText(8, bounds.top() + 5, "100")
        painter.drawText(18, bounds.center().y() + 5, "50")
        painter.drawText(24, bounds.bottom() + 5, "0")
        painter.drawText(bounds.left(), self.height() - 8, "Recent runtime samples")
        if len(self._samples) < 2:
            painter.drawText(bounds, Qt.AlignCenter, "Waiting for runtime samples...")
            return

        def draw_series(values: list[float], color: QColor, scale: float = 100.0) -> None:
            path = QPainterPath()
            for index, value in enumerate(values):
                x = bounds.left() + index * bounds.width() / max(1, len(values) - 1)
                normalized = min(1.0, max(0.0, value / scale))
                y = bounds.bottom() - normalized * bounds.height()
                if index == 0:
                    path.moveTo(QPointF(x, y))
                else:
                    path.lineTo(QPointF(x, y))
            painter.setPen(QPen(color, 2))
            painter.drawPath(path)

        draw_series([sample.cpu_percent for sample in self._samples], QColor("#56d7ff"))
        gpu_values = [
            sample.gpu_percent if sample.gpu_percent is not None else 0.0
            for sample in self._samples
        ]
        if any(sample.gpu_percent is not None for sample in self._samples):
            draw_series(gpu_values, QColor("#f0c95a"))
        memory_values = [sample.memory_mb for sample in self._samples]
        memory_scale = max(512.0, max(memory_values, default=0.0) * 1.15)
        draw_series(memory_values, QColor("#70e0a9"), memory_scale)
        fps_values = [min(100.0, sample.fps) for sample in self._samples]
        draw_series(fps_values, QColor("#c68cff"))
        painter.setPen(QColor("#56d7ff"))
        painter.drawText(bounds.right() - 300, 14, "CPU")
        painter.setPen(QColor("#f0c95a"))
        painter.drawText(bounds.right() - 250, 14, "GPU")
        painter.setPen(QColor("#70e0a9"))
        painter.drawText(bounds.right() - 190, 14, "Memory")
        painter.setPen(QColor("#c68cff"))
        painter.drawText(bounds.right() - 105, 14, "FPS")


class DiagnosticsDialog(QDialog):
    def __init__(
        self,
        runtime: RuntimeServices,
        context_provider: Callable[[], dict[str, Any]],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.runtime = runtime
        self.context_provider = context_provider
        self.last_snapshot: RuntimeSnapshot | None = None
        self.setObjectName("DiagnosticsDialog")
        self.setWindowTitle("MORICE Diagnostics")
        self.setMinimumSize(900, 640)
        self.resize(1080, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        header = QHBoxLayout()
        title = QLabel("MORICE Diagnostics")
        title.setObjectName("DiagnosticsTitle")
        self.status = QLabel("Collecting runtime status...")
        self.status.setObjectName("DiagnosticsStatus")
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.open_logs_button = QPushButton("Open logs")
        self.open_logs_button.clicked.connect(self._open_logs)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        header.addWidget(title)
        header.addWidget(self.status, stretch=1)
        header.addWidget(self.refresh_button)
        header.addWidget(self.open_logs_button)
        header.addWidget(close_button)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.overview_page = self._build_overview()
        self.health_page = self._build_health()
        self.logs_page = self._build_logs()
        self.performance_page = self._build_performance()
        self.agent_page = self._build_agent()
        self.components_page = self._build_components()
        self.voice_page = self._build_voice()
        self.tabs.addTab(self.overview_page, "Overview")
        self.tabs.addTab(self.health_page, "Health")
        self.tabs.addTab(self.logs_page, "Logs")
        self.tabs.addTab(self.performance_page, "Performance")
        self.tabs.addTab(self.agent_page, "Agent")
        self.tabs.addTab(self.components_page, "Components")
        self.tabs.addTab(self.voice_page, "Voice")
        root.addLayout(header)
        root.addWidget(self.tabs, stretch=1)

        self.timer = QTimer(self)
        self.timer.setInterval(1_000)
        self.timer.timeout.connect(self.refresh)

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(8)
        return page, layout

    def _build_overview(self) -> QWidget:
        page, layout = self._page()
        self.overview_tree = QTreeWidget()
        self.overview_tree.setObjectName("DiagnosticsOverview")
        self.overview_tree.setHeaderLabels(["Item", "Value"])
        self.overview_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.overview_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.overview_tree, stretch=1)
        return page

    def _build_health(self) -> QWidget:
        page, layout = self._page()
        self.health_table = QTableWidget(0, 4)
        self.health_table.setObjectName("DiagnosticsHealthTable")
        self.health_table.setHorizontalHeaderLabels(
            ["Status", "Check", "Category", "Detail"]
        )
        self.health_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.health_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.health_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.health_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )
        self.health_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.health_table, stretch=1)
        return page

    def _build_logs(self) -> QWidget:
        page, layout = self._page()
        filters = QHBoxLayout()
        self.log_search = QLineEdit()
        self.log_search.setPlaceholderText("Search structured logs...")
        self.log_search.textChanged.connect(self._refresh_logs)
        self.log_level = QComboBox()
        self.log_level.addItems(["All levels", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level.currentIndexChanged.connect(self._refresh_logs)
        self.log_category = QComboBox()
        self.log_category.addItem("All categories", "")
        self.log_category.currentIndexChanged.connect(self._refresh_logs)
        export_button = QPushButton("Export JSON")
        export_button.clicked.connect(self._export_logs)
        filters.addWidget(self.log_search, stretch=1)
        filters.addWidget(self.log_level)
        filters.addWidget(self.log_category)
        filters.addWidget(export_button)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("DiagnosticsLogViewer")
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addLayout(filters)
        layout.addWidget(self.log_view, stretch=1)
        return page

    def _build_performance(self) -> QWidget:
        page, layout = self._page()
        self.performance_summary = QLabel("Waiting for runtime samples...")
        self.performance_summary.setWordWrap(True)
        self.performance_graph = MetricsGraph()
        self.profile_table = QTableWidget(0, 4)
        self.profile_table.setHorizontalHeaderLabels(
            ["Operation", "Calls", "Average", "Maximum"]
        )
        self.profile_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        for column in (1, 2, 3):
            self.profile_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        self.profile_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.performance_summary)
        layout.addWidget(self.performance_graph)
        layout.addWidget(self.profile_table, stretch=1)
        return page

    def _build_components(self) -> QWidget:
        page, layout = self._page()
        self.components_tree = QTreeWidget()
        self.components_tree.setHeaderLabels(["Component", "Status", "Backend / version"])
        self.components_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.components_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.components_tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.components_tree, stretch=1)
        return page

    def _build_voice(self) -> QWidget:
        page, layout = self._page()
        hint = QLabel(
            "Live STT diagnostics. Microphone tests keep only level/result metadata; audio is discarded."
        )
        hint.setWordWrap(True)
        controls = QHBoxLayout()
        self.microphone_test_button = QPushButton("Test Microphone")
        self.microphone_test_button.clicked.connect(self._test_microphone)
        self.microphone_playback = QCheckBox("Play sample back")
        self.microphone_test_status = QLabel("No microphone test run yet.")
        self.microphone_test_status.setWordWrap(True)
        controls.addWidget(self.microphone_test_button)
        controls.addWidget(self.microphone_playback)
        controls.addWidget(self.microphone_test_status, stretch=1)
        self.voice_tree = QTreeWidget()
        self.voice_tree.setObjectName("DiagnosticsVoiceTree")
        self.voice_tree.setHeaderLabels(["Voice diagnostic", "Value"])
        self.voice_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.voice_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(hint)
        layout.addLayout(controls)
        layout.addWidget(self.voice_tree, stretch=1)
        return page

    def _test_microphone(self) -> None:
        self.microphone_test_button.setEnabled(False)
        self.microphone_test_status.setText("Testing the selected microphone...")
        try:
            result = self.runtime.speech_input.test_microphone(
                duration_seconds=0.8,
                playback=self.microphone_playback.isChecked(),
            )
            self.microphone_test_status.setText(str(result.get("message", "")))
        except Exception as exc:  # noqa: BLE001
            self.microphone_test_status.setText(f"Microphone test failed: {exc}")
        finally:
            self.microphone_test_button.setEnabled(True)
        if self.last_snapshot is not None:
            self._refresh_voice_values(
                self.runtime.speech_input.diagnostics(),
                self.last_snapshot.voice,
                self.last_snapshot.live_vision,
            )

    def _build_agent(self) -> QWidget:
        page, layout = self._page()
        self.agent_tree = QTreeWidget()
        self.agent_tree.setHeaderLabels(["Agent state", "Value"])
        self.agent_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.agent_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.agent_actions = QTableWidget(0, 6)
        self.agent_actions.setHorizontalHeaderLabels(
            ["Time", "Tool", "Result", "Verified", "Duration", "Files"]
        )
        self.agent_actions.setEditTriggers(QTableWidget.NoEditTriggers)
        for column in (0, 1, 2, 3, 4):
            self.agent_actions.horizontalHeader().setSectionResizeMode(
                column,
                QHeaderView.ResizeToContents,
            )
        self.agent_actions.horizontalHeader().setSectionResizeMode(
            5,
            QHeaderView.Stretch,
        )
        layout.addWidget(self.agent_tree, stretch=1)
        layout.addWidget(self.agent_actions, stretch=2)
        return page

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()
        self.timer.start()

    def hideEvent(self, event) -> None:
        self.timer.stop()
        super().hideEvent(event)

    def _snapshot(self) -> RuntimeSnapshot:
        context = dict(self.context_provider() or {})
        return self.runtime.snapshot(
            renderer_capabilities=context.get("renderer_capabilities", ()),
            model=context.get("model", {}),
            gpu=context.get("gpu", {}),
            tools=context.get("tools", ()),
            task_queue=context.get("task_queue", 0),
            renderer_cache_bytes=context.get("renderer_cache_bytes", 0),
            project_root=context.get("project_root", ""),
        )

    def refresh(self) -> None:
        snapshot = self._snapshot()
        self.last_snapshot = snapshot
        self.status.setText(
            f"Health: {snapshot.health.status.title()} | "
            f"CPU {snapshot.performance.cpu_percent:.1f}% | "
            f"RAM {snapshot.performance.memory_mb:.0f} MB | "
            f"Threads {snapshot.performance.thread_count}"
        )
        self._refresh_overview(snapshot)
        self._refresh_health(snapshot)
        self._refresh_logs()
        self._refresh_performance(snapshot)
        self._refresh_agent(snapshot)
        self._refresh_components(snapshot)
        self._refresh_voice_values(
            snapshot.speech_input,
            snapshot.voice,
            snapshot.live_vision,
        )

    def _refresh_voice_values(
        self,
        speech: dict[str, Any],
        voice: dict[str, Any],
        live_vision: dict[str, Any] | None = None,
    ) -> None:
        self.voice_tree.clear()
        sections = {
            "Speech input": speech,
            "Speech output": voice,
            "Live Vision": dict(live_vision or {}),
        }
        for name, values in sections.items():
            root = QTreeWidgetItem([name, ""])
            self.voice_tree.addTopLevelItem(root)
            self._append_mapping(root, dict(values))
            root.setExpanded(True)

    def _append_mapping(
        self, parent: QTreeWidgetItem, mapping: dict[str, Any]
    ) -> None:
        for key, value in mapping.items():
            if isinstance(value, dict):
                child = QTreeWidgetItem([str(key), ""])
                parent.addChild(child)
                self._append_mapping(child, value)
            else:
                parent.addChild(QTreeWidgetItem([str(key), str(value)]))

    def _refresh_overview(self, snapshot: RuntimeSnapshot) -> None:
        self.overview_tree.clear()
        sections = {
            "Application": snapshot.application,
            "System platform": snapshot.platform,
            "Autonomous platform": snapshot.autonomous_platform,
            "Model": snapshot.model or {"status": "Not selected"},
            "GPU": snapshot.gpu or {"status": "Not detected"},
            "Agent": {
                "requests": snapshot.agent.get("requestCount", 0),
                "activeRequest": snapshot.agent.get("activeRequestId", ""),
                "activeIntents": snapshot.agent.get("activeIntents", ()),
                "registeredTools": snapshot.agent.get("toolCount", 0),
                "modelHealth": snapshot.agent.get("modelHealth", {}),
            },
            "Workers": snapshot.workers,
            "Desktop environment": snapshot.desktop,
            "Dependencies": snapshot.dependencies,
        }
        for name, values in sections.items():
            item = QTreeWidgetItem([name, ""])
            self.overview_tree.addTopLevelItem(item)
            self._append_mapping(item, values)
            item.setExpanded(True)

    def _refresh_health(self, snapshot: RuntimeSnapshot) -> None:
        checks = snapshot.health.checks
        self.health_table.setRowCount(len(checks))
        for row, check in enumerate(checks):
            values = (check.status.upper(), check.name, check.category, check.detail)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setForeground(
                        QColor(
                            "#70e0a9"
                            if check.status == "healthy"
                            else "#ffd166"
                            if check.status == "degraded"
                            else "#ff6b7a"
                        )
                    )
                self.health_table.setItem(row, column, item)

    @staticmethod
    def _format_log(record: StructuredLogRecord) -> str:
        metadata = (
            f" | {json.dumps(record.metadata, ensure_ascii=False)}"
            if record.metadata
            else ""
        )
        timestamp = record.timestamp.replace("T", " ")[:23]
        return (
            f"{timestamp}  {record.level:<8}  {record.category:<14}  "
            f"[{record.thread}] {record.message}{metadata}"
        )

    def _refresh_logs(self) -> None:
        level = self.log_level.currentText()
        if level == "All levels":
            level = ""
        category = str(self.log_category.currentData() or "")
        records = self.runtime.logs.search(
            self.log_search.text(),
            level=level,
            category=category,
        )
        categories = self.runtime.logs.categories()
        current = category
        self.log_category.blockSignals(True)
        self.log_category.clear()
        self.log_category.addItem("All categories", "")
        for value in categories:
            self.log_category.addItem(value, value)
        index = self.log_category.findData(current)
        self.log_category.setCurrentIndex(max(0, index))
        self.log_category.blockSignals(False)
        self.log_view.setPlainText("\n".join(self._format_log(record) for record in records))

    def _refresh_performance(self, snapshot: RuntimeSnapshot) -> None:
        sample = snapshot.performance
        gpu_text = (
            f"{sample.gpu_percent:.1f}%"
            if sample.gpu_percent is not None
            else "unavailable"
        )
        vram_text = (
            f"{sample.vram_used_mb:.0f} MB"
            if sample.vram_used_mb is not None
            else "unavailable"
        )
        self.performance_summary.setText(
            f"Process CPU: {sample.cpu_percent:.1f}%   "
            f"GPU: {gpu_text}   VRAM used: {vram_text}   "
            f"Process RAM: {sample.memory_mb:.1f} MB\n"
            f"FPS: {sample.fps:.1f}   Frame: {sample.frame_time_ms:.2f} ms   "
            f"Threads: {sample.thread_count}   Queue: {sample.task_queue}   "
            f"Renderer: {snapshot.profiler.get('currentRenderer') or 'idle'}\n"
            f"Disk read: {sample.disk_read_mb_s:.2f} MB/s   "
            f"Disk write: {sample.disk_write_mb_s:.2f} MB/s   "
            f"Estimated model speed: {sample.token_speed_tps:.1f} tok/s"
        )
        self.performance_graph.set_samples(self.runtime.profiler.samples())
        durations = snapshot.profiler.get("durations", {})
        rows = sorted(
            durations.items(),
            key=lambda item: float(item[1].get("averageMs", 0.0)),
            reverse=True,
        )
        self.profile_table.setRowCount(len(rows))
        for row, (name, values) in enumerate(rows):
            entries = (
                name,
                str(values.get("count", 0)),
                f"{float(values.get('averageMs', 0.0)):.2f} ms",
                f"{float(values.get('maxMs', 0.0)):.2f} ms",
            )
            for column, value in enumerate(entries):
                self.profile_table.setItem(row, column, QTableWidgetItem(value))

    def _refresh_components(self, snapshot: RuntimeSnapshot) -> None:
        self.components_tree.clear()
        renderers = QTreeWidgetItem(["Renderers", str(len(snapshot.renderers)), ""])
        self.components_tree.addTopLevelItem(renderers)
        for renderer in snapshot.renderers:
            renderers.addChild(
                QTreeWidgetItem(
                    [
                        renderer["label"] or renderer["id"],
                        "Available" if renderer["available"] else "Unavailable",
                        renderer["backend"] or renderer["reason"],
                    ]
                )
            )
        tools = QTreeWidgetItem(["Tools", str(len(snapshot.tools)), "Built in"])
        self.components_tree.addTopLevelItem(tools)
        for tool in snapshot.tools:
            tools.addChild(QTreeWidgetItem([tool, "Loaded", "MORICE desktop"]))
        agent_tools = snapshot.agent.get("tools", ())
        agent = QTreeWidgetItem(
            ["Agent tools", str(len(agent_tools)), "Typed + validated"]
        )
        self.components_tree.addTopLevelItem(agent)
        for tool in agent_tools:
            agent.addChild(
                QTreeWidgetItem(
                    [
                        str(tool.get("display_name") or tool.get("tool_id", "")),
                        str(tool.get("health_status", "")).title(),
                        (
                            f"{tool.get('tool_id', '')} v{tool.get('version', '')} | "
                            f"{tool.get('risk', '')}"
                        ),
                    ]
                )
            )
        workers = QTreeWidgetItem(
            [
                "Worker threads",
                str(snapshot.workers.get("threadCount", 0)),
                f"Queue: {snapshot.workers.get('taskQueue', 0)}",
            ]
        )
        self.components_tree.addTopLevelItem(workers)
        for thread in snapshot.workers.get("activeNames", ()):
            workers.addChild(QTreeWidgetItem([str(thread), "Active", "Python thread"]))
        desktop_capabilities = snapshot.desktop.get("capabilities", {})
        desktop = QTreeWidgetItem(
            [
                "Desktop managers",
                str(len(desktop_capabilities)),
                "Permission-controlled",
            ]
        )
        self.components_tree.addTopLevelItem(desktop)
        for name, available in desktop_capabilities.items():
            if isinstance(available, dict):
                enabled = any(bool(value) for value in available.values())
                detail = json.dumps(available, ensure_ascii=False)
            else:
                enabled = bool(available)
                detail = "Phase 3 desktop integration"
            desktop.addChild(
                QTreeWidgetItem(
                    [
                        str(name),
                        "Available" if enabled else "Unavailable",
                        detail,
                    ]
                )
            )
        renderers.setExpanded(True)
        tools.setExpanded(True)
        agent.setExpanded(True)
        workers.setExpanded(True)
        desktop.setExpanded(True)

    def _refresh_agent(self, snapshot: RuntimeSnapshot) -> None:
        agent = snapshot.agent
        self.agent_tree.clear()
        sections = {
            "Current request": {
                "id": agent.get("activeRequestId", ""),
                "intents": agent.get("activeIntents", ()),
                "requestCount": agent.get("requestCount", 0),
            },
            "Pipeline stages": agent.get("activeStages", {}),
            "Model health": agent.get("modelHealth", {}),
        }
        for label, values in sections.items():
            item = QTreeWidgetItem([label, ""])
            self.agent_tree.addTopLevelItem(item)
            self._append_mapping(item, values)
            item.setExpanded(True)
        actions = list(agent.get("recentActions", ()))
        self.agent_actions.setRowCount(len(actions))
        for row, action in enumerate(reversed(actions)):
            files = [
                *action.get("modified_files", ()),
                *action.get("generated_files", ()),
            ]
            values = (
                str(action.get("timestamp", "")),
                str(action.get("tool_id", "")),
                "Success" if action.get("success") else "Failed",
                "Yes" if action.get("verified") else "No",
                f"{float(action.get('duration_ms', 0)):.2f} ms",
                ", ".join(str(path) for path in files),
            )
            for column, value in enumerate(values):
                self.agent_actions.setItem(row, column, QTableWidgetItem(value))

    def _open_logs(self) -> None:
        self.runtime.logs.directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.runtime.logs.directory)))

    def _export_logs(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Export MORICE diagnostics logs",
            str(Path.home() / "morice-diagnostics-logs.json"),
            "JSON (*.json)",
        )
        if not target:
            return
        records = [asdict(record) for record in self.runtime.logs.search(limit=2_000)]
        with open(target, "w", encoding="utf-8") as stream:
            json.dump(records, stream, ensure_ascii=False, indent=2)

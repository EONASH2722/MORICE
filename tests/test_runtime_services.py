import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MORICE_DISABLE_SESSION", "1")
os.environ.setdefault("MORICE_DISABLE_RECOVERY", "1")
os.environ.setdefault("MORICE_PRELOAD", "0")
os.environ.setdefault("MORICE_REDUCE_MOTION", "1")

from PySide6.QtWidgets import QApplication

from morice.diagnostics_ui import DiagnosticsDialog
from morice.desktop_assistant import parse_desktop_command
from morice.runtime_services import (
    BackgroundTaskManager,
    CrashRecoveryManager,
    PerformanceProfiler,
    RuntimeServices,
    StartupHealthChecker,
    StructuredLogManager,
)
from morice.visualization import VisualizationManager


class StructuredLoggingTests(unittest.TestCase):
    def test_logs_are_json_searchable_and_reloadable(self):
        with tempfile.TemporaryDirectory() as directory:
            logs = StructuredLogManager(directory)
            logs.log("INFO", "Renderer ready", category="renderer")
            logs.log(
                "ERROR",
                "Model timed out",
                category="model",
                metadata={"timeout": 180},
            )

            self.assertEqual(
                [record.message for record in logs.search("timed", level="ERROR")],
                ["Model timed out"],
            )
            line = Path(logs.path).read_text(encoding="utf-8").splitlines()[-1]
            self.assertEqual(json.loads(line)["category"], "model")

            reloaded = StructuredLogManager(directory)
            self.assertEqual(len(reloaded.tail()), 2)
            self.assertEqual(reloaded.categories(), ["model", "renderer"])


class PerformanceProfilerTests(unittest.TestCase):
    def test_profiler_records_durations_runtime_samples_and_queue(self):
        profiler = PerformanceProfiler()
        with profiler.measure("unit-test", "tool"):
            time.sleep(0.002)
        profiler.set_frame_time(16.0)
        profiler.set_task_queue(3)
        profiler.record_model_completion(400, 1_000)
        sample = profiler.sample()
        summary = profiler.summary()

        self.assertGreaterEqual(sample.cpu_percent, 0)
        self.assertGreaterEqual(sample.memory_mb, 0)
        self.assertAlmostEqual(sample.fps, 62.5, places=1)
        self.assertEqual(sample.task_queue, 3)
        self.assertAlmostEqual(sample.token_speed_tps, 100.0)
        self.assertGreaterEqual(sample.disk_read_mb_s, 0)
        self.assertGreaterEqual(sample.disk_write_mb_s, 0)
        self.assertEqual(summary["durations"]["tool.unit-test"]["count"], 1)


class CrashRecoveryTests(unittest.TestCase):
    def test_unclean_session_offers_bounded_recovery_then_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            first = CrashRecoveryManager(directory)
            self.assertFalse(first.begin_session().available)
            first.save_snapshot(
                {
                    "history": [
                        {"role": "user", "content": f"message-{index}"}
                        for index in range(200)
                    ],
                    "draft": "continue this",
                }
            )

            second = CrashRecoveryManager(directory)
            recovery = second.begin_session()
            self.assertTrue(recovery.available)
            self.assertEqual(recovery.payload["draft"], "continue this")
            self.assertEqual(len(recovery.payload["history"]), 160)

            try:
                raise RuntimeError("controlled crash")
            except RuntimeError as exc:
                second.record_exception(type(exc), exc, exc.__traceback__)
            crash = json.loads(second.crash_path.read_text(encoding="utf-8"))
            self.assertEqual(crash["exceptionType"], "RuntimeError")
            self.assertIn("controlled crash", crash["stackTrace"])

            second.mark_clean()
            self.assertFalse(second.marker_path.exists())
            self.assertFalse(second.snapshot_path.exists())

    def test_locked_recovery_storage_never_prevents_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            recovery = CrashRecoveryManager(directory)
            denied = PermissionError(5, "Access is denied", str(recovery.marker_path))

            with patch(
                "morice.runtime_services._atomic_json_write",
                side_effect=denied,
            ):
                info = recovery.begin_session()
                recovery.save_snapshot({"history": [], "draft": "safe"})

            self.assertFalse(info.available)
            self.assertIn("continued", info.reason.casefold())
            self.assertIn("access is denied", recovery.last_write_error.casefold())


class HealthAndRuntimeTests(unittest.TestCase):
    def test_health_check_covers_assets_dependencies_model_and_renderers(self):
        manager = VisualizationManager()
        with tempfile.TemporaryDirectory() as directory:
            checker = StartupHealthChecker(
                Path(__file__).resolve().parent.parent,
                directory,
            )
            report = checker.run(
                renderer_capabilities=manager.capabilities(),
                model_path="",
                model_name="",
                tools=("Diagnostics", "System status"),
                gpu={"detected": True, "name": "Test GPU", "vramMb": 6144},
            )
        manager.shutdown()

        names = {check.name for check in report.checks}
        self.assertIn("Runtime storage", names)
        self.assertIn("Renderer registry", names)
        self.assertIn("AI model", names)
        self.assertIn("Dependency: PySide6", names)
        self.assertIn("Tool registry", names)
        self.assertIn("GPU profile", names)
        self.assertFalse(report.critical_failures)

    def test_health_check_rejects_corrupted_settings_json(self):
        manager = VisualizationManager()
        with tempfile.TemporaryDirectory() as directory:
            settings_file = Path(directory) / "settings.json"
            settings_file.write_text("{broken", encoding="utf-8")
            checker = StartupHealthChecker(
                Path(__file__).resolve().parent.parent,
                Path(directory) / "runtime",
            )
            with patch("morice.settings.settings_path", return_value=str(settings_file)):
                report = checker.run(
                    renderer_capabilities=manager.capabilities(),
                    tools=("Diagnostics",),
                )
        manager.shutdown()

        settings_check = next(
            check for check in report.checks if check.name == "Settings configuration"
        )
        self.assertEqual(settings_check.status, "failed")
        self.assertTrue(settings_check.critical)
        self.assertIn(settings_check, report.critical_failures)

    def test_bundled_dependency_without_distribution_metadata_is_healthy(self):
        checker = StartupHealthChecker(
            Path(__file__).resolve().parent.parent,
        )
        with patch(
            "morice.runtime_services.importlib.metadata.version",
            side_effect=__import__("importlib").metadata.PackageNotFoundError,
        ):
            check = checker._dependency_check("PySide6", "PySide6")

        self.assertEqual(check.status, "healthy")
        self.assertFalse(check.critical)
        self.assertTrue(check.detail)

    def test_runtime_start_worker_snapshot_and_clean_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeServices(
                directory,
                project_root=Path(__file__).resolve().parent.parent,
            )
            recovery = runtime.start()
            self.assertFalse(recovery.available)
            future = runtime.workers.submit("controlled-task", lambda: 42)
            self.assertEqual(future.result(timeout=3), 42)
            manager = VisualizationManager()
            runtime.run_health_check(
                renderer_capabilities=manager.capabilities()
            )
            snapshot = runtime.snapshot(
                tools=("System status", "Diagnostics"),
                task_queue=2,
            )

            self.assertEqual(snapshot.application["name"], "MORICE")
            self.assertGreaterEqual(snapshot.performance.thread_count, 1)
            self.assertIn("Diagnostics", snapshot.tools)
            self.assertIn("python", snapshot.platform)
            self.assertIn("PySide6", snapshot.dependencies)
            self.assertIn("orchestrator", snapshot.autonomous_platform)
            self.assertIn("knowledge", snapshot.autonomous_platform)
            manager.shutdown()
            runtime.shutdown(clean=True)
            self.assertFalse(runtime.recovery.marker_path.exists())

    def test_shutdown_finishes_remaining_cleanup_and_refuses_restart_after_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeServices(
                directory,
                project_root=Path(__file__).resolve().parent.parent,
            )
            runtime.start()
            real_platform = runtime.platform_services
            real_plugins = runtime.plugins
            real_desktop = runtime.desktop
            real_workers = runtime.workers
            runtime.platform_services = Mock()
            runtime.platform_services.shutdown.side_effect = RuntimeError(
                "controlled platform failure"
            )
            runtime.plugins = Mock()
            runtime.desktop = Mock()
            runtime.workers = Mock()

            try:
                runtime.shutdown(clean=True)

                runtime.platform_services.shutdown.assert_called_once_with()
                runtime.plugins.shutdown.assert_called_once_with()
                runtime.desktop.shutdown.assert_called_once_with()
                runtime.workers.shutdown.assert_called_once_with()
                self.assertFalse(runtime.started)
                self.assertTrue(runtime.recovery.marker_path.exists())
                with self.assertRaisesRegex(RuntimeError, "cannot restart"):
                    runtime.start()
            finally:
                runtime.recovery.uninstall_exception_hooks()
                runtime.recovery.mark_clean()
                real_platform.shutdown()
                real_plugins.shutdown()
                real_desktop.shutdown()
                real_workers.shutdown()

    def test_owned_ollama_process_is_stopped_during_runtime_reset(self):
        from morice import llm_client

        process = Mock()
        process.poll.return_value = None
        process.wait.return_value = 0
        llm_client._OLLAMA_PROCESS = process
        with (
            patch("morice.llama_server.stop_server") as stop_server,
            patch("morice.local_llama.clear_cache") as clear_cache,
        ):
            llm_client.reset_model_runtime()

        stop_server.assert_called_once_with()
        clear_cache.assert_called_once_with()
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=8)
        self.assertIsNone(llm_client._OLLAMA_PROCESS)

    def test_diagnostics_command_is_routed(self):
        action = parse_desktop_command("/diagnostics")
        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "diagnostics")


class DiagnosticsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_exposes_health_logs_performance_and_components(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeServices(
                directory,
                project_root=Path(__file__).resolve().parent.parent,
            )
            runtime.start()
            manager = VisualizationManager()
            runtime.run_health_check(renderer_capabilities=manager.capabilities())
            runtime.logs.log("INFO", "Diagnostics UI test", category="test")
            dialog = DiagnosticsDialog(
                runtime,
                lambda: {
                    "renderer_capabilities": manager.capabilities(),
                    "model": {"name": "test-model"},
                    "gpu": {"name": "test-gpu", "vramMb": 6144},
                    "tools": ("Diagnostics", "System"),
                    "task_queue": 0,
                    "renderer_cache_bytes": manager.resources.used_bytes,
                },
            )
            dialog.show()
            self.app.processEvents()
            dialog.refresh()

            self.assertEqual(
                [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())],
                ["Overview", "Health", "Logs", "Performance", "Agent", "Components", "Voice"],
            )
            self.assertEqual(dialog.microphone_test_button.text(), "Test Microphone")
            self.assertFalse(dialog.microphone_playback.isChecked())
            self.assertGreater(dialog.overview_tree.topLevelItemCount(), 0)
            self.assertGreater(dialog.health_table.rowCount(), 0)
            self.assertIn("Diagnostics UI test", dialog.log_view.toPlainText())
            self.assertGreater(dialog.components_tree.topLevelItemCount(), 0)

            dialog.close()
            manager.shutdown()
            runtime.shutdown(clean=True)


class PriorityWorkerTests(unittest.TestCase):
    def test_interactive_task_is_not_queued_behind_background_work(self):
        with tempfile.TemporaryDirectory() as directory:
            logs = StructuredLogManager(directory)
            profiler = PerformanceProfiler()
            manager = BackgroundTaskManager(logs, profiler, max_workers=4)
            release = threading.Event()
            started = [threading.Event(), threading.Event()]

            def occupy(index: int) -> None:
                started[index].set()
                release.wait(3)

            background = [
                manager.submit("index", occupy, index, priority="background")
                for index in range(2)
            ]
            self.assertTrue(all(event.wait(1) for event in started))
            interactive = manager.submit(
                "chat-reply",
                lambda: "ready",
                priority="interactive",
            )
            self.assertEqual("ready", interactive.result(timeout=1))
            release.set()
            for future in background:
                future.result(timeout=2)
            manager.shutdown()


if __name__ == "__main__":
    unittest.main()

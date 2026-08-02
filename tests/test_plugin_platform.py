from __future__ import annotations

import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from morice.agent_tools import ToolRegistry
from morice.plugin_cli import create_plugin, pack_plugin
from morice.plugin_manager import (
    PermissionReviewRequired,
    PluginEventBus,
    PluginManager,
    PluginMarketplace,
)
from morice.plugin_sdk import (
    PluginManifest,
    PluginState,
    PluginValidationError,
    SemVer,
    validate_transition,
    version_satisfies,
)
from morice.plugin_ui import PluginCenter
from morice.visualization import RendererRegistry


PLUGIN_SOURCE = """\
class Plugin:
    def __init__(self, api):
        self.api = api
        self.events = []

    def on_start(self):
        self.api.storage_set("starts", self.api.storage_get("starts", 0) + 1)

    def on_event(self, name, payload):
        self.events.append(name)

    def handle_command(self, command_id, arguments):
        if command_id == "crash":
            raise RuntimeError("intentional test failure")
        return {"command": command_id, "arguments": arguments}

    def handle_tool(self, tool_id, arguments):
        return {"tool": tool_id, "value": arguments.get("value")}

    def render(self, renderer_id, prompt):
        return {
            "kind": "diagram",
            "title": "Plugin diagram",
            "diagramType": "flowchart",
            "nodes": [
                {"id": "start", "label": "Start"},
                {"id": "finish", "label": "Finish"},
            ],
            "edges": [{"source": "start", "target": "finish", "label": "next"}],
        }
"""


def write_plugin(
    install_root: Path,
    plugin_id: str = "test.extension",
    *,
    version: str = "1.0.0",
    permissions: list[str] | None = None,
    dependencies=None,
    source: str = PLUGIN_SOURCE,
    renderer: bool = True,
) -> Path:
    root = install_root / plugin_id
    root.mkdir(parents=True, exist_ok=True)
    contributions = {
        "commands": [{"id": "hello", "title": "Hello command"}],
        "tools": [
            {
                "id": f"{plugin_id}.tool",
                "title": "Test tool",
                "description": "Test tool contribution.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "additionalProperties": False,
                },
                "outputSchema": {"type": "object"},
            }
        ],
    }
    if renderer:
        contributions["renderers"] = [
            {
                "id": f"{plugin_id}.renderer",
                "title": "Test renderer",
                "keywords": ["plugin-diagram"],
            }
        ]
    manifest = {
        "id": plugin_id,
        "name": plugin_id,
        "version": version,
        "apiVersion": "1.0",
        "description": "Test plugin",
        "author": "MORICE tests",
        "entryPoint": "plugin.py",
        "categories": ["tool", "renderer"] if renderer else ["tool"],
        "permissions": permissions or [],
        "dependencies": dependencies or [],
        "platforms": ["any"],
        "minMoriceVersion": "0.5.0",
        "contributions": contributions,
    }
    (root / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "plugin.py").write_text(source, encoding="utf-8")
    return root


class PluginSDKTests(unittest.TestCase):
    def test_semver_and_constraints(self):
        self.assertEqual(str(SemVer.parse("2.4.1")), "2.4.1")
        self.assertTrue(version_satisfies("1.4.2", "^1.2.0"))
        self.assertTrue(version_satisfies("1.4.2", ">=1.0.0,<2.0.0"))
        self.assertFalse(version_satisfies("2.0.0", "~1.4.0"))

    def test_manifest_rejects_unsafe_entry_and_unknown_permission(self):
        base = {
            "id": "test.plugin",
            "name": "Test",
            "version": "1.0.0",
            "entryPoint": "../escape.py",
        }
        with self.assertRaises(PluginValidationError):
            PluginManifest.from_dict(base)

    def test_manifest_accepts_declarative_native_ui_contributions(self):
        manifest = PluginManifest.from_dict(
            {
                "id": "test.ui",
                "name": "UI Test",
                "version": "1.0.0",
                "entryPoint": "plugin.py",
                "contributions": {
                    "toolbarButtons": [
                        {
                            "id": "open",
                            "title": "Open",
                            "commandId": "open-command",
                        }
                    ],
                    "sidebarPanels": [{"id": "panel", "title": "Test Panel"}],
                    "floatingWindows": [{"id": "window", "title": "Test Window"}],
                },
            }
        )
        self.assertEqual(
            [item.kind for item in manifest.contributions.ui],
            ["toolbar-button", "sidebar-panel", "floating-window"],
        )
        base = {
            "id": "test.plugin",
            "name": "Test",
            "version": "1.0.0",
        }
        base["entryPoint"] = "plugin.py"
        base["permissions"] = ["entire.computer"]
        with self.assertRaises(PluginValidationError):
            PluginManifest.from_dict(base)

    def test_manifest_rejects_duplicate_and_undeclared_contributions(self):
        base = {
            "id": "test.contributions",
            "name": "Contribution Test",
            "version": "1.0.0",
            "entryPoint": "plugin.py",
            "contributions": {
                "commands": [
                    {"id": "duplicate", "title": "First"},
                    {"id": "duplicate", "title": "Second"},
                ]
            },
        }
        with self.assertRaisesRegex(PluginValidationError, "Duplicate"):
            PluginManifest.from_dict(base)
        base["contributions"] = {
            "tools": [
                {
                    "id": "test.contributions.tool",
                    "title": "Tool",
                    "description": "Requires a declared capability.",
                    "permissions": ["network"],
                }
            ]
        }
        with self.assertRaisesRegex(PluginValidationError, "not declared"):
            PluginManifest.from_dict(base)

    def test_lifecycle_rejects_invalid_transition(self):
        with self.assertRaises(PluginValidationError):
            validate_transition(PluginState.INSTALLED, PluginState.RUNNING)

    def test_event_bus_isolates_failing_subscriber(self):
        bus = PluginEventBus()
        seen = []
        bus.subscribe("*", lambda event: seen.append(event.event_type))
        bus.subscribe("*", lambda _event: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.publish("test.event", {"ok": True})
        self.assertEqual(seen, ["test.event"])
        self.assertEqual(bus.history[-1].payload, {"ok": True})


class PluginManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.manager = PluginManager(
            self.root / "runtime",
            core_root=Path(__file__).resolve().parents[1],
        )

    def tearDown(self):
        try:
            self.manager.shutdown()
        except RuntimeError:
            pass
        self.temporary.cleanup()

    def install_path(self) -> Path:
        return self.manager.install_root

    def test_discover_start_command_storage_and_shutdown(self):
        write_plugin(self.install_path())
        records = self.manager.discover()
        self.assertEqual(len(records), 1)
        record = self.manager.start("test.extension")
        self.assertEqual(record.state, PluginState.RUNNING)
        self.assertTrue(record.sandbox and record.sandbox.running)
        response = self.manager.invoke_command("test.extension", "hello", {"x": 1})
        self.assertEqual(response["arguments"], {"x": 1})
        self.manager.disable("test.extension")
        self.assertEqual(record.state, PluginState.DISABLED)
        storage = json.loads(
            (self.manager.storage_root / "test.extension" / "storage.json").read_text()
        )
        self.assertEqual(storage["starts"], 1)

    def test_lazy_plugin_registers_proxies_and_starts_on_first_use(self):
        root = write_plugin(self.install_path())
        manifest_path = root / "plugin.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["lazy"] = True
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        self.manager.discover()
        tools = ToolRegistry()
        renderers = RendererRegistry()
        self.manager.bind(tool_registry=tools, renderer_registry=renderers)
        result = self.manager.start_enabled()
        record = self.manager.require("test.extension")
        self.assertEqual(result["test.extension"], "lazy")
        self.assertEqual(record.state, PluginState.VALIDATED)
        self.assertIsNone(record.sandbox)
        self.assertIsNotNone(tools.definition("test.extension.tool"))
        response = self.manager.invoke_command("test.extension", "hello", {})
        self.assertEqual(response["command"], "hello")
        self.assertEqual(record.state, PluginState.RUNNING)

    def test_diagnostics_include_process_resources_and_dependencies(self):
        write_plugin(self.install_path())
        self.manager.discover()
        self.manager.start("test.extension")
        diagnostics = self.manager.diagnostics("test.extension")
        process = diagnostics["diagnostics"]["process"]
        self.assertTrue(process["running"])
        self.assertGreater(process["memoryBytes"], 0)
        self.assertIn("cpuUsagePercent", process)
        self.assertEqual(diagnostics["diagnostics"]["dependencies"], [])

    def test_permission_review_is_mandatory_and_version_specific(self):
        write_plugin(self.install_path(), permissions=["notifications", "network"])
        self.manager.discover()
        with self.assertRaises(PermissionReviewRequired):
            self.manager.start("test.extension")
        self.manager.review_permissions("test.extension", ["notifications"])
        self.manager.start("test.extension")
        review = self.manager.permissions.snapshot("test.extension")
        self.assertEqual(review["granted"], ["notifications"])
        self.assertEqual(review["denied"], ["network"])

    def test_tool_and_renderer_contributions_are_removed_on_pause(self):
        write_plugin(self.install_path())
        self.manager.discover()
        tools = ToolRegistry()
        renderers = RendererRegistry()
        self.manager.bind(tool_registry=tools, renderer_registry=renderers)
        self.manager.start("test.extension")
        self.assertIsNotNone(tools.definition("test.extension.tool"))
        renderer = renderers.get("test.extension.renderer")
        self.assertIsNotNone(renderer)
        artifact = renderer.render("plugin-diagram")
        valid, error = renderer.validate(artifact)
        self.assertTrue(valid, error)
        self.manager.pause("test.extension")
        self.assertIsNone(tools.definition("test.extension.tool"))
        self.assertIsNone(renderers.get("test.extension.renderer"))
        self.manager.resume("test.extension")
        self.assertIsNotNone(tools.definition("test.extension.tool"))

    def test_dependency_order_and_version_conflict(self):
        write_plugin(self.install_path(), "test.base", renderer=False)
        write_plugin(
            self.install_path(),
            "test.child",
            dependencies=[{"id": "test.base", "version": "^1.0.0"}],
            renderer=False,
        )
        self.manager.discover()
        self.assertEqual(
            self.manager.dependency_order(), ("test.base", "test.child")
        )
        (self.install_path() / "test.base" / "plugin.json").write_text(
            (self.install_path() / "test.base" / "plugin.json")
            .read_text()
            .replace('"version": "1.0.0"', '"version": "2.0.0"'),
            encoding="utf-8",
        )
        self.manager.discover()
        with self.assertRaises(PluginValidationError):
            self.manager.dependency_order()

    def test_dependency_cycle_is_rejected(self):
        write_plugin(
            self.install_path(),
            "test.first",
            dependencies=[{"id": "test.second", "version": "*"}],
            renderer=False,
        )
        write_plugin(
            self.install_path(),
            "test.second",
            dependencies=[{"id": "test.first", "version": "*"}],
            renderer=False,
        )
        self.manager.discover()
        with self.assertRaises(PluginValidationError):
            self.manager.dependency_order()

    def test_plugin_exception_does_not_crash_manager(self):
        write_plugin(self.install_path())
        self.manager.discover()
        self.manager.start("test.extension")
        with self.assertRaises(RuntimeError):
            self.manager.invoke(
                "test.extension",
                "command",
                {"id": "crash", "arguments": {}},
            )
        record = self.manager.require("test.extension")
        self.assertEqual(record.state, PluginState.RUNNING)
        self.assertEqual(record.diagnostics.failures, 1)
        self.assertTrue(record.sandbox and record.sandbox.running)

    def test_hard_plugin_crash_is_isolated_and_recorded(self):
        source = PLUGIN_SOURCE.replace(
            'if command_id == "crash":\n            raise RuntimeError("intentional test failure")',
            'if command_id == "crash":\n            import os\n            os._exit(23)',
        )
        write_plugin(self.install_path(), source=source)
        self.manager.discover()
        self.manager.start("test.extension")
        with self.assertRaises(RuntimeError):
            self.manager.invoke(
                "test.extension",
                "command",
                {"id": "crash", "arguments": {}},
                timeout=2,
            )
        record = self.manager.require("test.extension")
        self.assertEqual(record.state, PluginState.FAILED)
        self.assertEqual(record.diagnostics.crashes, 1)
        self.assertFalse(record.sandbox)

    def test_timeout_terminates_hung_plugin(self):
        source = PLUGIN_SOURCE.replace(
            "def handle_command(self, command_id, arguments):",
            "def handle_command(self, command_id, arguments):\n"
            '        if command_id == "sleep":\n'
            "            import time\n"
            "            time.sleep(10)\n",
        )
        write_plugin(self.install_path(), source=source)
        self.manager.discover()
        self.manager.start("test.extension")
        with self.assertRaises(TimeoutError):
            self.manager.invoke(
                "test.extension",
                "command",
                {"id": "sleep", "arguments": {}},
                timeout=0.2,
            )
        record = self.manager.require("test.extension")
        self.assertEqual(record.state, PluginState.FAILED)

    def test_undeclared_file_read_is_denied_inside_host(self):
        outside = self.root / "private.txt"
        outside.write_text("secret", encoding="utf-8")
        source = PLUGIN_SOURCE.replace(
            "def handle_command(self, command_id, arguments):",
            "def handle_command(self, command_id, arguments):\n"
            '        if command_id == "read":\n'
            f"            return open({str(outside)!r}, encoding='utf-8').read()\n",
        )
        write_plugin(self.install_path(), source=source)
        self.manager.discover()
        self.manager.start("test.extension")
        with self.assertRaisesRegex(RuntimeError, "filesystem.read"):
            self.manager.invoke(
                "test.extension",
                "command",
                {"id": "read", "arguments": {}},
            )
        self.assertEqual(
            self.manager.require("test.extension").state,
            PluginState.RUNNING,
        )

    def test_approved_file_api_writes_outside_core_atomically(self):
        output = self.root / "approved-output.txt"
        source = PLUGIN_SOURCE.replace(
            'if command_id == "crash":',
            'if command_id == "hello":\n'
            '            return self.api.file_write_text(arguments["path"], "approved")\n'
            '        if command_id == "crash":',
        )
        write_plugin(
            self.install_path(),
            permissions=["filesystem.write"],
            source=source,
        )
        self.manager.discover()
        self.manager.review_permissions("test.extension", ["filesystem.write"])
        self.manager.start("test.extension")
        result = self.manager.invoke_command(
            "test.extension",
            "hello",
            {"path": str(output)},
        )
        self.assertEqual(output.read_text(encoding="utf-8"), "approved")
        self.assertEqual(result["bytes"], len("approved"))

    def test_core_mutation_is_denied_even_with_write_permission(self):
        build_root = Path(__file__).resolve().parents[1] / "build"
        build_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="plugin-core-canary-",
            dir=build_root,
        ) as temporary:
            canary = Path(temporary) / "keep.txt"
            canary.write_text("keep", encoding="utf-8")
            source = PLUGIN_SOURCE.replace(
                'if command_id == "crash":',
                'if command_id == "hello":\n'
                '            import os\n'
                f"            os.remove({str(canary)!r})\n"
                '        if command_id == "crash":',
            )
            write_plugin(
                self.install_path(),
                permissions=["filesystem.write"],
                source=source,
            )
            self.manager.discover()
            self.manager.review_permissions("test.extension", ["filesystem.write"])
            self.manager.start("test.extension")
            with self.assertRaisesRegex(RuntimeError, "core files"):
                self.manager.invoke_command("test.extension", "hello", {})
            self.assertTrue(canary.exists())

    def test_plugin_events_are_delivered_to_other_running_plugins(self):
        source = PLUGIN_SOURCE.replace(
            'if command_id == "crash":',
            'if arguments.get("emit"):\n'
            '            self.api.emit("test.peer-event", {"ok": True})\n'
            '        if arguments.get("events"):\n'
            '            return {"events": list(self.events)}\n'
            '        if command_id == "crash":',
        )
        write_plugin(self.install_path(), "test.first", source=source)
        write_plugin(self.install_path(), "test.second", source=source)
        self.manager.discover()
        self.manager.start("test.first")
        self.manager.start("test.second")
        self.manager.invoke_command("test.first", "hello", {"emit": True})
        deadline = time.monotonic() + 3
        events = []
        while time.monotonic() < deadline:
            result = self.manager.invoke_command(
                "test.second",
                "hello",
                {"events": True},
            )
            events = result["events"]
            if "test.peer-event" in events:
                break
            time.sleep(0.05)
        self.assertIn("test.peer-event", events)

    def test_safe_package_install_update_and_rollback(self):
        source = self.root / "source"
        write_plugin(source, version="1.0.0")
        package = self.root / "one.zip"
        with zipfile.ZipFile(package, "w") as archive:
            for path in (source / "test.extension").iterdir():
                archive.write(path, path.name)
        record = self.manager.install(package)
        self.assertEqual(record.manifest.version, "1.0.0")

        updated = self.root / "updated"
        write_plugin(updated, version="1.1.0")
        update_package = self.root / "two.zip"
        with zipfile.ZipFile(update_package, "w") as archive:
            for path in (updated / "test.extension").iterdir():
                archive.write(path, path.name)
        record = self.manager.update("test.extension", update_package)
        self.assertEqual(record.manifest.version, "1.1.0")
        restored = self.manager.rollback("test.extension", "1.0.0")
        self.assertEqual(restored.manifest.version, "1.0.0")

    def test_pinned_plugin_rejects_updates(self):
        source = self.root / "source"
        write_plugin(source, version="1.0.0")
        package = self.root / "one.zip"
        with zipfile.ZipFile(package, "w") as archive:
            for path in (source / "test.extension").iterdir():
                archive.write(path, path.name)
        self.manager.install(package)
        self.manager.pin("test.extension", "1.0.0")
        with self.assertRaisesRegex(PluginValidationError, "pinned"):
            self.manager.update("test.extension", package)

    def test_update_rejects_mismatched_plugin_before_replacement(self):
        source = self.root / "source"
        write_plugin(source, "test.extension", version="1.0.0")
        package = self.root / "one.zip"
        with zipfile.ZipFile(package, "w") as archive:
            for path in (source / "test.extension").iterdir():
                archive.write(path, path.name)
        self.manager.install(package)

        other = self.root / "other"
        write_plugin(other, "other.extension", version="2.0.0")
        other_package = self.root / "other.zip"
        with zipfile.ZipFile(other_package, "w") as archive:
            for path in (other / "other.extension").iterdir():
                archive.write(path, path.name)
        with self.assertRaisesRegex(PluginValidationError, "does not match"):
            self.manager.update("test.extension", other_package)
        self.assertEqual(
            self.manager.require("test.extension").manifest.version,
            "1.0.0",
        )

    def test_incompatible_replacement_keeps_installed_plugin(self):
        source = self.root / "source"
        write_plugin(source, "test.extension", version="1.0.0")
        package = self.root / "one.zip"
        with zipfile.ZipFile(package, "w") as archive:
            for path in (source / "test.extension").iterdir():
                archive.write(path, path.name)
        self.manager.install(package)

        incompatible = self.root / "incompatible"
        root = write_plugin(
            incompatible,
            "test.extension",
            version="2.0.0",
        )
        manifest_path = root / "plugin.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["minMoriceVersion"] = "99.0.0"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        incompatible_package = self.root / "incompatible.zip"
        with zipfile.ZipFile(incompatible_package, "w") as archive:
            for path in root.iterdir():
                archive.write(path, path.name)

        with self.assertRaisesRegex(PluginValidationError, "incompatible"):
            self.manager.install(incompatible_package)
        self.assertEqual(
            self.manager.require("test.extension").manifest.version,
            "1.0.0",
        )
        installed = PluginManifest.from_path(
            self.manager.install_root / "test.extension" / "plugin.json"
        )
        self.assertEqual(installed.version, "1.0.0")

    def test_automatic_update_preference_is_persisted(self):
        self.manager.set_automatic_updates(True)
        other = PluginManager(
            self.root / "runtime",
            core_root=Path(__file__).resolve().parents[1],
        )
        try:
            self.assertTrue(other.auto_updates_enabled)
        finally:
            other.shutdown()

    def test_shutdown_is_idempotent(self):
        write_plugin(self.install_path())
        self.manager.discover()
        self.manager.start("test.extension")
        self.manager.shutdown()
        self.manager.shutdown()
        self.assertEqual(
            self.manager.require("test.extension").state,
            PluginState.VALIDATED,
        )

    def test_zip_traversal_is_rejected(self):
        package = self.root / "unsafe.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("../escape.txt", "no")
            archive.writestr("plugin.json", "{}")
        with self.assertRaises(PluginValidationError):
            self.manager.install(package)
        self.assertFalse((self.root / "escape.txt").exists())

    def test_hot_reload_detects_entry_change(self):
        root = write_plugin(self.install_path())
        self.manager.discover()
        self.manager.start("test.extension")
        before = self.manager.require("test.extension").diagnostics.restarts
        time.sleep(0.02)
        (root / "plugin.py").write_text(PLUGIN_SOURCE + "\n# changed\n", encoding="utf-8")
        self.manager.start_hot_reload(interval=0.05)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.manager.require("test.extension").diagnostics.restarts > before:
                break
            time.sleep(0.05)
        self.assertGreater(
            self.manager.require("test.extension").diagnostics.restarts, before
        )

    def test_100_plugin_discovery_stress(self):
        for index in range(100):
            write_plugin(
                self.install_path(),
                f"stress.plugin{index}",
                renderer=False,
            )
        started = time.perf_counter()
        records = self.manager.discover()
        elapsed = time.perf_counter() - started
        self.assertEqual(len(records), 100)
        self.assertLess(elapsed, 5.0)
        self.assertEqual(len(self.manager.dependency_order()), 100)


class PluginMarketplaceAndCLITests(unittest.TestCase):
    def test_local_marketplace_search(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = Path(temporary) / "catalog.json"
            catalog.write_text(
                json.dumps(
                    {
                        "plugins": [
                            {
                                "id": "science.plotter",
                                "name": "Science Plotter",
                                "version": "1.0.0",
                                "description": "Interactive science charts",
                                "downloadUrl": "https://example.invalid/plugin.zip",
                                "sha256": "a" * 64,
                                "verified": True,
                                "featured": True,
                                "rating": 4.8,
                                "downloads": 1200,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            marketplace = PluginMarketplace()
            marketplace.refresh(catalog)
            result = marketplace.search("science", verified_only=True)
            self.assertEqual(result[0].plugin_id, "science.plotter")

    def test_generator_validate_and_pack(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plugin = create_plugin(root / "sample", "sample.generated", "Generated")
            manifest = PluginManifest.from_path(plugin / "plugin.json")
            self.assertEqual(manifest.plugin_id, "sample.generated")
            archive = pack_plugin(plugin, root / "sample.zip")
            self.assertTrue(zipfile.is_zipfile(archive))


class PluginUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_plugin_center_exposes_all_phase_six_surfaces(self):
        with tempfile.TemporaryDirectory() as temporary:
            manager = PluginManager(
                Path(temporary) / "runtime",
                core_root=Path(__file__).resolve().parents[1],
            )
            try:
                write_plugin(manager.install_root, renderer=False)
                manager.discover()
                center = PluginCenter(manager)
                self.assertEqual(
                    [center.tabs.tabText(index) for index in range(center.tabs.count())],
                    [
                        "Installed",
                        "Marketplace",
                        "Permissions",
                        "Diagnostics",
                        "Developer",
                    ],
                )
                self.assertEqual(center.installed_list.count(), 1)
                self.assertIn("test.extension", center.diagnostics_text.toPlainText())
                center.close()
            finally:
                manager.shutdown()


if __name__ == "__main__":
    unittest.main()

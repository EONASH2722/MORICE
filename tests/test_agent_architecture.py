import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from morice.agent_orchestrator import AgentOrchestrator
from morice.agent_tools import BuiltinTools
from morice.agent_types import (
    ExecutionStage,
    IntentType,
    PermissionStatus,
    ToolCall,
)
from morice.intent_router import IntentRouter
from morice.model_router import ContextManager, ModelRouter
from morice.project_index import ProjectIndexer
from morice.runtime_services import RuntimeServices


class IntentRouterTests(unittest.TestCase):
    def test_multi_intent_request_is_split_into_ordered_subtasks(self):
        plan = IntentRouter().plan(
            "Build the Python project, run its tests, and plot the benchmark data."
        )

        self.assertIn(IntentType.PROJECT_MODIFICATION, plan.intents)
        self.assertIn(IntentType.CODING, plan.intents)
        self.assertIn(IntentType.TERMINAL_TASK, plan.intents)
        self.assertIn(IntentType.VISUALIZATION, plan.intents)
        self.assertEqual(tuple(ExecutionStage), plan.stages)
        self.assertGreaterEqual(len(plan.subtasks), 4)

    def test_unmatched_conversation_uses_general_chat(self):
        matches = IntentRouter().classify("hello there")
        self.assertEqual(matches[0].intent, IntentType.GENERAL_CHAT)


class ProjectIndexerTests(unittest.TestCase):
    def test_indexer_extracts_project_facts_symbols_and_relevant_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "node_modules").mkdir()
            (root / "src" / "main.py").write_text(
                "import json\n\nclass App:\n    pass\n\ndef launch():\n    return App()\n",
                encoding="utf-8",
            )
            (root / "requirements.txt").write_text(
                "fastapi==1.2.3\npytest>=8\n",
                encoding="utf-8",
            )
            (root / "node_modules" / "noise.js").write_text(
                "function ignored() {}",
                encoding="utf-8",
            )
            indexer = ProjectIndexer()
            index = indexer.build(root)
            relevant = indexer.search(index, "launch app")

            self.assertEqual(index.languages["Python"], 1)
            self.assertIn("FastAPI", index.frameworks)
            self.assertIn("fastapi", index.dependencies)
            self.assertNotIn(
                "node_modules/noise.js",
                {item.path for item in index.files},
            )
            symbols = {
                symbol.name
                for item in index.files
                for symbol in item.symbols
            }
            self.assertIn("App", symbols)
            self.assertIn("launch", symbols)
            self.assertEqual(relevant[0]["path"], "src/main.py")


class ToolExecutionTests(unittest.TestCase):
    def test_patch_requires_exact_permission_then_supports_verified_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            target = root / "app.py"
            target.write_text("print('before')\n", encoding="utf-8")
            tools = BuiltinTools(Path(directory) / "agent")
            arguments = {
                "root": str(root),
                "changes": [
                    {"path": "app.py", "content": "print('after')\n"},
                    {"path": "new.py", "content": "VALUE = 2\n"},
                ],
            }

            preview = tools.executor.execute(
                ToolCall("filesystem.preview_patch", arguments)
            )
            self.assertTrue(preview.success)
            self.assertIn("-print('before')", preview.output["files"][0]["diff"])
            denied = tools.executor.execute(
                ToolCall("filesystem.apply_patch", arguments)
            )
            self.assertFalse(denied.success)
            self.assertEqual(
                denied.permission_status,
                PermissionStatus.REQUIRED,
            )

            token = tools.permissions.grant("filesystem.apply_patch", arguments)
            applied = tools.executor.execute(
                ToolCall(
                    "filesystem.apply_patch",
                    arguments,
                    permission_token=token,
                )
            )
            self.assertTrue(applied.success)
            self.assertTrue(applied.verified)
            self.assertEqual(target.read_text(encoding="utf-8"), "print('after')\n")
            self.assertTrue((root / "new.py").is_file())
            undo_id = applied.metadata["undoId"]

            undo_arguments = {"undo_id": undo_id}
            undo_token = tools.permissions.grant("action.undo", undo_arguments)
            undone = tools.executor.execute(
                ToolCall(
                    "action.undo",
                    undo_arguments,
                    permission_token=undo_token,
                )
            )
            self.assertTrue(undone.success)
            self.assertTrue(undone.verified)
            self.assertEqual(target.read_text(encoding="utf-8"), "print('before')\n")
            self.assertFalse((root / "new.py").exists())
            self.assertGreaterEqual(len(tools.history.recent()), 4)

    def test_permission_token_cannot_be_reused_or_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            tools = BuiltinTools(Path(directory) / "agent")
            arguments = {
                "root": str(root),
                "changes": [{"path": "one.txt", "content": "one"}],
            }
            token = tools.permissions.grant("filesystem.apply_patch", arguments)
            changed = {
                "root": str(root),
                "changes": [{"path": "two.txt", "content": "two"}],
            }
            rejected = tools.executor.execute(
                ToolCall(
                    "filesystem.apply_patch",
                    changed,
                    permission_token=token,
                )
            )
            self.assertFalse(rejected.success)
            self.assertEqual(
                rejected.permission_status,
                PermissionStatus.REQUIRED,
            )
            self.assertFalse((root / "two.txt").exists())

    def test_patch_rejects_workspace_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            tools = BuiltinTools(Path(directory) / "agent")
            arguments = {
                "root": str(root),
                "changes": [{"path": "../escape.txt", "content": "no"}],
            }
            preview = tools.executor.execute(
                ToolCall("filesystem.preview_patch", arguments)
            )
            self.assertFalse(preview.success)
            self.assertIn("escapes", preview.errors[0])
            self.assertFalse((Path(directory) / "escape.txt").exists())

    def test_terminal_requires_permission_and_returns_real_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            tools = BuiltinTools(Path(directory) / "agent")
            arguments = {
                "cwd": directory,
                "command": [sys.executable, "-c", "print('agent-ok')"],
                "timeout": 10,
            }
            denied = tools.executor.execute(ToolCall("terminal.run", arguments))
            self.assertFalse(denied.success)
            token = tools.permissions.grant("terminal.run", arguments)
            result = tools.executor.execute(
                ToolCall("terminal.run", arguments, permission_token=token)
            )
            self.assertTrue(result.success)
            self.assertTrue(result.verified)
            self.assertEqual(result.output["exitCode"], 0)
            self.assertIn("agent-ok", result.output["stdout"])

    def test_running_terminal_tool_can_be_cancelled(self):
        with tempfile.TemporaryDirectory() as directory:
            tools = BuiltinTools(Path(directory) / "agent")
            arguments = {
                "cwd": directory,
                "command": [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(10)",
                ],
                "timeout": 30,
            }
            call_id = "cancel-terminal-test"
            token = tools.permissions.grant("terminal.run", arguments)
            results = []
            thread = threading.Thread(
                target=lambda: results.append(
                    tools.executor.execute(
                        ToolCall(
                            "terminal.run",
                            arguments,
                            call_id=call_id,
                            permission_token=token,
                        )
                    )
                )
            )
            thread.start()
            cancelled = False
            for _ in range(40):
                if tools.cancel(call_id):
                    cancelled = True
                    break
                time.sleep(0.05)
            thread.join(timeout=4)

            self.assertTrue(cancelled)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(results), 1)
            self.assertFalse(results[0].success)

    def test_read_only_action_can_be_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            (root / "needle.txt").write_text("find the needle", encoding="utf-8")
            tools = BuiltinTools(Path(directory) / "agent")
            result = tools.executor.execute(
                ToolCall(
                    "filesystem.search",
                    {"root": str(root), "query": "needle"},
                    call_id="search-action",
                )
            )
            replay = tools.replay("search-action")

            self.assertTrue(result.success)
            self.assertTrue(replay.success)
            self.assertEqual(replay.output["matches"][0]["path"], "needle.txt")


class ModelAndContextTests(unittest.TestCase):
    def test_router_prefers_coding_model_and_tracks_health(self):
        router = ModelRouter()
        route = router.route(
            (IntentType.CODING, IntentType.PROJECT_MODIFICATION),
            available_models=("Hermes-3", "Qwen2.5-Coder-7B"),
        )
        self.assertEqual(route.preferred, "Qwen2.5-Coder-7B")
        self.assertEqual(route.task_profile, "coding")
        router.record(
            route.preferred,
            success=True,
            latency_ms=1_000,
            prompt_tokens=500,
            generated_tokens=100,
            context_limit=4_000,
        )
        health = router.health()[route.preferred]
        self.assertEqual(health["success_rate"], 1.0)
        self.assertAlmostEqual(health["last_tokens_per_second"], 100.0)
        self.assertEqual(health["last_context_usage"], 0.125)

    def test_context_manager_compresses_old_irrelevant_history(self):
        history = [
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"old unrelated message {index} " + ("x" * 1_000),
            }
            for index in range(30)
        ]
        selected, metadata = ContextManager().prepare(
            history,
            "fix launch function",
            token_budget=2_048,
            project_context="src/main.py contains launch",
        )
        self.assertTrue(metadata["compressed"])
        self.assertGreater(metadata["omittedMessages"], 0)
        self.assertLess(len(selected), len(history))
        self.assertTrue(selected[0]["content"].startswith("Earlier conversation summary:"))


class AgentOrchestratorTests(unittest.TestCase):
    def test_request_pipeline_indexes_project_and_exposes_all_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            (project / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
            agent = AgentOrchestrator(Path(directory) / "runtime")
            context = agent.prepare_request(
                "Fix the Python project and run tests",
                history=({"role": "user", "content": "Use Python."},),
                project_root=str(project),
                selected_model="Qwen Coder",
                capabilities=("project.index", "terminal.run"),
            )

            self.assertEqual(context.project.root, str(project.resolve()))
            self.assertIn("Python", context.project.summary["languages"])
            self.assertIn("def main", context.project.relevant_files[0]["content"])
            self.assertEqual(context.model_route["task_profile"], "coding")
            result = agent.execute(context.request_id, ())
            self.assertTrue(result.success)
            agent.mark_ui_complete(context.request_id, response_present=True)
            snapshot = agent.snapshot()
            self.assertEqual(snapshot["activeStages"]["ui_update"], "completed")
            self.assertEqual(snapshot["activeStages"]["final_response"], "completed")
            self.assertGreaterEqual(snapshot["toolCount"], 15)
            self.assertTrue(snapshot["recentActions"])

    def test_runtime_snapshot_includes_agent_registry_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeServices(directory)
            runtime.start()
            context = runtime.agent.prepare_request("hello")
            runtime.agent.mark_ui_complete(context.request_id, response_present=True)
            snapshot = runtime.snapshot()
            runtime.shutdown()

            self.assertGreaterEqual(snapshot.agent["toolCount"], 15)
            self.assertEqual(snapshot.agent["activeIntents"], ["general_chat"])
            self.assertEqual(
                snapshot.agent["activeStages"]["final_response"],
                "completed",
            )


if __name__ == "__main__":
    unittest.main()

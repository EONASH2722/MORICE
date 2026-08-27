from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from morice.pc_control import (
    ActionRisk,
    ControlAction,
    ControlProviderRegistry,
    ControlResult,
    DesktopContext,
    FastActionRouter,
    PermissionBroker,
    PermissionCategory,
    PolicyMode,
    build_pc_control_registry,
)


@dataclass(frozen=True)
class FakeGrant:
    token: str


@dataclass(frozen=True)
class FakeCandidate:
    name: str
    target: str
    source: str = "fake"


@dataclass(frozen=True)
class FakeProcess:
    image_name: str
    pid: int
    session_name: str = "Console"
    memory_kb: int = 0


@dataclass(frozen=True)
class FakeWindow:
    handle: int
    title: str
    pid: int
    rect: tuple[int, int, int, int] = (0, 0, 800, 600)
    visible: bool = True
    minimized: bool = False
    maximized: bool = False


class FakeApplications:
    def __init__(self):
        self.processes = [FakeProcess("morice.exe", 1, memory_kb=50_000)]
        self.launches: list[str] = []

    def request_launch(self, target: str) -> FakeGrant:
        return FakeGrant(f"launch:{target}")

    def launch(self, target: str, token: str) -> FakeCandidate:
        if token != f"launch:{target}":
            raise PermissionError("bad fake application grant")
        name = Path(target).stem or target
        executable = target if target.endswith(".exe") else f"{target}.exe"
        self.launches.append(target)
        self.processes.append(FakeProcess(executable, 100 + len(self.launches)))
        return FakeCandidate(name, executable)

    def list_processes(self) -> list[FakeProcess]:
        return list(self.processes)


class FakeWindows:
    def __init__(self):
        self.items = [FakeWindow(10, "Notepad - notes.txt", 101)]
        self.active_handle: int | None = None
        self.calls: list[tuple[int, str]] = []

    def list_windows(self) -> list[FakeWindow]:
        return list(self.items)

    def request(self, handle: int, action: str, **parameters: Any) -> FakeGrant:
        return FakeGrant(f"window:{handle}:{action}")

    def control(
        self,
        handle: int,
        action: str,
        token: str,
        **parameters: Any,
    ) -> None:
        if token != f"window:{handle}:{action}":
            raise PermissionError("bad fake window grant")
        self.calls.append((handle, action))
        updated = []
        for item in self.items:
            if item.handle != handle:
                updated.append(item)
            elif action == "minimize":
                updated.append(replace(item, minimized=True, maximized=False))
            elif action == "focus":
                self.active_handle = handle
                updated.append(replace(item, minimized=False))
            elif action == "close":
                continue
            else:
                updated.append(item)
        self.items = updated


class FakeMedia:
    def __init__(self):
        self.state = {
            "playbackState": "playing",
            "currentTrack": "Track A",
            "volume": 40,
            "muted": False,
        }
        self.calls: list[str] = []

    def request(self, action: str) -> FakeGrant:
        return FakeGrant(f"media:{action}")

    def control(self, action: str, token: str) -> str:
        if token != f"media:{action}":
            raise PermissionError("bad fake media grant")
        self.calls.append(action)
        if action == "play-pause":
            self.state["playbackState"] = (
                "paused" if self.state["playbackState"] == "playing" else "playing"
            )
        elif action == "next":
            self.state["currentTrack"] = "Track B"
        elif action == "previous":
            self.state["currentTrack"] = "Track Previous"
        elif action == "volume-up":
            self.state["volume"] += 5
        elif action == "volume-down":
            self.state["volume"] -= 5
        elif action == "mute":
            self.state["muted"] = True
        return f"fake media {action}"

    def status(self) -> dict[str, Any]:
        return dict(self.state)


class FakeFiles:
    def __init__(self, root: Path):
        self.root = root
        self.searches: list[tuple[str, tuple[str, ...]]] = []
        self.opened: list[str] = []
        self.revealed: list[str] = []

    def search(self, query: str, roots: Any, *, limit: int = 80) -> list[dict[str, Any]]:
        normalized_roots = tuple(str(Path(root).resolve()) for root in roots)
        self.searches.append((query, normalized_roots))
        return [
            {
                "path": str((self.root / "chemistry.pdf").resolve()),
                "score": 42.0,
                "reasons": ["name matched"],
            }
        ][:limit]

    def preview(self, path: str) -> dict[str, str]:
        return {"path": path, "kind": "pdf"}

    def open(self, path: str) -> dict[str, str]:
        self.opened.append(path)
        return {"opened": path}

    def reveal(self, path: str) -> dict[str, str]:
        self.revealed.append(path)
        return {"revealed": path}


class FakeSystemMonitor:
    @staticmethod
    def sample() -> dict[str, Any]:
        return {
            "memory_total_gb": 16.0,
            "memory_available_gb": 6.0,
            "memory_percent": 62.5,
            "gpu_percent": 25.0,
            "vram_used_mb": 2_048.0,
            "vram_total_mb": 8_192.0,
        }


@dataclass(frozen=True)
class FakeScreenshot:
    path: str
    width: int = 1920
    height: int = 1080
    mode: str = "full"


class FakeScreenshots:
    def __init__(self, root: Path):
        self.root = root
        self.captures: list[str] = []

    def request(self, mode: str) -> FakeGrant:
        return FakeGrant(f"screenshot:{mode}")

    def capture(self, mode: str, token: str) -> FakeScreenshot:
        if token != f"screenshot:{mode}":
            raise PermissionError("bad fake screenshot grant")
        target = self.root / "screenshot.png"
        target.write_bytes(b"fake-png")
        self.captures.append(mode)
        return FakeScreenshot(str(target), mode=mode)


class FakeLayer:
    def __init__(self, root: Path):
        self.applications = FakeApplications()
        self.windows = FakeWindows()
        self.media = FakeMedia()
        self.files = FakeFiles(root)
        self.system_monitor = FakeSystemMonitor()
        self.screenshots = FakeScreenshots(root)


class FakeBrowser:
    def __init__(self):
        self.history = ["https://start.example"]
        self.reload_count = 0
        self.last_load_succeeded = True

    @property
    def current_url(self) -> str:
        return self.history[-1]

    def open(self, url: str) -> None:
        self.history.append(url)

    def back(self) -> None:
        if len(self.history) > 1:
            self.history.pop()

    def reload(self) -> None:
        self.reload_count += 1


class RecordingAdapter:
    adapter_id = "test.recording"

    def __init__(self, domain: str, verb: str):
        self.domain = domain
        self.verb = verb
        self.calls: list[ControlAction] = []

    def supports(self, action: ControlAction) -> bool:
        return action.domain == self.domain and action.verb == self.verb

    @staticmethod
    def availability(action: ControlAction | None = None) -> tuple[bool, str]:
        return True, ""

    def execute(self, action: ControlAction, context: DesktopContext) -> ControlResult:
        self.calls.append(action)
        return ControlResult(
            action.action_id,
            action.tool_id,
            True,
            True,
            "Fake action verified.",
            output={"target": action.target},
            adapter_id=self.adapter_id,
        )


def allow_defaults(*categories: PermissionCategory) -> dict[PermissionCategory, PolicyMode]:
    return {category: PolicyMode.ALLOW for category in categories}


class PermissionBrokerTests(unittest.TestCase):
    def test_category_policy_persists_and_corruption_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "permissions.json"
            broker = PermissionBroker(path)
            broker.set_policy(PermissionCategory.MEDIA_CONTROL, PolicyMode.ALLOW)

            restored = PermissionBroker(path)
            self.assertEqual(
                restored.policy(PermissionCategory.MEDIA_CONTROL), PolicyMode.ALLOW
            )
            self.assertEqual(
                restored.policy(PermissionCategory.FILE_WRITE), PolicyMode.ASK
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 1)

            path.write_text("not-json", encoding="utf-8")
            failed_closed = PermissionBroker(path)
            self.assertEqual(
                failed_closed.policy(PermissionCategory.MEDIA_CONTROL), PolicyMode.ASK
            )

    def test_ask_policy_accepts_only_an_exact_one_use_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = PermissionBroker(Path(directory) / "permissions.json")
            action = ControlAction(
                "media",
                "pause",
                "active media",
                permissions=(PermissionCategory.MEDIA_CONTROL,),
            )
            changed = replace(action, target="different media")

            self.assertTrue(broker.authorize(action).confirmation_required)
            wrong_grant = broker.request_confirmation(action)
            self.assertFalse(broker.authorize(changed, wrong_grant.token).allowed)
            self.assertFalse(broker.authorize(action, wrong_grant.token).allowed)

            grant = broker.request_confirmation(action)
            self.assertTrue(broker.authorize(action, grant.token).allowed)
            self.assertFalse(broker.authorize(action, grant.token).allowed)

            same_parameters_new_action = ControlAction(
                "media",
                "pause",
                "active media",
                permissions=(PermissionCategory.MEDIA_CONTROL,),
            )
            instance_grant = broker.request_confirmation(action)
            self.assertFalse(
                broker.authorize(same_parameters_new_action, instance_grant.token).allowed
            )

    def test_destructive_action_requires_exact_confirmation_even_when_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = PermissionBroker(
                Path(directory) / "permissions.json",
                defaults=allow_defaults(PermissionCategory.FILE_WRITE),
            )
            action = ControlAction(
                "file",
                "delete",
                "notes.txt",
                permissions=(PermissionCategory.FILE_WRITE,),
                risk=ActionRisk.DESTRUCTIVE,
            )

            denied = broker.authorize(action)
            self.assertFalse(denied.allowed)
            self.assertTrue(denied.confirmation_required)
            grant = broker.request_confirmation(action)
            self.assertTrue(broker.authorize(action, grant.token).allowed)

    def test_deny_policy_overrides_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = PermissionBroker(
                Path(directory) / "permissions.json",
                defaults={PermissionCategory.SCREEN_ACCESS: PolicyMode.DENY},
            )
            action = ControlAction(
                "computer",
                "interact",
                "screen",
                permissions=(PermissionCategory.SCREEN_ACCESS,),
                risk=ActionRisk.SENSITIVE,
            )
            grant = broker.request_confirmation(action)
            decision = broker.authorize(action, grant.token)

            self.assertFalse(decision.allowed)
            self.assertEqual(
                decision.missing_permissions, (PermissionCategory.SCREEN_ACCESS,)
            )


class FastActionRouterTests(unittest.TestCase):
    def test_requested_natural_media_and_safe_window_phrases_route_honestly(self):
        router = FastActionRouter()

        music = router.route("Put some music on")
        spotify = router.route("Play Starboy on Spotify")
        recent = router.route("Open that thing I was coding yesterday")
        move = router.route("Move that window over there")
        close = router.route("Close everything except MORICE")

        self.assertEqual(music.action.tool_id, "media.resume")
        self.assertEqual(music.action.target, "Amazon Music")
        self.assertEqual(music.route_type, "FAST_TOOL")
        self.assertEqual(music.model_invocations, 0)
        self.assertEqual(spotify.action.tool_id, "browser.search")
        self.assertEqual(spotify.action.arguments["site"], "open.spotify.com")
        self.assertEqual(recent.action.tool_id, "file.open_recent")
        self.assertIsNone(move.action)
        self.assertIn("where", move.clarification.casefold())
        self.assertEqual(close.action.tool_id, "application.close_others")
        self.assertEqual(close.action.risk, ActionRisk.DESTRUCTIVE)

    def test_application_and_media_routine_language_uses_fast_path(self):
        context = DesktopContext(last_application="Notepad", current_media="Track A")
        router = FastActionRouter(context)

        opened = router.route("Open Notepad")
        focused = router.route("Focus it")
        minimized = router.route("Minimize it")
        paused = router.route("Pause it")
        skipped = router.route("Skip it")
        louder = router.route("Little louder")

        self.assertEqual(opened.action.tool_id, "application.open")
        self.assertEqual(focused.action.target, "Notepad")
        self.assertEqual(minimized.action.tool_id, "application.minimize")
        self.assertEqual(paused.action.tool_id, "media.pause")
        self.assertEqual(skipped.action.tool_id, "media.next")
        self.assertEqual(louder.action.arguments["direction"], "up")
        self.assertFalse(louder.escalate_to_model)
        self.assertGreaterEqual(louder.duration_ms, 0)

    def test_file_search_and_pronoun_open_reveal_use_context(self):
        context = DesktopContext()
        router = FastActionRouter(context)
        found = router.route("Find my chemistry PDF")
        self.assertEqual(found.action.tool_id, "file.search")

        context.last_domain = "file"
        context.last_file = r"C:\Docs\chemistry.pdf"
        opened = router.route("Open it")
        revealed = router.route("Show it in Explorer")
        self.assertEqual(opened.action.target, context.last_file)
        self.assertEqual(opened.action.tool_id, "file.open")
        self.assertEqual(revealed.action.tool_id, "file.reveal")

    def test_contextual_site_search_and_result_reference_are_structured(self):
        context = DesktopContext(last_error="CUDA out of memory")
        router = FastActionRouter(context)
        search = router.route("Search Reddit for this issue")

        self.assertEqual(search.action.tool_id, "browser.search")
        self.assertEqual(search.action.target, "CUDA out of memory")
        self.assertEqual(search.action.arguments["site"], "reddit")

        context.web_results = [
            {"url": "https://example.com/one", "title": "One"},
            {"url": "https://example.com/two", "title": "Two"},
        ]
        opened = router.route("Open the first useful result")
        self.assertEqual(opened.action.tool_id, "browser.open")
        self.assertEqual(opened.action.target, "https://example.com/one")

        contextual = router.route(
            "Search Reddit for people having this CUDA issue"
        )
        self.assertEqual(
            contextual.action.target,
            "people having CUDA out of memory",
        )

    def test_system_status_routes_ram_gpu_and_process_requests(self):
        router = FastActionRouter()

        ram = router.route("What's using my RAM?")
        gpu = router.route("Show GPU usage")
        processes = router.route("Show running processes")

        self.assertEqual(ram.action.arguments["metric"], "ram_usage")
        self.assertEqual(gpu.action.arguments["metric"], "gpu")
        self.assertEqual(processes.action.arguments["metric"], "processes")
        self.assertEqual(
            ram.action.permissions, (PermissionCategory.READ_SYSTEM_STATE,)
        )

    def test_amazon_music_fast_routes_are_structured_and_never_call_a_model(self):
        router = FastActionRouter(default_music_provider="Amazon Music")
        requests = {
            "What's my RAM usage?": "system.status",
            "What is my current RAM usage?": "system.status",
            "Take a screenshot.": "screenshot.capture",
            "Open Amazon Music and play Dark Red by Steve Lacy": "media.play_query",
            "Play Starboy": "media.play_query",
            "Pause": "media.pause",
            "Resume": "media.resume",
            "Next song": "media.next",
            "Previous song": "media.previous",
            "Restart this song": "media.restart",
            "Set volume to 30%": "media.set_volume",
            "What song is playing?": "media.status",
            "Close Amazon Music": "application.close",
            "Open music": "application.open",
        }

        decisions = {text: router.route(text) for text in requests}

        for text, tool_id in requests.items():
            with self.subTest(text=text):
                decision = decisions[text]
                self.assertIsNotNone(decision.action, decision.reason)
                self.assertEqual(decision.action.tool_id, tool_id)
                self.assertEqual(decision.route_type, "FAST_TOOL")
                self.assertEqual(decision.model_invocations, 0)
                self.assertFalse(decision.escalate_to_model)
        self.assertEqual(
            decisions["Play Starboy"].action.arguments["provider"],
            "Amazon Music",
        )
        self.assertEqual(
            decisions["Open Amazon Music and play Dark Red by Steve Lacy"]
            .action.arguments["query"],
            "dark red by steve lacy",
        )

    def test_unnamed_playlist_clarifies_without_model_escalation(self):
        decision = FastActionRouter().route("Play my playlist")

        self.assertIsNone(decision.action)
        self.assertFalse(decision.escalate_to_model)
        self.assertEqual(decision.route_type, "FAST_TOOL")
        self.assertIn("which", decision.clarification.casefold())

    def test_explicit_pause_and_resume_music_are_fast_tools(self):
        router = FastActionRouter(default_music_provider="Amazon Music")

        paused = router.route("Pause music")
        resumed = router.route("Resume the music")

        self.assertEqual(paused.route_type, "FAST_TOOL")
        self.assertEqual(paused.action.tool_id, "media.pause")
        self.assertEqual(paused.model_invocations, 0)
        self.assertFalse(paused.escalate_to_model)
        self.assertEqual(resumed.route_type, "FAST_TOOL")
        self.assertEqual(resumed.action.tool_id, "media.resume")
        self.assertEqual(resumed.model_invocations, 0)
        self.assertFalse(resumed.escalate_to_model)

    def test_browser_back_uses_recent_domain_and_ambiguity_escalates(self):
        browser_context = DesktopContext(
            last_domain="browser", current_url="https://example.com/two"
        )
        browser_back = FastActionRouter(browser_context).route("Go back")
        self.assertEqual(browser_back.action.tool_id, "browser.back")

        media_context = DesktopContext(last_domain="media", current_media="Track A")
        media_back = FastActionRouter(media_context).route("Go back")
        self.assertEqual(media_back.action.tool_id, "media.previous")

        ambiguous = FastActionRouter().route("Go back")
        self.assertTrue(ambiguous.escalate_to_model)
        self.assertIn("browser", ambiguous.clarification.casefold())

    def test_missing_referent_and_complex_request_escalate_without_action(self):
        router = FastActionRouter()
        ambiguous = router.route("Minimize it")
        complex_request = router.route(
            "Find the project, open it, run the tests, and figure out why it crashes"
        )

        self.assertIsNone(ambiguous.action)
        self.assertTrue(ambiguous.escalate_to_model)
        self.assertIn("which application", ambiguous.clarification.casefold())
        self.assertIsNone(complex_request.action)
        self.assertTrue(complex_request.escalate_to_model)


class AdapterRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "chemistry.pdf").write_bytes(b"%PDF-fake")
        self.context = DesktopContext()
        categories = tuple(PermissionCategory)
        self.broker = PermissionBroker(
            self.root / "permissions.json",
            defaults=allow_defaults(*categories),
        )
        self.layer = FakeLayer(self.root)
        self.browser = FakeBrowser()
        self.search_queries: list[str] = []

        def search(query: str) -> list[dict[str, str]]:
            self.search_queries.append(query)
            return [
                {
                    "title": "CUDA discussion",
                    "snippet": "A useful result",
                    "url": "https://www.reddit.com/r/cuda/example",
                }
            ]

        self.registry = build_pc_control_registry(
            self.layer,
            self.broker,
            context=self.context,
            file_roots=(self.root,),
            browser=self.browser,
            web_search=search,
        )
        self.router = FastActionRouter(self.context)

    def tearDown(self):
        self.temporary.cleanup()

    def execute_text(self, text: str) -> ControlResult:
        decision = self.router.route(text)
        self.assertIsNotNone(decision.action, decision.reason)
        return self.registry.execute(decision.action)

    def test_application_window_and_media_adapters_verify_fake_state(self):
        opened = self.execute_text("Open Notepad")
        focused = self.execute_text("Focus it")
        minimized = self.execute_text("Minimize it")
        paused = self.execute_text("Pause it")
        skipped = self.execute_text("Skip it")
        louder = self.execute_text("Little louder")

        self.assertTrue(opened.success)
        self.assertTrue(opened.verified)
        self.assertTrue(focused.verified)
        self.assertTrue(minimized.verified)
        self.assertTrue(paused.verified)
        self.assertTrue(skipped.verified)
        self.assertTrue(louder.verified)
        self.assertEqual(self.layer.windows.active_handle, 10)
        self.assertIn("play-pause", self.layer.media.calls)
        self.assertIn("total", paused.timings_ms)
        self.assertIn("route", paused.timings_ms)

    def test_file_adapter_search_open_and_reveal_never_calls_the_os(self):
        found = self.execute_text("Find my chemistry PDF")
        opened = self.execute_text("Open it")
        revealed = self.execute_text("Show it in Explorer")

        expected = str((self.root / "chemistry.pdf").resolve())
        self.assertTrue(found.verified)
        self.assertEqual(self.context.last_file, expected)
        self.assertTrue(opened.verified)
        self.assertTrue(revealed.verified)
        self.assertEqual(self.layer.files.opened, [expected])
        self.assertEqual(self.layer.files.revealed, [expected])

    def test_file_adapter_rejects_existing_paths_outside_approved_roots(self):
        approved = self.root / "approved"
        approved.mkdir()
        outside = self.root / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        registry = build_pc_control_registry(
            self.layer,
            self.broker,
            context=DesktopContext(),
            file_roots=(approved,),
        )
        action = ControlAction(
            "file",
            "open",
            str(outside),
            permissions=(PermissionCategory.FILE_READ,),
        )

        result = registry.execute(action)

        self.assertFalse(result.success)
        self.assertIn("outside approved locations", result.errors[0])
        self.assertEqual(self.layer.files.opened, [])

    def test_web_search_result_open_and_browser_verification_are_stateful(self):
        self.context.remember_error("CUDA out of memory")
        searched = self.execute_text("Search Reddit for this issue")
        opened = self.execute_text("Open the first result")
        reloaded = self.execute_text("Reload the page")

        self.assertTrue(searched.verified)
        self.assertEqual(
            self.search_queries, ["site:reddit.com CUDA out of memory"]
        )
        self.assertTrue(opened.verified)
        self.assertEqual(
            self.browser.current_url,
            "https://www.reddit.com/r/cuda/example",
        )
        self.assertTrue(reloaded.verified)
        self.assertEqual(self.browser.reload_count, 1)

    def test_system_adapter_returns_observed_process_and_gpu_state(self):
        processes = self.execute_text("Show running processes")
        gpu = self.execute_text("Show GPU usage")

        self.assertTrue(processes.verified)
        self.assertEqual(processes.output["processes"][0]["image_name"], "morice.exe")
        self.assertTrue(gpu.verified)
        self.assertEqual(gpu.output["gpu_percent"], 25.0)

    def test_screenshot_fast_path_captures_and_verifies_the_output_file(self):
        captured = self.execute_text("Take a screenshot.")

        self.assertTrue(captured.success)
        self.assertTrue(captured.verified)
        self.assertEqual(captured.tool_id, "screenshot.capture")
        self.assertEqual(self.layer.screenshots.captures, ["full"])
        self.assertTrue(Path(captured.output["path"]).is_file())

    def test_permission_denial_prevents_adapter_execution(self):
        self.broker.set_policy(PermissionCategory.MEDIA_CONTROL, PolicyMode.DENY)
        decision = self.router.route("Pause it")
        before = list(self.layer.media.calls)
        result = self.registry.execute(decision.action)

        self.assertFalse(result.success)
        self.assertEqual(
            result.missing_permissions, (PermissionCategory.MEDIA_CONTROL,)
        )
        self.assertEqual(self.layer.media.calls, before)
        self.assertIn("authorization", result.timings_ms)

    def test_registry_enforces_destructive_confirmation_before_adapter(self):
        adapter = RecordingAdapter("file", "delete")
        registry = ControlProviderRegistry(self.broker)
        registry.register(adapter, priority=500)
        action = ControlAction(
            "file",
            "delete",
            str(self.root / "chemistry.pdf"),
            permissions=(PermissionCategory.FILE_WRITE,),
            risk=ActionRisk.DESTRUCTIVE,
        )

        blocked = registry.execute(action)
        self.assertFalse(blocked.success)
        self.assertTrue(blocked.confirmation_required)
        self.assertEqual(adapter.calls, [])

        grant = self.broker.request_confirmation(action)
        completed = registry.execute(action, confirmation_token=grant.token)
        replay = registry.execute(action, confirmation_token=grant.token)
        self.assertTrue(completed.success)
        self.assertTrue(completed.verified)
        self.assertEqual(len(adapter.calls), 1)
        self.assertFalse(replay.success)
        self.assertEqual(len(adapter.calls), 1)

    def test_close_everything_except_morice_requires_confirmation_and_verifies(self):
        self.layer.windows.items.append(FakeWindow(11, "MORICE", 1))
        decision = self.router.route("Close everything except MORICE")

        blocked = self.registry.execute(decision.action)
        self.assertTrue(blocked.confirmation_required)
        grant = self.broker.request_confirmation(decision.action)
        completed = self.registry.execute(
            decision.action,
            confirmation_token=grant.token,
        )

        self.assertTrue(completed.success)
        self.assertTrue(completed.verified)
        self.assertEqual([item.title for item in self.layer.windows.items], ["MORICE"])

    def test_computer_use_is_honestly_unavailable(self):
        action = ControlAction(
            "computer",
            "interact",
            "legacy application",
            permissions=(
                PermissionCategory.SCREEN_ACCESS,
                PermissionCategory.APPLICATION_CONTROL,
            ),
            risk=ActionRisk.SENSITIVE,
        )

        result = self.registry.execute(action)
        capability = next(
            item
            for item in self.registry.capabilities()
            if item["adapterId"] == "computer_use.unavailable"
        )

        self.assertFalse(result.success)
        self.assertFalse(result.verified)
        self.assertIn("blind screen coordinates", result.message)
        self.assertFalse(capability["available"])
        self.assertIn("observed-state", capability["reason"])


if __name__ == "__main__":
    unittest.main()

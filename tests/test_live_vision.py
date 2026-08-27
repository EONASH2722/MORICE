from __future__ import annotations

import io
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from morice.live_vision import (
    FrameManager,
    LlamaCppVisionProvider,
    LiveVisionRuntime,
    VisionProviderStatus,
    VisionResult,
    VisualMemory,
    _parse_provider_json,
    assess_frame_quality,
    visual_follow_up,
    visual_intent,
)


def jpeg(level: int = 128, *, detail: bool = True) -> bytes:
    image = Image.new("RGB", (160, 120), (level, level, level))
    if detail:
        pixels = image.load()
        for y in range(20, 100):
            for x in range(20, 140):
                if (x // 8 + y // 8) % 2:
                    detail_level = min(255, level + 90)
                    pixels[x, y] = (detail_level, detail_level, detail_level)
                else:
                    detail_level = max(0, level - 80)
                    pixels[x, y] = (detail_level, detail_level, detail_level)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


class FakeProvider:
    name = "fake-vision"

    def __init__(self, *, result_text: str = "A blue test connector is visible."):
        self.result_text = result_text
        self.calls = []
        self.stopped = False

    def status(self):
        return VisionProviderStatus(self.name, True, True, "ready", "fake", 0)

    def prewarm(self):
        return self.status()

    def analyze(self, frame, prompt, *, cancel_event, request_id):
        self.calls.append((frame, prompt, request_id))
        if cancel_event.is_set():
            return VisionResult.failure(request_id, frame, "cancelled", "cancelled")
        return VisionResult(
            request_id=request_id,
            frame_id=frame.frame_id,
            frame_timestamp=frame.timestamp,
            provider=self.name,
            success=True,
            summary=self.result_text,
            confidence=0.82,
            quality=frame.quality,
        )

    def shutdown(self):
        self.stopped = True


class LiveVisionTests(unittest.TestCase):
    def test_packaged_vision_pair_is_preferred_for_offline_portable_use(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package"
            package.mkdir()
            bundled = package / "assets" / "vision"
            bundled.mkdir(parents=True)
            model = bundled / "SmolVLM2-500M-Video-Instruct-Q8_0.gguf"
            projector = bundled / "mmproj-SmolVLM2-500M-Video-Instruct-Q8_0.gguf"
            model.touch()
            projector.touch()
            with (
                patch("morice.live_vision.local_data_dir", return_value=root / "data"),
                patch("morice.live_vision.__file__", str(package / "live_vision.py")),
            ):
                provider = LlamaCppVisionProvider(server_path=root / "server.exe")

        self.assertEqual(provider.model_path, model.resolve())
        self.assertEqual(provider.mmproj_path, projector.resolve())

    def test_default_server_uses_shared_packaged_binary_resolver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packaged_server = root / "package" / "llama-server.exe"
            packaged_server.parent.mkdir(parents=True)
            packaged_server.touch()
            with (
                patch("morice.live_vision.local_data_dir", return_value=root),
                patch(
                    "morice.live_vision.selected_server_path",
                    return_value=str(packaged_server),
                ),
            ):
                provider = LlamaCppVisionProvider()

        self.assertEqual(provider.server_path, packaged_server.resolve())

    def test_server_command_uses_verified_smolvlm_chat_template_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server = root / "llama-server.exe"
            model = root / "vision.gguf"
            projector = root / "mmproj.gguf"
            for item in (server, model, projector):
                item.touch()
            process = Mock()
            process.poll.return_value = None
            factory = Mock(return_value=process)
            provider = LlamaCppVisionProvider(
                server_path=server,
                model_path=model,
                mmproj_path=projector,
                cache_dir=root / "cache",
                process_factory=factory,
            )
            with patch.object(
                provider, "_server_ready", side_effect=(False, False, True)
            ):
                provider._ensure_server()

        command = factory.call_args.args[0]
        self.assertIn("--no-jinja", command)
        self.assertEqual(command[command.index("--chat-template") + 1], "smolvlm")
        self.assertIn("--json-schema", command)

    def test_provider_json_rejects_unrelated_nested_object(self):
        with self.assertRaisesRegex(ValueError, "unexpected JSON schema"):
            _parse_provider_json('{"data":{"title":"unrelated"}}')

    def test_provider_json_accepts_only_complete_grounding_schema(self):
        parsed = _parse_provider_json(
            '{"summary":"A desk is visible.","extracted_text":"",'
            '"confidence":0.7,"uncertainty":"","regions":[]}'
        )

        self.assertEqual(parsed["summary"], "A desk is visible.")

    def test_installed_500m_pair_is_preferred_over_the_2b_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            small = root / "models" / "vision" / "SmolVLM2-500M-Video-Instruct-GGUF"
            large = root / "models" / "vision" / "SmolVLM2-2.2B-Instruct-GGUF"
            small.mkdir(parents=True)
            large.mkdir(parents=True)
            small_model = small / "SmolVLM2-500M-Video-Instruct-Q8_0.gguf"
            small_projector = small / "mmproj-SmolVLM2-500M-Video-Instruct-Q8_0.gguf"
            large_model = large / "SmolVLM2-2.2B-Instruct-Q4_K_M.gguf"
            large_projector = large / "mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf"
            for item in (small_model, small_projector, large_model, large_projector):
                item.touch()
            with patch("morice.live_vision.local_data_dir", return_value=root):
                provider = LlamaCppVisionProvider()

        self.assertEqual(provider.model_path, small_model.resolve())
        self.assertEqual(provider.mmproj_path, small_projector.resolve())

    def test_frame_manager_retains_only_latest_frame_and_scene_metric(self):
        manager = FrameManager()
        first = manager.publish(jpeg(80), width=160, height=120)
        second = manager.publish(jpeg(180), width=160, height=120)

        self.assertNotEqual(first.frame_id, second.frame_id)
        self.assertEqual(manager.latest().frame_id, second.frame_id)
        diagnostics = manager.diagnostics()
        self.assertEqual(diagnostics["framesPublished"], 2)
        self.assertEqual(diagnostics["framesReplaced"], 1)
        self.assertGreater(diagnostics["sceneChange"], 0.0)

    def test_stale_frame_is_never_analyzed(self):
        manager = FrameManager(max_frame_age_seconds=0.5)
        manager.publish(
            jpeg(),
            width=160,
            height=120,
            captured_at=datetime.now(timezone.utc) - timedelta(seconds=5),
            monotonic_ns=time.monotonic_ns() - 5_000_000_000,
        )
        provider = FakeProvider()
        runtime = LiveVisionRuntime(provider, frame_manager=manager)
        try:
            result = runtime.analyze_latest("What is this?").result(timeout=2)
        finally:
            runtime.shutdown()

        self.assertFalse(result.success)
        self.assertEqual(result.failure_code, "no-fresh-frame")
        self.assertEqual(provider.calls, [])

    def test_dark_frame_is_rejected_before_provider(self):
        provider = FakeProvider()
        runtime = LiveVisionRuntime(provider)
        runtime.publish_frame(jpeg(2, detail=False), width=160, height=120)
        try:
            result = runtime.analyze_latest("Read this").result(timeout=2)
        finally:
            runtime.shutdown()

        self.assertFalse(result.success)
        self.assertEqual(result.failure_code, "too-dark")
        self.assertIn("too dark", result.message.lower())
        self.assertEqual(provider.calls, [])

    def test_success_is_timestamped_and_saved_without_raw_image(self):
        provider = FakeProvider()
        runtime = LiveVisionRuntime(provider)
        frame = runtime.publish_frame(jpeg(), width=160, height=120, camera_id="camera-1")
        try:
            result = runtime.analyze_latest("What am I holding?", request_id="vision-1").result(timeout=2)
            remembered = runtime.memory.recall()
        finally:
            runtime.shutdown()

        self.assertTrue(result.success)
        self.assertEqual(result.request_id, "vision-1")
        self.assertEqual(result.frame_id, frame.frame_id)
        self.assertEqual(result.frame_timestamp, frame.timestamp)
        self.assertIsNotNone(remembered)
        self.assertNotIn("jpeg", remembered.__dict__)
        self.assertIn("successfully processed actual camera frame", result.context_text())

    def test_disabled_runtime_does_not_accept_or_analyze_frames(self):
        runtime = LiveVisionRuntime(FakeProvider(), enabled=False)
        with self.assertRaisesRegex(RuntimeError, "disabled"):
            runtime.publish_frame(jpeg(), width=160, height=120)
        result = runtime.analyze_latest("What is this?").result(timeout=1)
        self.assertEqual(result.failure_code, "vision-disabled")
        runtime.shutdown()

    def test_visual_memory_expires(self):
        memory = VisualMemory(ttl_seconds=5)
        result = VisionResult(
            "request",
            "frame",
            datetime.now(timezone.utc).isoformat(),
            "fake",
            True,
            summary="object",
        )
        memory.remember(result)
        self.assertIsNotNone(memory.recall())
        memory._stored_ns = time.monotonic_ns() - 6_000_000_000
        self.assertIsNone(memory.recall())

    def test_quality_and_intent_helpers_are_conservative(self):
        quality = assess_frame_quality(jpeg())
        self.assertGreater(quality.brightness, 20)
        self.assertTrue(visual_intent("MORICE, what am I holding?"))
        self.assertTrue(visual_intent("Can you read this label?"))
        self.assertFalse(visual_intent("Play some music"))
        self.assertTrue(visual_follow_up("Search it online"))


if __name__ == "__main__":
    unittest.main()

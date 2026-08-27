from __future__ import annotations

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from morice.realtime_intelligence import (
    BackgroundMind,
    CancellationToken,
    LatencyRegistry,
    LatencyStage,
    LatencyTrace,
    MemoryCandidate,
    ModelTier,
    RealtimeIntelligence,
    RequestCancelledError,
    SemanticChunker,
    TieredModelRouter,
    rank_memories,
)


class LatencyTraceTests(unittest.TestCase):
    def test_t0_through_t12_are_ordered_and_have_short_aliases(self) -> None:
        stages = list(LatencyStage)
        self.assertEqual(13, len(stages))
        self.assertIs(LatencyStage.T0, LatencyStage.SPEECH_DETECTED)
        self.assertIs(LatencyStage.T12, LatencyStage.SPEECH_COMPLETE)

        origin = 1_000_000_000
        trace = LatencyTrace("request-1", created_monotonic_ns=origin)
        for index, stage in enumerate(stages):
            self.assertTrue(trace.mark(stage, at_ns=origin + index * 1_000_000))

        snapshot = trace.snapshot()
        self.assertEqual([stage.value for stage in stages], list(snapshot["stages"]))
        self.assertEqual(12.0, snapshot["intervals"]["totalResponseMs"])
        self.assertEqual(1.0, snapshot["intervals"]["timeToFirstTokenMs"])
        self.assertTrue(snapshot["generationComplete"])
        self.assertTrue(snapshot["speechComplete"])

    def test_marks_are_first_write_wins_and_chronologically_consistent(self) -> None:
        trace = LatencyTrace("request-2", created_monotonic_ns=0)
        self.assertTrue(trace.mark(LatencyStage.T6, at_ns=600))
        self.assertFalse(trace.mark(LatencyStage.T6, at_ns=601))
        self.assertFalse(trace.mark(LatencyStage.T5, at_ns=700))
        self.assertTrue(trace.mark(LatencyStage.T5, at_ns=500))
        self.assertFalse(trace.mark(LatencyStage.T4, at_ns=550))
        self.assertFalse(trace.mark(LatencyStage.T0, at_ns=-1))

    def test_counter_updates_are_thread_safe(self) -> None:
        trace = LatencyTrace("request-3")

        def increment_many() -> None:
            for _ in range(250):
                trace.increment("tokens")

        threads = [threading.Thread(target=increment_many) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(2_000, trace.snapshot()["counters"]["tokens"])

    def test_registry_is_bounded_and_reports_interpolated_percentiles(self) -> None:
        registry = LatencyRegistry(max_traces=4)
        for index, duration_ms in enumerate((20, 40, 60, 80, 100)):
            trace = registry.begin(
                f"request-{index}", created_monotonic_ns=1_000_000
            )
            trace.mark(LatencyStage.T0, at_ns=1_000_000)
            trace.mark(
                LatencyStage.T12,
                at_ns=1_000_000 + duration_ms * 1_000_000,
            )

        self.assertIsNone(registry.get("request-0"))
        self.assertEqual(4, len(registry.recent()))
        metric = registry.metric(LatencyStage.T0, LatencyStage.T12)
        self.assertEqual(4, metric["count"])
        self.assertEqual(70.0, metric["p50Ms"])
        self.assertEqual(97.0, metric["p95Ms"])

    def test_named_events_measure_typed_tool_and_parallel_audio_paths(self) -> None:
        origin = 5_000_000_000
        trace = LatencyTrace("typed-tool", created_monotonic_ns=origin)
        self.assertTrue(trace.mark_event("text_submitted", at_ns=origin))
        self.assertTrue(trace.mark_event("route_completed", at_ns=origin + 2_000_000))
        self.assertTrue(
            trace.mark_event("tool_execution_started", at_ns=origin + 3_000_000)
        )
        self.assertTrue(
            trace.mark_event("tool_execution_finished", at_ns=origin + 8_000_000)
        )
        self.assertTrue(
            trace.mark_event("fast_response_visible", at_ns=origin + 9_000_000)
        )

        snapshot = trace.snapshot()
        self.assertEqual(2.0, snapshot["intervals"]["textSubmitToRouteMs"])
        self.assertEqual(5.0, snapshot["intervals"]["toolExecutionMs"])
        self.assertEqual(9.0, snapshot["intervals"]["fastCommandTotalMs"])

    def test_generation_can_complete_before_parallel_audio_arrives(self) -> None:
        origin = 8_000_000_000
        trace = LatencyTrace("parallel", created_monotonic_ns=origin)
        self.assertTrue(
            trace.mark(LatencyStage.GENERATION_COMPLETE, at_ns=origin + 2_000_000)
        )
        self.assertTrue(
            trace.mark(LatencyStage.FIRST_AUDIO_GENERATED, at_ns=origin + 5_000_000)
        )


class TieredModelRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = TieredModelRouter(
            {
                ModelTier.REFLEX: "tiny.gguf",
                ModelTier.GENERAL: "general.gguf",
                ModelTier.DEEP: "deep.gguf",
            }
        )

    def test_routes_reflex_general_and_deep_profiles(self) -> None:
        command = self.router.route("open Spotify")
        self.assertEqual(ModelTier.REFLEX, command.tier)
        self.assertTrue(command.host_action)
        self.assertEqual("tiny.gguf", command.model_id)

        calculation = self.router.route("20% of 450")
        self.assertEqual(ModelTier.REFLEX, calculation.tier)
        self.assertTrue(calculation.host_action)

        conversation = self.router.route("Tell me a short story about rain")
        self.assertEqual(ModelTier.GENERAL, conversation.tier)

        deep = self.router.route("Audit this repository for a race condition")
        self.assertEqual(ModelTier.DEEP, deep.tier)
        self.assertEqual("deep.gguf", deep.model_id)

    def test_partial_destructive_commands_are_never_actions_or_prefetches(self) -> None:
        decision = self.router.route("delete the temp folder", partial=True)
        self.assertEqual(ModelTier.REFLEX, decision.tier)
        self.assertFalse(decision.host_action)
        self.assertFalse(decision.safe_to_prefetch)
        self.assertTrue(decision.requires_final)
        self.assertIn("held", decision.reason)

    def test_partial_read_only_command_may_prefetch_but_not_execute(self) -> None:
        decision = self.router.route("show GPU usage", partial=True)
        self.assertFalse(decision.host_action)
        self.assertTrue(decision.safe_to_prefetch)
        self.assertTrue(decision.requires_final)

    def test_explicit_overrides_win_and_are_visible(self) -> None:
        decision = self.router.route(
            "hello",
            override_tier="deep",
            override_model="operator-selected.gguf",
        )
        self.assertEqual(ModelTier.DEEP, decision.tier)
        self.assertEqual("operator-selected.gguf", decision.model_id)
        self.assertTrue(decision.explicit_override)

    def test_missing_tier_uses_configured_fallback(self) -> None:
        router = TieredModelRouter({ModelTier.GENERAL: "only.gguf"})
        decision = router.route("Audit this repository for deadlocks")
        self.assertEqual(ModelTier.DEEP, decision.tier)
        self.assertEqual("only.gguf", decision.model_id)
        self.assertIn("fallback", decision.reason)


class CancellationTokenTests(unittest.TestCase):
    def test_cancellation_is_idempotent_and_epoch_scoped(self) -> None:
        token = CancellationToken(7)
        self.assertTrue(token.matches(7))
        self.assertFalse(token.matches(8))
        self.assertTrue(token.cancel("barge-in"))
        self.assertFalse(token.cancel("second reason"))
        self.assertEqual("barge-in", token.reason)
        self.assertFalse(token.matches(7))
        self.assertTrue(token.wait(0))
        with self.assertRaisesRegex(RequestCancelledError, "barge-in"):
            token.raise_if_cancelled()


class SemanticChunkerTests(unittest.TestCase):
    def test_fragmented_sentence_and_abbreviation_are_not_split_early(self) -> None:
        chunker = SemanticChunker()
        self.assertEqual((), chunker.feed("Dr."))
        self.assertEqual((), chunker.feed(" Ada shipped version 2."))
        chunks = chunker.feed("1. It works well.")
        self.assertEqual(2, len(chunks))
        self.assertEqual("Dr. Ada shipped version 2.1.", chunks[0].display_text)
        self.assertEqual("It works well.", chunks[1].spoken_text)

    def test_markdown_link_target_does_not_create_a_false_boundary(self) -> None:
        chunker = SemanticChunker()
        self.assertEqual((), chunker.feed("Read [the guide](https://docs."))
        chunks = chunker.feed("example.com/api). It is useful.")
        self.assertEqual(2, len(chunks))
        self.assertIn("https://docs.example.com/api", chunks[0].display_text)
        self.assertEqual("Read the guide.", chunks[0].spoken_text)

    def test_fenced_code_remains_displayable_but_is_not_spoken(self) -> None:
        fence = chr(96) * 3
        chunker = SemanticChunker(min_clause_chars=12)
        self.assertEqual(
            (),
            chunker.feed(fence + "python\nprint('secret value')\n"),
        )
        chunks = chunker.feed(fence + " The result follows.")
        self.assertGreaterEqual(len(chunks), 1)
        display = " ".join(chunk.display_text for chunk in chunks)
        spoken = " ".join(chunk.spoken_text for chunk in chunks)
        self.assertIn("secret value", display)
        self.assertNotIn("secret value", spoken)
        self.assertIn("Code block omitted", spoken)

    def test_spoken_form_cleans_markdown_images_inline_code_and_urls(self) -> None:
        tick = chr(96)
        source = (
            "## Result\n- Use "
            + tick
            + "fast_mode"
            + tick
            + " with ![chart](chart.png) at https://example.com/docs"
        )
        spoken = SemanticChunker.to_spoken(source)
        self.assertNotIn("##", spoken)
        self.assertNotIn("https://", spoken)
        self.assertIn("fast_mode", spoken)
        self.assertIn("Image: chart", spoken)
        self.assertIn("a link", spoken)

    def test_chunk_size_is_bounded_at_a_word_boundary(self) -> None:
        chunker = SemanticChunker(
            min_clause_chars=12,
            soft_clause_chars=40,
            max_chunk_chars=60,
        )
        chunks = chunker.feed("word " * 30)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertLessEqual(len(chunks[0].display_text), 60)

    def test_first_speakable_chunk_has_a_tighter_latency_bound(self) -> None:
        chunker = SemanticChunker(
            min_clause_chars=24,
            soft_clause_chars=120,
            max_chunk_chars=240,
            first_chunk_chars=72,
        )
        chunks = chunker.feed(
            "This opening contains enough meaningful words to begin speaking while the "
            "model continues generating the rest of a much longer answer"
        )

        self.assertGreaterEqual(len(chunks), 1)
        self.assertLessEqual(len(chunks[0].display_text), 80)
        self.assertTrue(chunks[0].display_text.endswith("the"))

    def test_flush_emits_an_incomplete_final_clause(self) -> None:
        chunker = SemanticChunker()
        self.assertEqual((), chunker.feed("unfinished thought"))
        chunks = chunker.flush()
        self.assertEqual(1, len(chunks))
        self.assertEqual("unfinished thought", chunks[0].spoken_text)
        self.assertEqual("", chunker.pending_display)


class MemoryRankingTests(unittest.TestCase):
    def test_expiry_project_isolation_and_scope_are_enforced(self) -> None:
        now = 10_000.0
        candidates = [
            MemoryCandidate(
                "keep",
                "MORICE uses the blue model profile",
                project_id="morice",
                scope="project",
                updated_at=now,
            ),
            MemoryCandidate(
                "expired",
                "MORICE once used the red model profile",
                project_id="morice",
                scope="project",
                expires_at=now,
            ),
            MemoryCandidate(
                "other-project",
                "MORICE uses a green model profile",
                project_id="another",
                scope="project",
            ),
            MemoryCandidate(
                "wrong-scope",
                "MORICE uses a yellow model profile",
                scope="private",
            ),
        ]
        ranked = rank_memories(
            candidates,
            "MORICE model profile",
            now=now,
            project_id="morice",
            scopes={"project"},
        )
        self.assertEqual(["keep"], [item.candidate.memory_id for item in ranked])

    def test_weighted_ranking_prefers_query_match_and_project(self) -> None:
        now = 20_000.0
        candidates = [
            MemoryCandidate(
                "matched",
                "ElevenLabs voice latency uses streamed chunks",
                relevance=0.8,
                importance=0.7,
                project_id="morice",
                updated_at=now,
            ),
            MemoryCandidate(
                "important-unrelated",
                "The desktop wallpaper is violet",
                importance=1.0,
                updated_at=now,
            ),
        ]
        ranked = rank_memories(
            candidates,
            "voice latency streamed chunks",
            now=now,
            project_id="morice",
        )
        self.assertEqual("matched", ranked[0].candidate.memory_id)
        self.assertGreater(ranked[0].lexical_relevance, ranked[1].lexical_relevance)

    def test_recency_and_character_budget_are_applied(self) -> None:
        now = 50_000.0
        candidates = [
            MemoryCandidate(
                "fresh",
                "same topic " + "x" * 100,
                created_at=now,
                updated_at=now,
            ),
            MemoryCandidate(
                "old",
                "same topic " + "y" * 100,
                created_at=now - 100_000,
                updated_at=now - 100_000,
            ),
        ]
        ranked = rank_memories(
            candidates,
            "same topic",
            now=now,
            half_life_seconds=100,
            char_budget=40,
        )
        self.assertEqual(1, len(ranked))
        self.assertEqual("fresh", ranked[0].candidate.memory_id)
        self.assertLessEqual(len(ranked[0].excerpt), 40)
        self.assertTrue(ranked[0].excerpt.endswith("\u2026"))


class BackgroundMindTests(unittest.TestCase):
    def test_event_reducer_builds_compact_status(self) -> None:
        mind = BackgroundMind(max_events=4, max_recent_files=2)
        mind.publish("project.opened", {"root": "D:/MORICE"}, timestamp=1)
        mind.publish("file.modified", {"path": "first.py"}, timestamp=2)
        mind.publish("file.modified", {"path": "second.py"}, timestamp=3)
        mind.publish("file.modified", {"path": "third.py"}, timestamp=4)
        mind.publish(
            "model.loaded",
            {"model": "general.gguf", "ignored": object()},
            timestamp=5,
        )
        mind.publish(
            "system.metrics",
            {"cpuPercent": 25, "gpuPercent": "72.5", "vramUsedMb": 3300},
            timestamp=6,
        )
        snapshot = mind.snapshot()
        self.assertEqual("D:/MORICE", snapshot.current_project)
        self.assertEqual("general.gguf", snapshot.current_model)
        self.assertEqual("loaded", snapshot.model_state)
        self.assertEqual(("third.py", "second.py"), snapshot.recent_files)
        self.assertEqual(72.5, snapshot.utilization["gpuPercent"])
        self.assertEqual(6, snapshot.event_count)
        self.assertEqual(4, len(mind.events()))

    def test_tasks_errors_and_subscribers_are_isolated(self) -> None:
        mind = BackgroundMind()
        seen: list[int] = []
        good = mind.subscribe(lambda event: seen.append(event.sequence))
        mind.subscribe(lambda _event: (_ for _ in ()).throw(RuntimeError("boom")))

        mind.publish("task.started", {"taskId": "a", "name": "index repo"})
        mind.publish(
            "task.failed",
            {"taskId": "a", "error": "index failed"},
        )
        snapshot = mind.snapshot()
        self.assertEqual((), snapshot.pending_tasks)
        self.assertEqual(("index repo",), snapshot.recent_tasks)
        self.assertEqual(("index failed",), snapshot.open_errors)
        self.assertEqual([1, 2], seen)
        self.assertTrue(mind.unsubscribe(good))
        self.assertFalse(mind.unsubscribe(good))

    def test_concurrent_publish_keeps_unique_sequences_and_bounded_history(self) -> None:
        mind = BackgroundMind(max_events=10)

        def publish(index: int) -> int:
            return mind.publish("file.modified", {"path": f"{index}.py"}).sequence

        with ThreadPoolExecutor(max_workers=8) as pool:
            sequences = list(pool.map(publish, range(100)))
        self.assertEqual(100, len(set(sequences)))
        self.assertEqual(100, mind.snapshot().event_count)
        self.assertEqual(10, len(mind.events()))


class RealtimeIntelligenceTests(unittest.TestCase):
    def test_new_epoch_cancels_old_request_and_rejects_stale_delta(self) -> None:
        intelligence = RealtimeIntelligence(
            models={ModelTier.GENERAL: "general.gguf"}
        )
        first = intelligence.begin_request("first request", request_id="first")
        second = intelligence.begin_request("second request", request_id="second")
        self.assertTrue(first.cancellation.cancelled)
        self.assertFalse(intelligence.is_current(first.epoch))
        self.assertTrue(intelligence.is_current(second.epoch))
        self.assertEqual((), intelligence.accept_delta(first.epoch, "stale text."))

    def test_facade_tracks_streaming_lifecycle_and_awareness(self) -> None:
        intelligence = RealtimeIntelligence(
            models={
                ModelTier.REFLEX: "tiny.gguf",
                ModelTier.GENERAL: "general.gguf",
            }
        )
        now_ns = time.perf_counter_ns() - 10_000_000
        request = intelligence.begin_request(
            "Explain streaming briefly",
            request_id="stream",
            started_ns=now_ns,
            initial_marks={
                LatencyStage.T0: now_ns,
                LatencyStage.T1: now_ns + 1_000_000,
                LatencyStage.T2: now_ns + 2_000_000,
            },
        )
        self.assertTrue(intelligence.mark(request.request_id, LatencyStage.T4))
        self.assertTrue(intelligence.mark(request.request_id, LatencyStage.T5))
        chunks = intelligence.accept_delta(request.epoch, "Streaming lowers latency.")
        self.assertEqual(1, len(chunks))
        self.assertTrue(request.trace.has(LatencyStage.T6))
        self.assertTrue(request.trace.has(LatencyStage.T7))
        for stage in (LatencyStage.T8, LatencyStage.T9, LatencyStage.T10):
            self.assertTrue(intelligence.mark(request.request_id, stage))
        self.assertEqual((), intelligence.complete_generation(request.epoch))
        self.assertTrue(request.trace.has(LatencyStage.T11))
        self.assertTrue(intelligence.finish_speech(request.epoch))
        self.assertTrue(request.trace.has(LatencyStage.T12))

        intelligence.record_event("network.online")
        snapshot = intelligence.snapshot()
        self.assertEqual({}, snapshot["active"])
        self.assertEqual(1, snapshot["latency"]["traceCount"])
        self.assertTrue(snapshot["awareness"]["online"])

    def test_facade_exposes_ranked_memory(self) -> None:
        intelligence = RealtimeIntelligence()
        ranked = intelligence.rank_memory(
            [MemoryCandidate("one", "GPU model routing")],
            "GPU routing",
        )
        self.assertEqual("one", ranked[0].candidate.memory_id)


if __name__ == "__main__":
    unittest.main()

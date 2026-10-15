"""Cross-system regression cases found by the Phase 8 source audit."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from morice.kernel import CapabilityKernel, ResourceClaim, ResourceDescriptor
from morice.kernel.events import EventBus, EventType, KernelEvent
from morice.action_runtime import ActionJournal
from morice.runtime_services import RuntimeServices, StructuredLogManager


class Phase8HardeningTests(unittest.TestCase):
    def test_concurrent_publisher_can_return_while_callback_waits_for_domain_lock(self):
        bus = EventBus(); domain = threading.Lock(); entered = threading.Event()
        delivered = []; second_done = threading.Event()
        def callback(event):
            entered.set()
            with domain:
                delivered.append(event.source)
        bus.subscribe(callback)
        domain.acquire()
        first = threading.Thread(target=lambda: bus.publish(KernelEvent(EventType.TASK_PROGRESS, source="first")), daemon=True)
        second = threading.Thread(target=lambda: (bus.publish(KernelEvent(EventType.TASK_PROGRESS, source="second")),second_done.set()), daemon=True)
        try:
            first.start(); self.assertTrue(entered.wait(1)); second.start()
            self.assertTrue(second_done.wait(.3), "Publisher blocked on subscriber's domain lock")
        finally:
            domain.release(); first.join(2); second.join(2)
        self.assertEqual(delivered, ["first", "second"])

    def test_subscriber_exception_does_not_expose_private_text(self):
        bus = EventBus()
        def failing(event):
            raise ValueError("password=event-canary-private")
        bus.subscribe(failing)
        with self.assertLogs("morice.kernel.events", "ERROR") as captured:
            bus.publish(KernelEvent(EventType.TASK_STARTED))
        self.assertNotIn("event-canary-private", "\n".join(captured.output))

    def test_log_and_journal_redact_nested_credentials_and_bearer_text(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"MORICE_TEST_TOKEN":"environment-canary-private"}):
            logs = StructuredLogManager(directory)
            logs.log("ERROR", "Authorization: Bearer bearer-canary-private password=message-canary-private",
                metadata={"nested":{"api_key":"nested-canary-private"}, "trace":"environment-canary-private"})
            journal = ActionJournal(Path(directory)/"actions.json")
            journal.update("attempt", errors=["Authorization: Bearer journal-canary-private"])
            serialized = logs.path.read_text()+journal.path.read_text()
            for canary in ("bearer-canary-private", "message-canary-private", "nested-canary-private", "environment-canary-private", "journal-canary-private"):
                self.assertNotIn(canary, serialized)

    def test_corrupt_journal_is_preserved_and_blocks_writes(self):
        for contents in ('{"version":1,"attempts":[', '{"version":999,"attempts":[]}', '{"version":1,"attempts":[null]}'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/"journal.json"; path.write_text(contents)
                journal = ActionJournal(path)
                self.assertTrue(journal.load_error)
                with self.assertRaises(RuntimeError):
                    journal.update("new", phase="executing")
                self.assertEqual(path.read_text(), contents)

    def test_remaining_physical_lease_keeps_shutdown_marker_dirty(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeServices(directory, project_root=Path(__file__).resolve().parents[1])
            runtime.recovery.begin_session()
            runtime.kernel.resources.register(ResourceDescriptor("PHASE8_OWNED_TEST"))
            runtime.kernel.resources.acquire("physical-work", (ResourceClaim("PHASE8_OWNED_TEST"),))
            try:
                runtime.shutdown()
                self.assertTrue(runtime.recovery.marker_path.exists(), "Shutdown falsely marked retained work clean")
                self.assertFalse(runtime.shutdown_report["clean"])
                self.assertEqual(runtime.shutdown_report["leases_remaining"], 1)
            finally:
                runtime.kernel.resources.release("physical-work")

    def test_future_models_share_existing_vram_capacity(self):
        kernel = CapabilityKernel()
        for name, capacity in (("VRAM_MB",6144), ("IMAGE_MODEL",1), ("VIDEO_MODEL",1), ("RAM_OFFLOAD",16384)):
            kernel.resources.register(ResourceDescriptor(name,capacity))
        self.assertTrue(kernel.resources.acquire("llm", (ResourceClaim("VRAM_MB",4608),)))
        self.assertFalse(kernel.resources.acquire("image", (ResourceClaim("VRAM_MB",3584),ResourceClaim("IMAGE_MODEL"))))
        self.assertNotIn("image", kernel.resources.snapshot())
        kernel.resources.release("llm")
        self.assertTrue(kernel.resources.acquire("image", (ResourceClaim("VRAM_MB",3584),ResourceClaim("IMAGE_MODEL"))))
        kernel.resources.release("image"); kernel.shutdown()
        self.assertEqual(kernel.resources.snapshot(), {})

    def test_checkpoint_redaction_preserves_long_source_and_filename_hashes(self):
        from morice.project_build.workspace import redact_data
        value={"source_hashes":{"tokenizer.py":"a"*64},"source":"a"*20000}
        self.assertEqual(redact_data(value),value)

    def test_rotated_environment_secret_is_redacted_in_next_nested_record(self):
        from morice.redaction import redact_data
        for secret in ('first-rotation-canary','second-rotation-canary'):
            with patch.dict(os.environ, {'MORICE_TEST_TOKEN':secret}):
                value=redact_data({'details':[secret,{'message':secret}]})
                self.assertNotIn(secret,json.dumps(value))


if __name__ == "__main__":
    unittest.main()

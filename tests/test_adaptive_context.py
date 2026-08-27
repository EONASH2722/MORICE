from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from morice import knowledge
from morice.core import extract_notes_term, needs_web, wants_notes_search
from morice.web_search import _bing_rss, infer_web_need, internet_available


class AutomaticWebRoutingTests(unittest.TestCase):
    def test_bing_rss_fallback_returns_source_link(self):
        payload = (
            "<rss><channel><item><title>Python release</title>"
            "<link>https://www.python.org/downloads/</link>"
            "<description>Current stable release details.</description>"
            "</item></channel></rss>"
        )
        with patch("morice.web_search._fetch_text", return_value=payload):
            result = _bing_rss("latest Python", 1)
        self.assertIn("Python release", result)
        self.assertIn("Source: https://www.python.org/downloads/", result)

    def test_current_external_fact_selects_web_without_magic_command(self):
        decision = infer_web_need("What is the latest stable llama.cpp release?")

        self.assertTrue(decision.required)
        self.assertEqual(decision.query, "What is the latest stable llama.cpp release?")
        self.assertTrue(needs_web("What is the latest stable llama.cpp release?"))

    def test_timeless_explanation_stays_on_fast_local_path(self):
        decision = infer_web_need("Explain why a transformer uses attention.")

        self.assertFalse(decision.required)
        self.assertEqual(decision.query, "")

    def test_changing_office_holder_selects_web_without_current_keyword(self):
        decision = infer_web_need("Who is the CEO of NVIDIA?")

        self.assertTrue(decision.required)
        self.assertIn("changing-office-holder", decision.reason)

    def test_local_notes_request_does_not_leak_to_web(self):
        decision = infer_web_need("What did I write in my notes about the motor?")

        self.assertFalse(decision.required)

    def test_legacy_web_hint_is_only_a_backward_compatible_hint(self):
        decision = infer_web_need("@web current CUDA driver version")

        self.assertTrue(decision.required)
        self.assertEqual(decision.query, "current CUDA driver version")

    def test_offline_probe_returns_false_without_raising(self):
        with patch("morice.web_search.socket.create_connection", side_effect=OSError):
            self.assertFalse(internet_available(force=True, timeout=0.05))


class AutomaticNotesRoutingTests(unittest.TestCase):
    def setUp(self):
        self.previous_cache = knowledge._cached_chunks

    def tearDown(self):
        knowledge._cached_chunks = self.previous_cache

    def test_relevant_notes_are_retrieved_without_notes_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "people.md").write_text(
                "Faye prefers the northern workshop entrance.", encoding="utf-8"
            )
            with (
                patch.object(knowledge, "KB_DIR", str(root)),
                patch.object(knowledge, "KB_REQUIRE_TAG", False),
            ):
                knowledge._cached_chunks = None
                query = "Which workshop entrance does Faye prefer?"
                self.assertTrue(knowledge.should_use_context(query))
                context = knowledge.retrieve_context(query)

        self.assertIn("northern workshop entrance", context)

    def test_natural_notes_request_no_longer_needs_at_command(self):
        request = "Can you find what I wrote in my notes about Faye?"

        self.assertTrue(wants_notes_search(request))
        self.assertEqual(extract_notes_term(request), "faye")


if __name__ == "__main__":
    unittest.main()

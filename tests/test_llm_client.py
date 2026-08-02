from pathlib import Path
import unittest
from unittest.mock import patch

from morice import llm_client


class LlmCompletionTests(unittest.TestCase):
    def test_ollama_modelfile_matches_long_reply_runtime_limits(self):
        modelfile = (
            Path(__file__).resolve().parents[1] / "Modelfile"
        ).read_text(encoding="utf-8")
        self.assertIn(f"PARAMETER num_ctx {llm_client.DEFAULT_CTX}", modelfile)
        self.assertIn(
            f"PARAMETER num_predict {llm_client.DEFAULT_MAX_TOKENS}",
            modelfile,
        )

    def test_openai_length_finish_is_continued_without_duplicate_overlap(self):
        responses = [
            {
                "choices": [
                    {
                        "message": {"content": "First section.\nShared ending"},
                        "finish_reason": "length",
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "content": "Shared ending and the completed second section."
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        ]
        payload = {
            "messages": [{"role": "user", "content": "Write a complete report."}],
            "max_tokens": 64,
        }

        with patch.object(llm_client, "_post_json", side_effect=responses) as post:
            result = llm_client._try_openai_chat("http://local", payload, 10)

        self.assertEqual(post.call_count, 2)
        self.assertEqual(result.count("Shared ending"), 1)
        self.assertTrue(result.endswith("completed second section."))

    def test_context_fitting_preserves_system_and_latest_user_message(self):
        huge_history = [
            {"role": "system", "content": "SYSTEM RULES"},
            *[
                {"role": "assistant", "content": f"old-{index}-" + ("x" * 2000)}
                for index in range(40)
            ],
            {"role": "user", "content": "LATEST REQUEST"},
        ]

        fitted = llm_client._fit_messages_to_context(huge_history)

        self.assertEqual(fitted[0]["content"], "SYSTEM RULES")
        self.assertEqual(fitted[-1]["content"], "LATEST REQUEST")
        self.assertLess(
            sum(len(message["content"]) for message in fitted),
            sum(len(message["content"]) for message in huge_history),
        )


if __name__ == "__main__":
    unittest.main()

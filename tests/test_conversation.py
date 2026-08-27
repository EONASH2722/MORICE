import unittest

from morice.core import extract_web_query
from morice.conversation import (
    conversation_reference_instruction,
    previous_user_message,
    references_prior_context,
    saved_settings_instruction,
    select_recent_history,
    wants_previous_user_message,
)


class ConversationContextTests(unittest.TestCase):
    def test_natural_web_requests_no_longer_require_at_web_prefix(self):
        self.assertEqual(
            extract_web_query("Search the web for current CUDA drivers"),
            "current CUDA drivers",
        )
        self.assertEqual(
            extract_web_query("look up today's weather in Delhi"),
            "today's weather in Delhi",
        )

    def test_typo_heavy_previous_message_references_are_detected(self):
        self.assertTrue(references_prior_context("in the previus msg i said so"))
        self.assertTrue(references_prior_context("use what I mentioned earlier"))
        self.assertTrue(wants_previous_user_message("what did i say in my previos mesage"))
        self.assertFalse(references_prior_context("what happened in the previous month"))

    def test_previous_user_message_ignores_empty_values(self):
        self.assertEqual(
            previous_user_message(["first", "", "the actual previous request"]),
            "the actual previous request",
        )

    def test_recent_history_is_bounded_and_starts_with_user(self):
        history = [
            {"role": "assistant", "content": "orphan"},
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "answer one"},
            {"role": "user", "content": "two"},
            {"role": "assistant", "content": "answer two"},
        ]
        selected = select_recent_history(history, max_messages=4, max_chars=100)
        self.assertEqual(selected[0]["role"], "user")
        self.assertEqual(selected[-1]["content"], "answer two")
        self.assertLessEqual(len(selected), 4)

    def test_reference_instruction_quotes_real_previous_turns(self):
        history = [
            {"role": "user", "content": "Use teal for the dashboard."},
            {"role": "assistant", "content": "I will use teal."},
        ]
        instruction = conversation_reference_instruction(
            "In the previous message I said so, now make it darker.",
            history,
            ["Use teal for the dashboard."],
        )
        self.assertIn("Use teal for the dashboard.", instruction)
        self.assertIn("I will use teal.", instruction)
        self.assertIn("Do not invent missing context", instruction)

    def test_saved_settings_override_old_conversation_preferences(self):
        instruction = saved_settings_instruction(
            "SIR",
            "Be concise and technical.",
            "Emoji preference: do not use emoji in prose.",
            "Truth-first disagreement rule: user insistence is not evidence.",
        )
        self.assertIn("authoritative", instruction)
        self.assertIn("Address the user as 'SIR'", instruction)
        self.assertIn("Be concise and technical.", instruction)
        self.assertIn("do not use emoji", instruction)
        self.assertIn("user insistence is not evidence", instruction)


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from unittest.mock import patch

from morice.capabilities import (
    capability_answer,
    detect_capability_topic,
    emoji_preference_instruction,
)
from morice.core import SYSTEM_PROMPT, shorten_reply
from morice.settings import (
    DEFAULT_SETTINGS,
    load_settings,
    normalize_custom_font_path,
    normalize_emoji_level,
    normalize_font_family,
    save_settings,
)


class CapabilityRoutingTests(unittest.TestCase):
    def test_rendering_inventory_is_deterministic_and_complete(self):
        topic = detect_capability_topic("what all rendering can you do")
        answer = capability_answer(topic or "", "none")

        self.assertEqual(topic, "rendering")
        self.assertIn("Interactive 2D function graphs", answer)
        self.assertIn("3D function surfaces", answer)
        self.assertIn("Live physics scenes", answer)
        self.assertIn("molecular geometry", answer)
        self.assertIn("reports that honestly", answer)

    def test_capability_router_tolerates_common_typos(self):
        self.assertEqual(
            detect_capability_topic("what all rendring can you suport"),
            "rendering",
        )
        self.assertEqual(
            detect_capability_topic("tell me your modles capabilites"),
            "models",
        )

    def test_real_graph_request_is_not_replaced_by_inventory(self):
        self.assertIsNone(detect_capability_topic("can you plot y = x^2"))
        self.assertIsNone(
            detect_capability_topic("what do you know about black holes")
        )
        self.assertIsNone(
            detect_capability_topic("what do you think about model airplanes")
        )

    def test_emoji_levels_change_presentation_without_touching_content(self):
        plain = capability_answer("files", "none")
        medium = capability_answer("files", "medium")
        expressive = capability_answer("files", "expressive")

        self.assertNotIn("📁", plain)
        self.assertIn("📁", medium)
        self.assertGreater(expressive.count("📁"), medium.count("📁"))
        self.assertIn("Preview source code", plain)
        self.assertIn("Preview source code", expressive)

    def test_emoji_prompt_rules_are_explicit(self):
        self.assertIn("do not use emoji", emoji_preference_instruction("none"))
        self.assertIn("sparingly", emoji_preference_instruction("medium"))
        self.assertIn("lively but readable", emoji_preference_instruction("expressive"))

    def test_long_reply_is_not_truncated(self):
        reply = "A" * 5000
        self.assertEqual(shorten_reply(reply), reply)

    def test_conversation_evaluation_mode_has_no_app_level_morality_filter(self):
        self.assertIn("Testing mode is active", SYSTEM_PROMPT)
        self.assertIn("without MORICE app-level refusals or morality lectures", SYSTEM_PROMPT)


class AppearanceSettingsTests(unittest.TestCase):
    def test_appearance_normalizers_fail_closed(self):
        self.assertEqual(normalize_emoji_level("balanced"), "medium")
        self.assertEqual(normalize_emoji_level("well"), "expressive")
        self.assertEqual(normalize_emoji_level("unknown"), "medium")
        self.assertEqual(normalize_font_family(' Test; Font " '), "Test Font")
        self.assertEqual(normalize_custom_font_path("not-a-font.exe"), "")

    def test_appearance_settings_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"APPDATA": directory}
        ):
            custom_font = os.path.join(directory, "custom.ttf")
            settings = dict(DEFAULT_SETTINGS)
            settings.update(
                {
                    "emoji_level": "expressive",
                    "font_family": "Example Sans",
                    "custom_font_path": custom_font,
                }
            )
            save_settings(settings)
            loaded = load_settings()

            self.assertEqual(loaded["emoji_level"], "expressive")
            self.assertEqual(loaded["font_family"], "Example Sans")
            self.assertEqual(loaded["custom_font_path"], custom_font)


if __name__ == "__main__":
    unittest.main()

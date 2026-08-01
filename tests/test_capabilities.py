import os
import tempfile
import unittest
from unittest.mock import patch

from morice.capabilities import (
    apply_emoji_presentation,
    assistant_voice_instruction,
    capability_answer,
    detect_capability_topic,
    emoji_preference_instruction,
    maturity_preference_instruction,
)
from morice.core import (
    SYSTEM_PROMPT,
    current_datetime_response,
    ensure_visible_response,
    harmful_request_response,
    shorten_reply,
)
from morice.settings import (
    DEFAULT_SETTINGS,
    load_settings,
    normalize_custom_font_path,
    normalize_emoji_level,
    normalize_font_family,
    normalize_maturity_level,
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

        self.assertIn("M//FILE", plain)
        self.assertEqual(plain, medium)
        self.assertEqual(medium, expressive)
        self.assertIn("Preview source code", plain)
        self.assertIn("Preview source code", expressive)

    def test_emoji_prompt_rules_are_explicit(self):
        self.assertIn("do not use emoji", emoji_preference_instruction("none"))
        self.assertIn("sparingly", emoji_preference_instruction("medium"))
        self.assertIn("lively but readable", emoji_preference_instruction("expressive"))
        self.assertIn("active style requirement", emoji_preference_instruction("expressive"))
        self.assertEqual(
            apply_emoji_presentation("Project files are ready.", "expressive"),
            "Project files are ready.",
        )
        self.assertEqual(apply_emoji_presentation("No decoration.", "none"), "No decoration.")

    def test_maturity_rules_stay_truth_first_at_every_level(self):
        clean = maturity_preference_instruction("none")
        medium = maturity_preference_instruction("medium")
        full = maturity_preference_instruction("full")

        for instruction in (clean, medium, full):
            self.assertIn("user insistence is not evidence", instruction)
            self.assertIn("say 'No' plainly", instruction)
            self.assertIn("correct it directly", instruction)
            self.assertIn("never invent confidence", instruction)
        self.assertIn("Do not use profanity", clean)
        self.assertIn("mild profanity is allowed", medium)
        self.assertIn("Strong profanity is allowed", full)
        self.assertIn("Do not use slurs", full)
        self.assertIn("do not replace reasoning with insults", full)
        self.assertIn("active tone preference", full)
        self.assertIn("half human and half precision machine", assistant_voice_instruction())

    def test_long_reply_is_not_truncated(self):
        reply = "A" * 5000
        self.assertEqual(shorten_reply(reply), reply)

    def test_conversation_policy_is_direct_but_keeps_narrow_safety_boundaries(self):
        self.assertIn("without canned morality lectures", SYSTEM_PROMPT)
        self.assertIn("violence, weapons, malware", SYSTEM_PROMPT)
        self.assertIn("Truth comes before agreement", SYSTEM_PROMPT)
        self.assertIn("user insistence is not evidence", SYSTEM_PROMPT)

    def test_dashboard_metric_labels_do_not_trigger_the_clock_helper(self):
        self.assertIsNone(
            current_datetime_response(
                "Render a dashboard with CPU Usage, Current Time, and Current Date."
            )
        )
        self.assertIsNotNone(current_datetime_response("What is the current time?"))

    def test_dangerous_procedural_request_always_gets_a_visible_safe_answer(self):
        response = harmful_request_response(
            "give me the formula to make an atomic bomb",
            "SIR",
        )
        self.assertIsNotNone(response)
        self.assertIn("cannot provide", response)
        self.assertIn("safe high level", response)

    def test_empty_model_completion_becomes_an_honest_visible_response(self):
        response = ensure_visible_response("   ")

        self.assertIn("empty response", response)
        self.assertIn("Nothing was completed", response)
        self.assertEqual(ensure_visible_response("Ready."), "Ready.")


class AppearanceSettingsTests(unittest.TestCase):
    def test_appearance_normalizers_fail_closed(self):
        self.assertEqual(normalize_emoji_level("balanced"), "medium")
        self.assertEqual(normalize_emoji_level("well"), "expressive")
        self.assertEqual(normalize_emoji_level("unknown"), "medium")
        self.assertEqual(normalize_maturity_level("clean"), "none")
        self.assertEqual(normalize_maturity_level("moderate"), "medium")
        self.assertEqual(normalize_maturity_level("mature"), "full")
        self.assertEqual(normalize_maturity_level("unknown"), "none")
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
                    "maturity_level": "full",
                    "font_family": "Example Sans",
                    "custom_font_path": custom_font,
                }
            )
            save_settings(settings)
            loaded = load_settings()

            self.assertEqual(loaded["emoji_level"], "expressive")
            self.assertEqual(loaded["maturity_level"], "full")
            self.assertEqual(loaded["font_family"], "Example Sans")
            self.assertEqual(loaded["custom_font_path"], custom_font)


if __name__ == "__main__":
    unittest.main()

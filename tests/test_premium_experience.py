import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MORICE_DISABLE_SESSION", "1")
os.environ.setdefault("MORICE_PRELOAD", "0")
os.environ.setdefault("MORICE_REDUCE_MOTION", "1")
os.environ.setdefault("MORICE_START_AWAKE", "1")

from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QApplication, QPushButton, QSizePolicy

from morice.premium_experience import (
    ExperienceProfile,
    ExperienceProfileStore,
    MAX_VISIBLE_CHAT_WIDGETS,
    visible_chat_slice,
    workspace_layout,
)
from morice.pyside_app import AdaptivePromptEdit, ChatBubble, MoriceWindow
from morice.settings import (
    normalize_animation_speed,
    normalize_transparency,
    normalize_ui_scale,
    normalize_workspace_preset,
)
from morice.ui_system import AnimationEngine, premium_theme_stylesheet
from morice.ui_workspace import CommandPalette, NotificationToast

APP = QApplication.instance() or QApplication([])


class ExperienceFoundationTests(unittest.TestCase):
    def test_experience_normalizers_are_bounded(self):
        self.assertEqual(normalize_animation_speed("FAST"), "fast")
        self.assertEqual(normalize_animation_speed("instant"), "normal")
        self.assertEqual(normalize_ui_scale("0.1"), 0.8)
        self.assertEqual(normalize_ui_scale("9"), 1.6)
        self.assertEqual(normalize_transparency("20"), 70)
        self.assertEqual(normalize_transparency("140"), 100)
        self.assertEqual(normalize_workspace_preset("science"), "science")
        self.assertEqual(normalize_workspace_preset("unknown"), "balanced")

    def test_profiles_roundtrip_import_export_and_reject_bad_json(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ExperienceProfileStore(directory)
            profile = store.save(
                ExperienceProfile(
                    name="Studio",
                    theme="midnight",
                    accent="#12ab9d",
                    animation_speed="fast",
                    high_contrast=True,
                    ui_scale=1.25,
                    workspace_preset="research",
                )
            )
            self.assertEqual(store.get("studio"), profile)
            export_path = os.path.join(directory, "profiles-export.json")
            store.export(export_path)
            imported_store = ExperienceProfileStore(
                os.path.join(directory, "imported")
            )
            self.assertEqual(imported_store.import_file(export_path), 1)
            self.assertEqual(imported_store.get("Studio").theme, "midnight")
            invalid_path = os.path.join(directory, "invalid.json")
            with open(invalid_path, "w", encoding="utf-8") as handle:
                handle.write("{bad json")
            with self.assertRaises(ValueError):
                imported_store.import_file(invalid_path)

    def test_workspace_presets_and_virtual_window_are_deterministic(self):
        self.assertTrue(workspace_layout("science").science_panel)
        self.assertTrue(workspace_layout("project").project_panel)
        self.assertEqual(len(workspace_layout("research").splitter_sizes), 6)
        self.assertEqual(visible_chat_slice(20), (0, 20))
        self.assertEqual(
            visible_chat_slice(MAX_VISIBLE_CHAT_WIDGETS + 25),
            (25, MAX_VISIBLE_CHAT_WIDGETS + 25),
        )

    def test_all_theme_variants_include_accessible_focus_and_contrast(self):
        for theme in ("dark", "light", "midnight", "glass", "custom"):
            stylesheet = premium_theme_stylesheet(
                theme,
                "#3bc7a5",
                high_contrast=True,
                transparency=76,
            )
            self.assertIn("QAbstractButton:focus", stylesheet)
            self.assertIn("#SettingsPreview", stylesheet)
            self.assertIn("rgba(", stylesheet)

    def test_animation_engine_respects_speed_and_reduced_motion(self):
        engine = AnimationEngine(enabled=True, speed="fast")
        self.assertLess(engine.duration(200), 200)
        engine.configure(speed="slow")
        self.assertGreater(engine.duration(200), 200)
        engine.configure(enabled=False)
        target = QRect(1, 2, 3, 4)
        widget = ChatBubble("MORICE", "Ready")
        engine.geometry(widget, target)
        self.assertEqual(widget.geometry(), target)


class PremiumUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = APP

    def setUp(self):
        self.window = MoriceWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.reduced_motion = True
        self.window._motion_enabled = False
        self.window.animation_engine.configure(enabled=False)
        self.window.close()
        self.app.processEvents()

    def test_adaptive_composer_supports_multiline_history_and_quick_actions(self):
        self.assertIsInstance(self.window.input, AdaptivePromptEdit)
        self.assertLessEqual(self.window.input.height(), 48)
        self.window.input.setText("line one\nline two")
        self.app.processEvents()
        self.assertGreaterEqual(self.window.input.height(), 44)
        self.assertLessEqual(self.window.input.height(), 132)
        self.assertTrue(self.window.attach_btn.toolTip())
        self.assertTrue(self.window.voice_btn.accessibleName())
        self.window.user_messages = ["first prompt", "second prompt"]
        self.window._navigate_prompt_history(-1)
        self.assertEqual(self.window.input.text(), "second prompt")

    def test_chat_bubbles_have_timestamp_copy_edit_and_reactions(self):
        bubble = ChatBubble("Captain", "```python\nprint('ready')\n```", is_user=True)
        self.assertEqual(bubble.accessibleName(), "Captain message")
        self.assertEqual(bubble.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)
        self.assertEqual(bubble.maximumWidth(), 16777215)
        self.assertTrue(
            any(
                button.toolTip() == "Copy message"
                for button in bubble.findChildren(QPushButton)
            )
        )
        bubble.reaction_button.click()
        self.assertEqual(bubble.reaction_button.text(), "M^")

    def test_user_and_assistant_messages_use_the_full_chat_row(self):
        user_row = self.window._create_message_row("Captain", "Build it", True, animate=False)
        assistant_row = self.window._create_message_row("MORICE", "Built and verified", False, animate=False)
        self.app.processEvents()
        for row in (user_row, assistant_row):
            bubble = row.findChild(ChatBubble)
            self.assertIsNotNone(bubble)
            self.assertEqual(row.layout().count(), 1)
            self.assertEqual(bubble.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)
            self.assertEqual(bubble.maximumWidth(), 16777215)

    def test_docked_composer_hides_low_priority_controls_when_narrow(self):
        self.window._dock_composer_immediate()
        self.window.input_frame.setFixedWidth(540)
        self.window._update_composer_responsive_state()
        self.app.processEvents()

        self.assertFalse(self.window.composer_centered)
        self.assertTrue(self.window.attach_btn.isVisible())
        self.assertFalse(self.window.voice_btn.isVisible())
        self.assertFalse(self.window.model_selector_btn.isVisible())
        self.assertTrue(self.window.precision_btn.isVisible())
        self.assertFalse(self.window.personalization_btn.isVisible())
        self.assertTrue(self.window.send_btn.isVisible())

    def test_workspace_presets_rearrange_existing_panels(self):
        self.window._apply_workspace_preset("science", notify=False)
        self.app.processEvents()
        self.assertTrue(self.window.workspace_panel.isVisible())
        self.assertFalse(self.window.changes_panel.isVisible())
        self.window._apply_workspace_preset("project", notify=False)
        self.app.processEvents()
        self.assertEqual(self.window.chat_mode, "project")
        self.assertFalse(self.window.changes_panel.isVisible())
        self.window._on_project_changes_ready(
            "Updated app.py",
            "<p><span style='color:#7cf7b5'>+ print('ready')</span></p>",
        )
        self.app.processEvents()
        self.assertTrue(self.window.changes_panel.isVisible())
        self.assertEqual(self.window.workspace_preset, "project")

    def test_premium_settings_apply_theme_accessibility_and_scale(self):
        with patch("morice.pyside_app.save_settings"):
            self.window._apply_experience_preferences(
                {
                    "name": "Accessible",
                    "theme": "midnight",
                    "accent": "#32c89a",
                    "animation_speed": "fast",
                    "reduced_motion": True,
                    "high_contrast": True,
                    "large_text": True,
                    "ui_scale": 1.2,
                    "transparency": 84,
                    "workspace_preset": "focus",
                }
            )
        self.assertEqual(self.window.current_theme, "midnight")
        self.assertTrue(self.window.high_contrast)
        self.assertTrue(self.window.large_text)
        self.assertEqual(self.window.ui_scale, 1.2)
        self.assertFalse(self.window.animation_engine.enabled)
        self.assertIn("#32c89a", self.window.styleSheet())

    def test_top_bar_command_recents_and_actionable_notification(self):
        self.window._execute_palette_command("layout-focus")
        self.assertEqual(self.window.workspace_state.recent_commands[0], "layout-focus")
        palette = CommandPalette(self.window)
        palette.set_recent(["settings"])
        palette._filter("")
        self.assertEqual(palette.results.item(0).data(Qt.UserRole), "settings")
        called = []
        toast = NotificationToast(self.window)
        toast.show_message(
            "Retry available",
            "warning",
            0,
            action_text="Retry",
            action_callback=lambda: called.append(True),
            progress=40,
        )
        self.assertTrue(toast.action_button.isVisible())
        self.assertEqual(toast.progress.value(), 40)
        toast.action_button.click()
        self.assertEqual(called, [True])

    def test_platform_dashboard_is_available_in_the_tools_workspace(self):
        self.window._set_assistant_hub_visible(True)
        self.window.assistant_hub.show_tab("Platform")
        self.app.processEvents()
        self.assertEqual(
            self.window.assistant_hub.tabs.tabText(
                self.window.assistant_hub.tabs.currentIndex()
            ),
            "Platform",
        )
        self.assertTrue(self.window.assistant_hub.platform_summary.text())
        self.assertGreaterEqual(self.window.assistant_hub.platform_runs.count(), 1)

    def test_chat_virtualization_bounds_live_widgets(self):
        initial_archived = len(self.window._archived_messages)
        initial_rows = len(self.window._message_rows)
        for index in range(MAX_VISIBLE_CHAT_WIDGETS + 8):
            self.window.append_message("MORICE", f"message {index}", force_scroll=False)
        self.assertEqual(len(self.window._message_rows), MAX_VISIBLE_CHAT_WIDGETS)
        expected_archived = initial_archived + initial_rows + 8
        self.assertEqual(len(self.window._archived_messages), expected_archived)
        self.assertFalse(self.window.chat_archive_notice.isHidden())


if __name__ == "__main__":
    unittest.main()

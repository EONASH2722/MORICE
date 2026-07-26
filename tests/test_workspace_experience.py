import json
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MORICE_DISABLE_SESSION", "1")
os.environ.setdefault("MORICE_PRELOAD", "0")
os.environ.setdefault("MORICE_REDUCE_MOTION", "1")
os.environ.setdefault("MORICE_START_AWAKE", "1")

from PySide6.QtWidgets import QApplication

from morice.desktop_assistant import (
    collect_system_snapshot,
    parse_desktop_command,
    search_files,
)
from morice.pyside_app import MoriceWindow, register_ui_font_file
from morice.ui_workspace import FilePreview
from morice.workspace_state import (
    WorkspaceState,
    load_workspace_state,
    save_workspace_state,
    workspace_state_path,
)


class WorkspaceStateTests(unittest.TestCase):
    def test_state_roundtrip_is_bounded_and_preserves_workspace_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "workspace-state.json")
            state = WorkspaceState(
                theme="light",
                accent="#123456",
                geometry=[20, 30, 1200, 760],
                maximized=True,
                assistant_hub_visible=True,
                notes="remember this",
            )
            for index in range(190):
                state.history.append({"role": "user", "content": f"message-{index}"})
                state.add_activity(f"activity-{index}")
            state.add_recent_file(os.path.join(directory, "example.txt"))
            save_workspace_state(state, path)

            loaded = load_workspace_state(path)

            self.assertEqual(loaded.theme, "light")
            self.assertEqual(loaded.accent, "#123456")
            self.assertEqual(loaded.geometry, [20, 30, 1200, 760])
            self.assertTrue(loaded.maximized)
            self.assertTrue(loaded.assistant_hub_visible)
            self.assertEqual(loaded.notes, "remember this")
            self.assertEqual(len(loaded.history), 160)
            self.assertEqual(len(loaded.activity), 120)
            self.assertTrue(loaded.recent_files[0].endswith("example.txt"))

    def test_corrupt_state_fails_closed_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "workspace-state.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not valid json")
            loaded = load_workspace_state(path)
            self.assertEqual(loaded.theme, "dark")
            self.assertEqual(loaded.history, [])


class DesktopAssistantTests(unittest.TestCase):
    def test_command_parser_marks_process_closing_as_sensitive(self):
        action = parse_desktop_command("/close-app notepad")
        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "close-app")
        self.assertTrue(action.confirmation_required)

    def test_command_parser_supports_workspace_and_media(self):
        self.assertEqual(parse_desktop_command("/workspace").kind, "workspace")
        media = parse_desktop_command("/volume-up")
        self.assertEqual(media.kind, "media")
        self.assertEqual(media.argument, "volume-up")

    def test_file_search_skips_generated_dependency_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            wanted = os.path.join(directory, "project-notes.txt")
            ignored_dir = os.path.join(directory, "node_modules")
            os.makedirs(ignored_dir)
            with open(wanted, "w", encoding="utf-8") as handle:
                handle.write("ok")
            with open(
                os.path.join(ignored_dir, "project-secret.txt"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write("ignored")

            results = search_files("project", [directory])

            self.assertEqual(results, [wanted])

    def test_system_snapshot_has_real_machine_values(self):
        snapshot = collect_system_snapshot()
        self.assertGreaterEqual(snapshot.cpu_threads, 1)
        self.assertGreater(snapshot.storage_total_gb, 0)
        self.assertTrue(snapshot.operating_system)


class WorkspaceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MoriceWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_workspace_is_split_resizable_and_feature_complete(self):
        names = [
            self.window.workspace_splitter.widget(index).objectName()
            for index in range(self.window.workspace_splitter.count())
        ]
        self.assertEqual(
            names,
            [
                "ModePanel",
                "ContentHost",
                "ScienceWorkspacePanel",
                "ProjectChangesPanel",
                "SidebarPanel",
                "AssistantHub",
            ],
        )
        self.assertEqual(
            [
                self.window.assistant_hub.tabs.tabText(index)
                for index in range(self.window.assistant_hub.tabs.count())
            ],
            [
                "Dashboard",
                "Files",
                "Activity",
                "Tools",
            ],
        )

    def test_command_palette_filters_and_theme_switches(self):
        self.window.command_palette._filter("system")
        self.assertEqual(self.window.command_palette.results.count(), 1)
        before = self.window.current_theme
        self.window.toggle_theme()
        self.assertNotEqual(self.window.current_theme, before)
        self.assertIn(self.window.accent_color, self.window.styleSheet())

    def test_lab_closes_from_project_mode_even_during_splitter_transition(self):
        self.window._set_chat_mode("project")
        self.window._open_workspace("graph")

        # A splitter relayout can briefly report the old QWidget visibility.
        # The requested panel state must remain authoritative for the toggle.
        self.window.workspace_panel.setVisible(False)
        self.assertTrue(
            self.window._panel_target_visibility[self.window.workspace_panel]
        )

        self.window.toggle_workspace_panel()
        self.app.processEvents()

        self.assertFalse(
            self.window._panel_target_visibility[self.window.workspace_panel]
        )
        self.assertFalse(self.window.workspace_panel.isVisible())
        self.assertEqual(self.window.title_bar.workspace_btn.text(), "Lab")

    def test_appearance_controls_change_theme_emoji_and_font(self):
        self.assertEqual(
            [
                self.window.theme_select.itemText(index)
                for index in range(self.window.theme_select.count())
            ],
            ["Dark", "Light"],
        )
        self.assertEqual(
            [
                self.window.emoji_select.itemText(index)
                for index in range(self.window.emoji_select.count())
            ],
            ["None", "Medium", "Expressive"],
        )
        self.assertEqual(
            [
                self.window.maturity_select.itemText(index)
                for index in range(self.window.maturity_select.count())
            ],
            ["None", "Medium", "Full"],
        )
        self.assertGreater(self.window.font_select.count(), 0)

        with patch("morice.pyside_app.save_settings"):
            expressive = self.window.emoji_select.findData("expressive")
            self.window.emoji_select.setCurrentIndex(expressive)
            self.assertEqual(self.window.emoji_level, "expressive")

            full = self.window.maturity_select.findData("full")
            self.window.maturity_select.setCurrentIndex(full)
            self.assertEqual(self.window.maturity_level, "full")

            light = self.window.theme_select.findData("light")
            self.window.theme_select.setCurrentIndex(light)
            self.assertEqual(self.window.current_theme, "light")

            selected_family = self.window.font_select.itemData(0)
            self.window.font_select.setCurrentIndex(0)
            self.assertEqual(self.window.font_family, selected_family)
            self.assertIn(selected_family, self.window.styleSheet())

    def test_normal_chat_remembers_fast_replies_and_resolves_previous_message(self):
        self.window.input.setText("what all rendering can you do")
        self.window.on_send()
        self.app.processEvents()

        self.assertEqual(self.window.history[-2]["role"], "user")
        self.assertEqual(
            self.window.history[-2]["content"],
            "what all rendering can you do",
        )
        self.assertEqual(self.window.history[-1]["role"], "assistant")

        self.window.input.setText("what did i say in my previus msg")
        self.window.on_send()
        self.app.processEvents()

        self.assertIn(
            "what all rendering can you do",
            self.window.history[-1]["content"],
        )
        self.assertNotIn(
            "what did i say in my previus msg",
            self.window.history[-1]["content"],
        )

    def test_contextual_follow_up_receives_history_and_current_settings(self):
        calls = []

        class ImmediateThread:
            def __init__(self, target, daemon=True):
                self.target = target

            def start(self):
                self.target()

        def fake_chat(history, user_message, **kwargs):
            calls.append((history, user_message, kwargs))
            return "I used the earlier dashboard request."

        self.window.user_title = "Captain"
        self.window.response_style = "Be concise and technical."
        self.window.emoji_level = "none"
        self.window.maturity_level = "medium"
        self.window.history = [
            {"role": "user", "content": "Make the dashboard teal."},
            {"role": "assistant", "content": "I will use teal."},
        ]
        self.window.user_messages = ["Make the dashboard teal."]
        self.window.first_user_message = "Make the dashboard teal."

        with patch("morice.pyside_app.threading.Thread", ImmediateThread), patch(
            "morice.pyside_app.chat",
            side_effect=fake_chat,
        ):
            self.window.input.setText(
                "In the previous message I said so; now make it darker."
            )
            self.window.on_send()
            self.app.processEvents()

        self.assertEqual(len(calls), 1)
        history, _, kwargs = calls[0]
        self.assertEqual(history[-2]["content"], "Make the dashboard teal.")
        self.assertEqual(history[-1]["content"], "I will use teal.")
        extra_system = kwargs["extra_system"]
        self.assertIn("Address the user as 'Captain'", extra_system)
        self.assertIn("Be concise and technical.", extra_system)
        self.assertIn("do not use emoji", extra_system)
        self.assertIn("Maturity setting: Medium", extra_system)
        self.assertIn("user insistence is not evidence", extra_system)
        self.assertIn(
            "<previous_user_message>Make the dashboard teal.</previous_user_message>",
            extra_system,
        )

    def test_invalid_custom_font_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "fake.ttf")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not a font")
            self.assertEqual(register_ui_font_file(path), "")

    def test_text_json_and_csv_files_have_real_inline_previews(self):
        preview = FilePreview()
        with tempfile.TemporaryDirectory() as directory:
            text_path = os.path.join(directory, "readme.txt")
            json_path = os.path.join(directory, "data.json")
            csv_path = os.path.join(directory, "data.csv")
            with open(text_path, "w", encoding="utf-8") as handle:
                handle.write("MORICE preview")
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump({"ready": True, "count": 2}, handle)
            with open(csv_path, "w", encoding="utf-8", newline="") as handle:
                handle.write("name,value\nalpha,12\nbeta,24\n")

            text_ok, _ = preview.show_file(text_path)
            self.assertTrue(text_ok)
            self.assertEqual(preview.text.toPlainText(), "MORICE preview")

            json_ok, _ = preview.show_file(json_path)
            self.assertTrue(json_ok)
            self.assertGreater(preview.json_tree.topLevelItemCount(), 0)

            csv_ok, _ = preview.show_file(csv_path)
            self.assertTrue(csv_ok)
            self.assertEqual(preview.spreadsheet.rowCount(), 2)
            self.assertEqual(preview.spreadsheet.item(1, 1).text(), "24")

    def test_window_restores_saved_theme_notes_and_panel_state(self):
        self.window.close()
        self.app.processEvents()
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"APPDATA": directory, "MORICE_DISABLE_SESSION": "0"},
        ):
            state = WorkspaceState(
                theme="light",
                accent="#234567",
                assistant_hub_visible=True,
                notes="restored note",
                geometry=[40, 50, 1100, 720],
            )
            save_workspace_state(state, workspace_state_path())
            restored = MoriceWindow()
            restored.show()
            self.app.processEvents()
            try:
                self.assertEqual(restored.current_theme, "light")
                self.assertEqual(restored.accent_color, "#234567")
                self.assertEqual(restored.assistant_hub.notes.toPlainText(), "restored note")
                self.assertTrue(restored.assistant_hub.isVisible())
            finally:
                restored.close()
                self.app.processEvents()
        self.window = MoriceWindow()


if __name__ == "__main__":
    unittest.main()

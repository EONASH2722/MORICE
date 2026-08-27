import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MORICE_DISABLE_SESSION", "1")
os.environ.setdefault("MORICE_PRELOAD", "0")
os.environ.setdefault("MORICE_REDUCE_MOTION", "1")
os.environ.setdefault("MORICE_START_AWAKE", "1")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox
from PySide6.QtTest import QTest

from morice.desktop_assistant import (
    collect_system_snapshot,
    parse_desktop_command,
    search_files,
)
from morice.pyside_app import (
    MoriceWindow,
    _show_window_for_launch,
    register_ui_font_file,
)
from morice.pc_control import ControlResult
from morice.settings import normalize_chat_mode
from morice.speech_runtime import TranscriptResult
from morice.ui_workspace import DEFAULT_COMMANDS, FilePreview
from morice.wake_runtime import WakeRequest
from morice.workspace_state import (
    WorkspaceState,
    load_workspace_state,
    save_workspace_state,
    workspace_state_path,
)


class WorkspaceStateTests(unittest.TestCase):
    def test_voice_mode_is_registered_as_a_first_class_mode(self):
        self.assertEqual(normalize_chat_mode("voice"), "voice")
        self.assertIn("voice-mode", {command.key for command in DEFAULT_COMMANDS})

    def test_state_roundtrip_is_bounded_and_preserves_workspace_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "workspace-state.json")
            state = WorkspaceState(
                theme="light",
                accent="#123456",
                geometry=[20, 30, 1200, 760],
                maximized=True,
                fullscreen=True,
                assistant_hub_visible=True,
                splitter_sizes=[292, 700, 430, 0, 0, 0],
                workspace_preset="science",
                notes="remember this",
            )
            for index in range(190):
                state.history.append({"role": "user", "content": f"message-{index}"})
                state.add_activity(f"activity-{index}")
            state.add_recent_file(os.path.join(directory, "example.txt"))
            state.add_recent_command("settings")
            save_workspace_state(state, path)

            loaded = load_workspace_state(path)

            self.assertEqual(loaded.theme, "light")
            self.assertEqual(loaded.accent, "#123456")
            self.assertEqual(loaded.geometry, [20, 30, 1200, 760])
            self.assertTrue(loaded.maximized)
            self.assertTrue(loaded.fullscreen)
            self.assertTrue(loaded.assistant_hub_visible)
            self.assertEqual(loaded.splitter_sizes, [292, 700, 430, 0, 0, 0])
            self.assertEqual(loaded.workspace_preset, "science")
            self.assertEqual(loaded.recent_commands, ["settings"])
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
                "Platform",
                "Tools",
            ],
        )

    def test_direct_and_streamed_assistant_replies_speak_exactly_once(self):
        self.window.chat_mode = "voice"
        with patch.object(self.window, "_speak_assistant_text") as speak:
            self.window._append_direct_reply("hello", "hello back")
            speak.assert_called_once()

        self.window._streamed_voice_reply_pending = True
        self.window._set_busy(True)
        with patch.object(self.window, "_speak_assistant_text") as speak:
            self.window._on_message_ready("MORICE", "streamed reply", False)
            speak.assert_not_called()
        self.assertFalse(self.window._streamed_voice_reply_pending)
        self.assertFalse(self.window.is_busy)

    def test_model_delta_is_visible_before_generation_finishes(self):
        request = self.window.runtime.realtime.begin_request(
            "Explain latency",
            request_id="ui-stream-test",
        )
        self.window._set_busy(True)
        self.window._show_thinking("Generating.")

        self.window._on_assistant_stream_delta(request.request_id, "First useful ")
        self.window._on_assistant_stream_delta(request.request_id, "sentence.")

        self.assertIsNotNone(self.window._stream_bubble)
        self.assertIn("First useful sentence.", self.window._stream_bubble.message)
        self.assertIsNone(self.window.thinking_bubble)
        self.assertIn(
            "first_visible_token",
            request.trace.snapshot()["events"],
        )

        self.window.runtime.realtime.complete_generation(request.epoch)
        self.window._on_assistant_stream_finished(
            request.request_id,
            self.window._address("First useful sentence."),
        )
        self.assertFalse(self.window.is_busy)

    def test_new_user_turn_interrupts_audio_and_generation_before_reply(self):
        with (
            patch.object(self.window.runtime.voice, "interrupt") as interrupt,
            patch.object(self.window.runtime.speech_input, "cancel") as cancel,
            patch.object(self.window, "_speak_assistant_text"),
        ):
            self.window.input.setText("thanks")
            self.window.on_send()

        interrupt.assert_called_once_with("new-user-request")
        cancel.assert_called_once_with("transcript-submitted")

    def test_fast_system_tool_bypasses_agent_and_model_preparation(self):
        result = ControlResult(
            "fast-test",
            "system.status",
            True,
            True,
            "System state collected from the local machine.",
            output={
                "memoryTotalGb": 32.0,
                "memoryAvailableGb": 12.0,
                "memoryPercent": 62.5,
            },
        )

        def immediate(_name, function):
            function()
            return None

        with (
            patch.object(self.window, "_prepare_agent_request") as prepare_agent,
            patch.object(self.window.runtime.pc_control, "execute", return_value=result),
            patch("morice.pyside_app._start_background_task", side_effect=immediate),
        ):
            self.window.input.setText("What's my RAM usage?")
            self.window.on_send()
            self.app.processEvents()

        prepare_agent.assert_not_called()
        self.assertTrue(
            any("memoryTotalGb" in item["content"] for item in self.window.history)
        )
        self.assertFalse(self.window.is_busy)
        self.assertIsNone(self.window.thinking_bubble)
        self.assertEqual(self.window.send_btn.text(), "Send")

    def test_hands_free_conversation_resumes_microphone_after_playback(self):
        self.window.chat_mode = "voice"
        self.window._voice_conversation_active = True
        self.window._set_busy(False)
        with patch.object(self.window, "_begin_voice_listening") as listen:
            self.window._resume_voice_conversation()
        listen.assert_called_once()

    def test_live_action_barge_in_filters_echo_and_interrupts_new_speech(self):
        self.window.chat_mode = "voice"
        self.window._voice_conversation_active = True
        self.window._barge_in_monitoring = True
        self.window._last_spoken_text = "Here is the answer about your project files"
        with (
            patch.object(self.window.runtime.voice, "interrupt") as interrupt,
            patch.object(self.window.runtime.realtime, "cancel_active") as cancel,
            patch.object(self.window.runtime.live_vision, "cancel") as cancel_vision,
        ):
            self.window._on_speech_partial("the answer about your project files")
            interrupt.assert_not_called()

            self.window._on_speech_partial("stop and show me the graph")

        interrupt.assert_called_once_with("barge-in")
        cancel.assert_called_once_with("barge-in")
        cancel_vision.assert_called_once_with("barge-in")
        self.assertTrue(self.window._barge_in_interrupted)

    def test_voice_is_explicit_mode_and_exit_stops_all_audio_io(self):
        self.window.chat_mode = "normal"
        self.window.awake = False
        self.window._voice_return_mode = "normal"
        self.window._voice_conversation_active = False
        self.assertEqual(self.window.chat_mode, "normal")
        self.assertFalse(self.window._voice_conversation_active)
        with (
            patch.object(self.window, "_begin_voice_listening") as listen,
            patch.object(self.window.runtime.speech_input, "cancel") as cancel,
            patch.object(self.window.runtime.voice, "interrupt") as interrupt,
        ):
            self.window._set_chat_mode("voice")
            QTest.qWait(240)

            self.assertEqual(self.window.chat_mode, "voice")
            self.assertTrue(self.window.awake)
            self.assertTrue(self.window._voice_conversation_active)
            self.assertEqual(self.window.settings["chat_mode"], "normal")
            self.assertEqual(self.window.voice_mode_btn.property("active"), "true")
            listen.assert_called_once()

            self.window._set_chat_mode("normal")

        self.assertEqual(self.window.chat_mode, "normal")
        self.assertFalse(self.window._voice_conversation_active)
        cancel.assert_called_with("voice-mode-exited")
        interrupt.assert_called_with("voice-mode-exited")
        self.assertEqual(self.window.voice_btn.toolTip(), "Enter Live Action")

    def test_external_wake_from_normal_mode_enters_voice_without_phantom_send(self):
        self.window.chat_mode = "normal"
        self.window._voice_return_mode = "normal"
        self.window._voice_conversation_active = False
        self.window.input.setText("keep this unsent draft")
        payload = WakeRequest(
            source="magic words: morice",
            trigger="phrase",
            enter_live_action=True,
            preserve_focus=True,
        ).to_json()

        with (
            patch.object(self.window, "on_send") as send,
            patch.object(self.window, "_begin_voice_listening"),
            patch("morice.pyside_app.set_voice_session_active") as lease,
        ):
            self.window._wake_from_external(payload)

            self.assertEqual(self.window.chat_mode, "voice")
            self.assertTrue(self.window._voice_conversation_active)
            self.assertEqual(self.window._voice_return_mode, "normal")
            self.assertEqual(self.window.input.text(), "keep this unsent draft")
            send.assert_not_called()
            lease.assert_called_with(True)

            self.window._set_chat_mode("normal")
            lease.assert_called_with(False)

    def test_background_wake_launch_is_minimized_without_activation(self):
        window = Mock()

        was_background = _show_window_for_launch(
            window,
            {"MORICE_BACKGROUND_WAKE": "1"},
        )

        self.assertTrue(was_background)
        window.setAttribute.assert_called_once()
        window.showMinimized.assert_called_once_with()
        window.show.assert_not_called()

    def test_ordinary_launch_behavior_is_unchanged(self):
        window = Mock()

        was_background = _show_window_for_launch(window, {})

        self.assertFalse(was_background)
        window.show.assert_called_once_with()
        window.showMinimized.assert_not_called()

    def test_live_action_is_camera_centered_and_camera_is_explicit(self):
        self.window.chat_mode = "normal"
        self.window._voice_return_mode = "normal"
        with patch.object(self.window, "_begin_voice_listening"):
            self.window._set_chat_mode("voice")
            self.app.processEvents()

        self.assertTrue(self.window.live_action_workspace.isVisible())
        self.assertFalse(self.window.chat_container.isVisible())
        self.assertFalse(self.window.live_camera.desired_active)
        self.assertIn("Live Action", self.window.voice_mode_btn.text())

    def test_camera_off_clears_preview_and_rejects_a_queued_late_frame(self):
        preview = self.window.live_action_workspace.preview
        image = QImage(32, 32, QImage.Format_RGB32)
        image.fill(0x336699)
        preview.set_frame(image)
        self.assertFalse(preview._image.isNull())

        self.window.live_action_workspace.set_camera_state(
            "off", "Camera is off. No frames are being captured."
        )
        self.assertTrue(preview._image.isNull())

        self.window.chat_mode = "voice"
        self.window.live_camera._desired_active = False
        self.window._on_live_camera_frame(image)
        self.assertTrue(preview._image.isNull())

    def test_visual_request_without_camera_fails_closed_before_model(self):
        self.window.chat_mode = "voice"
        self.window._voice_conversation_active = True
        with (
            patch.object(self.window, "_prepare_agent_request") as prepare_agent,
            patch.object(self.window, "_speak_assistant_text"),
        ):
            self.window.input.setText("What am I holding?")
            self.window.on_send()

        prepare_agent.assert_not_called()
        self.assertIn("no fresh camera frame", self.window.history[-1]["content"])

    def test_voice_output_and_late_transcripts_are_blocked_outside_voice_mode(self):
        with patch.object(self.window.runtime.voice, "speak") as speak:
            self.window._speak_assistant_text("This must stay silent.")
        speak.assert_not_called()

        self.window.input.setText("typed text")
        self.window._on_speech_transcript(
            TranscriptResult(
                request_id="late",
                text="late microphone words",
                duration_ms=1,
            )
        )
        self.assertEqual(self.window.input.text(), "typed text")

    def test_voice_mode_keeps_project_and_visualization_routing(self):
        self.window.chat_mode = "voice"
        self.assertTrue(
            self.window._is_project_build_request(
                "build a complete website in the project folder"
            )
        )
        with patch.object(
            self.window.visualization_manager,
            "decide",
            return_value=None,
        ) as decide:
            self.assertFalse(self.window._handle_science_request("graph y = x"))
        decide.assert_called_once_with("graph y = x")

    def test_command_palette_filters_and_theme_switches(self):
        self.window.command_palette._filter("system")
        self.assertEqual(self.window.command_palette.results.count(), 1)
        before = self.window.current_theme
        self.window.toggle_theme()
        self.assertNotEqual(self.window.current_theme, before)
        self.assertIn(self.window.accent_color, self.window.styleSheet())
        self.assertEqual(
            self.window.title_bar.theme_btn.accessibleName(),
            "Light theme active"
            if self.window.current_theme == "light"
            else "Dark theme active",
        )
        self.assertFalse(self.window.title_bar.theme_btn.icon().isNull())

    def test_phase_three_search_and_clipboard_are_integrated_with_visible_consent(self):
        results = self.window.runtime.desktop.search.search(
            "advanced diagnostics", roots=()
        )
        self.assertTrue(
            any(
                item.category == "commands" and item.action == "diagnostics"
                for item in results
            )
        )
        self.assertFalse(self.window.runtime.desktop.clipboard.enabled)
        self.assertEqual(
            self.window.assistant_hub.clipboard_monitor_button.text(),
            "Enable for session",
        )
        with patch.object(
            QMessageBox,
            "question",
            return_value=QMessageBox.Yes,
        ):
            self.window._on_workspace_command("clipboard-monitor")
        QApplication.clipboard().setText("https://example.com/phase-three")
        self.app.processEvents()

        self.assertTrue(self.window.runtime.desktop.clipboard.enabled)
        self.assertTrue(
            any(
                item.kind == "url"
                for item in self.window.runtime.desktop.clipboard.history()
            )
        )
        self.assertEqual(
            self.window.assistant_hub.clipboard_monitor_button.text(),
            "Disable",
        )
        self.window.runtime.desktop.clipboard.disable(clear=True)
        self.window.assistant_hub.set_clipboard_status(False)

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

    def test_background_signals_are_suppressed_during_window_shutdown(self):
        received = []
        self.window.thinking_update.connect(received.append)

        self.assertTrue(
            self.window._emit_background("thinking_update", "still open")
        )
        self.app.processEvents()
        self.assertEqual(received, ["still open"])

        self.window._is_closing = True
        self.assertFalse(
            self.window._emit_background("thinking_update", "too late")
        )
        self.app.processEvents()
        self.assertEqual(received, ["still open"])
        self.window._is_closing = False

    def test_appearance_controls_change_theme_emoji_and_font(self):
        self.assertEqual(
            [
                self.window.theme_select.itemText(index)
                for index in range(self.window.theme_select.count())
            ],
            ["Dark", "Light", "Midnight", "Glass", "Custom"],
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
            yield "I used the earlier dashboard request."

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
            "morice.pyside_app.stream_chat",
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
                history=[{"role": "user", "content": "stale message"}],
                user_messages=["stale message"],
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
                self.assertEqual(restored.history, [])
                self.assertEqual(restored.user_messages, [])
            finally:
                restored.close()
                self.app.processEvents()
        self.window = MoriceWindow()


if __name__ == "__main__":
    unittest.main()

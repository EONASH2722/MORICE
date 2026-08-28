import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from morice.wake_runtime import (
    WakeRequest,
    _pid_is_running,
    app_session_active,
    parse_wake_request,
    set_app_session_active,
    set_voice_session_active,
    voice_session_active,
    write_wake_request,
)


class WakeRequestTests(unittest.TestCase):
    def test_structured_signal_roundtrip_enters_live_action_without_focus(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wake.signal"
            written = write_wake_request("double clap", path=path)
            decoded = parse_wake_request(path.read_text(encoding="utf-8"))

        self.assertEqual(decoded.source, "double clap")
        self.assertEqual(decoded.trigger, "clap")
        self.assertTrue(decoded.enter_live_action)
        self.assertTrue(decoded.preserve_focus)
        self.assertGreater(written.created_at, 0.0)

    def test_legacy_plain_text_wake_signals_remain_compatible(self):
        decoded = parse_wake_request("magic words: hey MORICE")

        self.assertEqual(decoded.source, "magic words: hey MORICE")
        self.assertEqual(decoded.trigger, "phrase")
        self.assertTrue(decoded.enter_live_action)

    def test_explicit_non_voice_signal_is_respected(self):
        payload = WakeRequest(
            source="diagnostic",
            enter_live_action=False,
            preserve_focus=True,
        ).to_json()

        self.assertFalse(parse_wake_request(payload).enter_live_action)


class VoiceSessionLeaseTests(unittest.TestCase):
    def test_process_probe_recognizes_a_different_live_process(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            self.assertTrue(_pid_is_running(process.pid))
        finally:
            process.terminate()
            process.wait(timeout=5)
        self.assertFalse(_pid_is_running(process.pid))

    def test_live_process_lease_pauses_listener_and_exit_resumes_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice-session.json"
            set_voice_session_active(True, path=path, pid=os.getpid())
            self.assertTrue(voice_session_active(path=path))

            set_voice_session_active(False, path=path)
            self.assertFalse(voice_session_active(path=path))
            self.assertFalse(path.exists())

    def test_stale_process_lease_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice-session.json"
            path.write_text(json.dumps({"pid": 999_999}), encoding="utf-8")

            active = voice_session_active(path=path, pid_probe=lambda _pid: False)

            self.assertFalse(active)
            self.assertFalse(path.exists())

    def test_one_voice_process_cannot_clear_another_process_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice-session.json"
            set_voice_session_active(True, path=path, pid=77)

            set_voice_session_active(False, path=path, pid=88)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["pid"], 77)
            set_voice_session_active(False, path=path, pid=77)
            self.assertFalse(path.exists())

    def test_app_session_lease_identifies_ui_without_confusing_daemon(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app-session.json"
            set_app_session_active(True, path=path, pid=77)
            self.assertTrue(
                app_session_active(path=path, pid_probe=lambda pid: pid == 77)
            )
            self.assertFalse(
                app_session_active(path=path, pid_probe=lambda _pid: False)
            )
            self.assertFalse(path.exists())

    def test_one_ui_process_cannot_clear_another_process_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app-session.json"
            set_app_session_active(True, path=path, pid=77)

            set_app_session_active(False, path=path, pid=88)

            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["pid"], 77)
            set_app_session_active(False, path=path, pid=77)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()

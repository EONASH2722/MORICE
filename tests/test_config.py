import os
import tempfile
import unittest
from pathlib import Path

from morice import config


class TTSConfigTests(unittest.TestCase):
    def setUp(self):
        self.original_loaded = config._DOTENV_LOADED

    def tearDown(self):
        config._DOTENV_LOADED = self.original_loaded

    def test_missing_or_placeholder_key_is_safe_and_non_fatal(self):
        for value in ("", "<USER_MUST_INSERT_NEW_KEY_HERE>"):
            with self.subTest(value=value):
                loaded = config.load_tts_config(
                    {},
                    environ={"ELEVENLABS_API_KEY": value},
                )
                self.assertFalse(loaded.api_configured)
                self.assertEqual(
                    loaded.api_status,
                    "ElevenLabs API: Not configured",
                )

    def test_secret_never_appears_in_repr_or_public_diagnostics(self):
        secret = "test-only-secret-value-that-must-not-leak"
        loaded = config.load_tts_config(
            {},
            environ={"ELEVENLABS_API_KEY": secret},
        )

        self.assertTrue(loaded.api_configured)
        self.assertNotIn(secret, repr(loaded))
        self.assertNotIn(secret, str(loaded.public_dict()))
        self.assertEqual(loaded.public_dict()["apiStatus"], "ElevenLabs API: Configured")

    def test_dotenv_is_loaded_once_without_overriding_process_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text(
                "ELEVENLABS_API_KEY=dotenv-test-value\n"
                "ELEVENLABS_VOICE_ID=dotenv-voice\n",
                encoding="utf-8",
            )
            previous = os.environ.get("ELEVENLABS_API_KEY")
            os.environ["ELEVENLABS_API_KEY"] = "process-test-value"
            config._DOTENV_LOADED = False
            try:
                loaded = config.load_tts_config(root=directory)
            finally:
                if previous is None:
                    os.environ.pop("ELEVENLABS_API_KEY", None)
                else:
                    os.environ["ELEVENLABS_API_KEY"] = previous

            self.assertEqual(loaded.api_key, "process-test-value")

    def test_voice_and_runtime_controls_are_normalized(self):
        loaded = config.load_tts_config(
            {
                "tts_provider": "LOCAL",
                "tts_enabled": "off",
                "tts_streaming": "yes",
                "tts_speech_speed": "9",
                "tts_automatic_fallback": "no",
                "tts_output_device": "4",
            },
            environ={"ELEVENLABS_VOICE_ID": "voice-from-env"},
        )

        self.assertEqual(loaded.provider, "local")
        self.assertFalse(loaded.enabled)
        self.assertTrue(loaded.streaming)
        self.assertEqual(loaded.speech_speed, 1.2)
        self.assertFalse(loaded.automatic_fallback)
        self.assertEqual(loaded.output_device, 4)
        self.assertEqual(loaded.voice_id, "voice-from-env")

    def test_local_data_directory_can_be_moved_off_the_system_drive(self):
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory) / "MORICE data"
            actual = config.local_data_dir(
                environ={"MORICE_LOCAL_DATA_DIR": str(expected)},
            )

            self.assertEqual(actual, expected.resolve())

    def test_process_temp_is_scoped_to_morice_local_data(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {"MORICE_LOCAL_DATA_DIR": directory}
            previous_tempdir = tempfile.tempdir
            try:
                actual = config.configure_process_temp_dir(environ=environment)
            finally:
                tempfile.tempdir = previous_tempdir

            expected = Path(directory) / "temp"
            self.assertEqual(actual, expected.resolve())
            self.assertTrue(expected.is_dir())
            self.assertEqual(environment["TEMP"], str(expected.resolve()))
            self.assertEqual(environment["TMP"], str(expected.resolve()))
            self.assertEqual(environment["MORICE_TEMP_DIR"], str(expected.resolve()))


if __name__ == "__main__":
    unittest.main()

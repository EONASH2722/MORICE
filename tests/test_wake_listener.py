import math
import unittest
from unittest.mock import patch

import numpy as np

from morice_wake_listener import (
    AdaptiveAudioFrontend,
    AudioMetrics,
    RollingTranscript,
    audio_stream_options,
    detect_clap,
    magic_phrases,
    morice_is_running,
    normalize_sensitivity,
    phrase_matches,
    resample_pcm16,
    self_test,
    wait_for_voice_session_release,
)


class WakeAudioFrontendTests(unittest.TestCase):
    def test_high_sensitivity_amplifies_weak_speech_without_clipping(self):
        phase = np.linspace(0.0, math.tau * 8, 640, endpoint=False)
        weak_voice = (np.sin(phase) * 52.0).astype(np.int16)
        frontend = AdaptiveAudioFrontend("high")

        conditioned = frontend.condition_for_speech(weak_voice)

        raw_rms = frontend.metrics(weak_voice).rms
        conditioned_rms = frontend.metrics(conditioned).rms
        self.assertGreater(conditioned_rms, raw_rms * 4.0)
        self.assertLessEqual(int(np.max(np.abs(conditioned.astype(np.int32)))), 32767)

    def test_noise_floor_does_not_learn_a_clap_as_ambient_sound(self):
        frontend = AdaptiveAudioFrontend("high")
        before = (frontend.noise_peak, frontend.noise_rms)

        frontend.observe_noise(AudioMetrics(8_000.0, 900.0), transient=True)

        self.assertEqual((frontend.noise_peak, frontend.noise_rms), before)

    def test_sustained_bad_microphone_noise_eventually_updates_floor(self):
        frontend = AdaptiveAudioFrontend("high")

        for _ in range(1_000):
            frontend.observe_noise(AudioMetrics(900.0, 220.0))

        self.assertGreater(frontend.noise_rms, 120.0)
        self.assertGreater(frontend.noise_peak, 500.0)

    def test_weak_compressed_clap_is_detected_but_room_noise_is_not(self):
        quiet = np.zeros(640, dtype=np.int16)
        weak_clap = quiet.copy()
        weak_clap[80] = 520
        weak_clap[81] = -430
        room_noise = np.random.default_rng(4).normal(0, 16, 640).astype(np.int16)

        clap_detected, _, _ = detect_clap(weak_clap, 90.0, 12.0, "high")
        noise_detected, _, _ = detect_clap(room_noise, 90.0, 16.0, "high")

        self.assertTrue(clap_detected)
        self.assertFalse(noise_detected)

    def test_rolling_partials_recover_a_phrase_split_across_blocks(self):
        transcript = RollingTranscript()
        transcript.add("wake", 10.0)
        transcript.add("wake up", 10.2)
        combined = transcript.add("wake up son", 10.4)

        self.assertEqual(combined, "wake up son")
        self.assertTrue(phrase_matches(combined, "wake up son"))

    def test_resampling_keeps_audio_duration_for_vosk(self):
        source = np.arange(1_920, dtype=np.int16)

        converted = resample_pcm16(source, 48_000, 16_000)

        self.assertEqual(converted.size, 640)
        self.assertEqual(converted.dtype, np.int16)

    def test_device_options_include_rate_fallbacks(self):
        devices = [
            {
                "index": 3,
                "name": "Weak USB microphone",
                "default_samplerate": 48_000.0,
                "score": 1000,
            }
        ]
        with patch("morice_wake_listener.input_device_candidates", return_value=devices):
            options = audio_stream_options(3)

        self.assertEqual(options[0]["index"], 3)
        self.assertEqual(options[0]["rate"], 16_000)
        self.assertIn(48_000, [item["rate"] for item in options])

    def test_sensitivity_aliases_and_embedded_self_test(self):
        self.assertEqual(normalize_sensitivity("poor mic"), "high")
        self.assertEqual(normalize_sensitivity("normal"), "balanced")
        self.assertEqual(self_test(), 0)

    def test_morice_and_configured_magic_words_are_in_recognizer_grammar(self):
        phrases = magic_phrases("computer awaken")

        self.assertIn("morice", phrases)
        self.assertIn("hey morice", phrases)
        self.assertIn("computer awaken", phrases)

    def test_listener_releases_microphone_until_live_action_exits(self):
        states = iter((True, True, False))
        sleeps = []

        paused = wait_for_voice_session_release(
            probe=lambda: next(states),
            sleeper=sleeps.append,
            poll_seconds=0.04,
        )

        self.assertTrue(paused)
        self.assertEqual(sleeps, [0.04])

    def test_listener_uses_ui_lease_instead_of_its_own_process_name(self):
        with patch("morice_wake_listener.app_session_active", return_value=True):
            self.assertTrue(morice_is_running())


if __name__ == "__main__":
    unittest.main()

import unittest

from morice.response_policy import (
    ActionState,
    action_acknowledgement,
    speech_delivery,
)


class ResponsePolicyTests(unittest.TestCase):
    def test_verified_actions_get_truthful_tiny_acknowledgements(self):
        self.assertEqual(
            action_acknowledgement("media.pause", ActionState.VERIFIED),
            "Paused.",
        )
        self.assertEqual(
            action_acknowledgement("media.adjust_volume", ActionState.VERIFIED),
            "Done.",
        )

    def test_failure_never_says_done(self):
        reply = action_acknowledgement(
            "media.pause", ActionState.FAILED, failure="No media session was active."
        )
        self.assertEqual(reply, "Not yet. No media session was active.")

    def test_delivery_distinguishes_ack_warning_and_explanation(self):
        ack = speech_delivery("Yep.")
        warning = speech_delivery("Not yet. Build failed.")
        explanation = speech_delivery(" ".join(["technical"] * 50))
        self.assertEqual(ack.kind, "acknowledgement")
        self.assertGreater(ack.speed, 1.0)
        self.assertEqual(warning.kind, "warning")
        self.assertGreater(warning.stability, ack.stability)
        self.assertEqual(explanation.kind, "explanation")


if __name__ == "__main__":
    unittest.main()

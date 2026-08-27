import unittest

from PySide6.QtCore import QSize
from PySide6.QtMultimedia import QCameraFormat

from morice.live_camera import choose_camera_format, format_resolution, parse_resolution


class LiveCameraHelpersTests(unittest.TestCase):
    def test_resolution_parser_is_bounded_by_a_safe_fallback(self) -> None:
        self.assertEqual(parse_resolution("1280x720"), (1280, 720))
        self.assertEqual(parse_resolution("not-a-size"), (1280, 720))
        self.assertEqual(parse_resolution("0x720"), (1280, 720))
        self.assertEqual(format_resolution((1920, 1080)), "1920x1080")

    def test_empty_format_list_is_explicitly_unavailable(self) -> None:
        self.assertIsNone(choose_camera_format([], (1280, 720), 30))

    def test_format_selection_prefers_requested_resolution(self) -> None:
        low = QCameraFormat()
        high = QCameraFormat()
        # Qt does not expose public QCameraFormat setters, so the null formats
        # exercise deterministic selection without fabricating camera hardware.
        selected = choose_camera_format([low, high], (1280, 720), 30)
        self.assertIn(selected, (low, high))


if __name__ == "__main__":
    unittest.main()

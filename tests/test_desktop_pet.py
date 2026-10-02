import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QWidget

from morice.desktop_pet import (
    AnimationController,
    AssetLoader,
    BehaviorController,
    PetOverlayWindow,
    PetProcessController,
    PointerGesture,
    SUPPORTED_PETS,
    _is_true_fullscreen_geometry,
    normalize_pet_id,
)
from morice.pet_launcher import (
    MoriceLauncher,
    normalize_open_action,
    repaired_window_geometry,
    restore_morice_window,
)
from morice.settings import (
    DEFAULT_SETTINGS,
    normalize_pet_click_action,
    normalize_pet_event_frequency,
    normalize_pet_size,
)


class PointerGestureTests(unittest.TestCase):
    def test_short_stationary_pointer_sequence_is_a_click(self):
        gesture = PointerGesture()
        gesture.begin(100, 100, 10.0, drag_threshold=12, click_timeout_seconds=0.5)

        self.assertEqual(gesture.finish(106, 104, 10.2), "click")

    def test_os_drag_threshold_prevents_launcher_activation(self):
        gesture = PointerGesture()
        gesture.begin(100, 100, 10.0, drag_threshold=10, click_timeout_seconds=0.5)

        self.assertTrue(gesture.move(110, 100))
        self.assertEqual(gesture.finish(110, 100, 10.2), "drag")

    def test_long_hold_is_not_treated_as_a_click(self):
        gesture = PointerGesture()
        gesture.begin(100, 100, 10.0, drag_threshold=10, click_timeout_seconds=0.4)

        self.assertEqual(gesture.finish(100, 100, 10.41), "drag")


class PetConfigurationTests(unittest.TestCase):
    def test_click_action_defaults_to_open_morice(self):
        self.assertEqual(DEFAULT_SETTINGS["pet_click_action"], "open_morice")
        self.assertEqual(normalize_pet_click_action("Open MORICE Chat"), "open_chat")
        self.assertEqual(normalize_open_action("Do nothing"), "nothing")

    def test_pet_values_are_bounded(self):
        self.assertEqual(normalize_pet_id("Mark42"), "ironman_mark42")
        self.assertEqual(normalize_pet_id("unknown"), "dog")
        self.assertEqual(normalize_pet_size("LARGE"), "large")
        self.assertEqual(normalize_pet_size("enormous"), "medium")
        self.assertEqual(normalize_pet_event_frequency("SHOWCASE"), "showcase")
        self.assertEqual(normalize_pet_event_frequency("constant"), "normal")

    def test_special_events_default_to_normal_frequency(self):
        self.assertEqual(DEFAULT_SETTINGS["pet_event_frequency"], "normal")

    def test_every_supported_pet_has_data_driven_metadata(self):
        loader = AssetLoader()

        definitions = [loader.load(pet_id) for pet_id in SUPPORTED_PETS]

        self.assertEqual({item.pet_id for item in definitions}, set(SUPPORTED_PETS))
        self.assertTrue(all(item.name and item.renderer and item.click_feedback for item in definitions))
        self.assertTrue(all(len(item.behavior_states) >= 4 for item in definitions))

    def test_maximized_window_is_not_treated_as_true_fullscreen(self):
        monitor = (0, 0, 1920, 1080)

        self.assertFalse(
            _is_true_fullscreen_geometry(
                (-8, -8, 1928, 1088),
                monitor,
                is_maximized=True,
            )
        )

    def test_borderless_monitor_sized_window_is_true_fullscreen(self):
        self.assertTrue(
            _is_true_fullscreen_geometry(
                (0, 0, 1920, 1080),
                (0, 0, 1920, 1080),
                is_maximized=False,
            )
        )

    def test_work_area_sized_window_is_not_true_fullscreen(self):
        self.assertFalse(
            _is_true_fullscreen_geometry(
                (0, 0, 1920, 1040),
                (0, 0, 1920, 1080),
                is_maximized=False,
            )
        )


class PetAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_animation_controller_advances_and_resets_per_state(self):
        animation = AnimationController("normal")
        animation.set_state("patrol", now=10.0)

        first_frame, _ = animation.sample(10.0)
        later_frame, _ = animation.sample(10.24)
        animation.set_state("sleep", now=11.0)
        reset_frame, _ = animation.sample(11.0)

        self.assertEqual(first_frame, 0)
        self.assertNotEqual(later_frame, first_frame)
        self.assertEqual(reset_frame, 0)

    def test_superhero_drag_release_enters_escape_state(self):
        behavior = BehaviorController(
            AssetLoader().load("spiderman"), now=10.0
        )

        behavior.begin_drag(now=11.0)
        self.assertEqual(behavior.update(11.1), "dragged")
        behavior.end_drag(now=12.0)

        self.assertEqual(behavior.update(12.1), "escape")

    def test_ground_pet_drag_release_enters_falling_state(self):
        behavior = BehaviorController(AssetLoader().load("dog"), now=10.0)

        behavior.begin_drag(now=11.0)
        behavior.end_drag(now=12.0)

        self.assertEqual(behavior.update(12.1), "falling")

    def test_event_sequence_runs_in_order_and_clears(self):
        behavior = BehaviorController(AssetLoader().load("dog"), now=10.0)

        self.assertTrue(
            behavior.queue_event(
                "dog_special_play",
                (("fetch_ready", 1.0), ("fetch_chase", 1.0)),
                now=11.0,
            )
        )
        self.assertEqual(behavior.update(11.2), "fetch_ready")
        self.assertEqual(behavior.update(12.1), "fetch_chase")
        behavior.update(13.2)

        self.assertFalse(behavior.major_event_active)

    def test_every_pet_renders_each_declared_state(self):
        loader = AssetLoader()
        for pet_id in SUPPORTED_PETS:
            definition = loader.load(pet_id)
            overlay = PetOverlayWindow(definition, click_action="nothing")
            overlay.show()
            for state in definition.behavior_states:
                overlay.behavior.force(state, 2.0)
                overlay.animation.set_state(state)
                overlay.update()
                self.app.processEvents()
                image = overlay.grab().toImage()
                self.assertFalse(image.isNull(), f"{pet_id}:{state}")
            overlay.shutdown()

    def test_hover_motion_stays_bounded_to_stable_anchor(self):
        overlay = PetOverlayWindow(
            AssetLoader().load("ironman_mark42"), click_action="nothing"
        )
        overlay.move(200, 120)
        overlay._position_x = 200.0
        overlay._position_y = 120.0
        overlay._flight_anchor_y = 120.0
        overlay.behavior.force("hover", 60.0)
        observed = []

        for _ in range(160):
            overlay._last_tick = __import__("time").monotonic() - 0.05
            overlay._tick()
            observed.append(overlay.y())

        self.assertLessEqual(max(observed) - min(observed), 12)
        overlay.shutdown()

    def test_size_presets_are_compact_desktop_companion_sizes(self):
        overlay = PetOverlayWindow(
            AssetLoader().load("dog"), click_action="nothing", size="small"
        )
        self.assertEqual(overlay.width(), 64)
        overlay.configure_size("medium")
        self.assertEqual(overlay.width(), 86)
        overlay.configure_size("large")
        self.assertEqual(overlay.width(), 112)
        overlay.shutdown()

    def test_ironman_fast_flight_targets_opposite_screen_edge(self):
        overlay = PetOverlayWindow(
            AssetLoader().load("ironman_mark42"), click_action="nothing"
        )
        overlay._position_x = 1500.0
        overlay._position_y = 500.0
        overlay._choose_flight_target("fast_flight", QRect(0, 0, 1920, 1080))

        self.assertEqual(overlay._target_x, 0.0)
        self.assertGreaterEqual(overlay._target_y, 12.0)
        self.assertLessEqual(overlay._target_y, 995.0)
        overlay.shutdown()

    def test_ground_pet_drop_uses_gravity_instead_of_teleporting(self):
        overlay = PetOverlayWindow(
            AssetLoader().load("cat"), click_action="nothing"
        )
        overlay._position_x = 400.0
        overlay._position_y = 100.0
        overlay._drop_velocity_y = 0.0
        overlay._advance_drop(0.05, QRect(0, 0, 1920, 1080))

        self.assertGreater(overlay._position_y, 100.0)
        self.assertLess(overlay._position_y, 995.0)
        overlay.shutdown()

    def test_spiderman_swing_follows_pendulum_arc(self):
        overlay = PetOverlayWindow(
            AssetLoader().load("spiderman"), click_action="nothing"
        )
        overlay._position_x = 700.0
        overlay._position_y = 420.0
        area = QRect(0, 0, 1920, 1080)
        overlay._begin_swing(area)
        before = (overlay._position_x, overlay._position_y)
        overlay._advance_swing(0.08, area)

        self.assertNotEqual((overlay._position_x, overlay._position_y), before)
        self.assertGreater(overlay._swing_length, 100.0)
        overlay.shutdown()


class WindowRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_valid_previous_monitor_location_is_preserved(self):
        geometry = (2100, 80, 1100, 700)
        screens = [(0, 0, 1920, 1040), (1920, 0, 1920, 1040)]

        self.assertEqual(repaired_window_geometry(geometry, screens), geometry)

    def test_missing_previous_monitor_moves_window_to_visible_display(self):
        repaired = repaired_window_geometry(
            (4200, 100, 1200, 700),
            [(0, 0, 1920, 1040)],
        )

        self.assertEqual(repaired, (32, 32, 1200, 700))

    def test_hidden_window_is_shown_and_activated(self):
        window = QWidget()
        window.resize(400, 300)
        window.hide()

        with patch("morice.pet_launcher._native_restore_window", return_value=True):
            restore_morice_window(window, "open_morice")
            self.app.processEvents()

        self.assertTrue(window.isVisible())
        window.close()


class LauncherDeduplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_rapid_open_requests_spawn_only_once(self):
        launch = Mock()
        launcher = MoriceLauncher(
            request=lambda _action: False,
            session_probe=lambda: False,
            launch=launch,
        )

        self.assertEqual(launcher.open("open_morice"), "launched")
        self.assertEqual(launcher.open("open_morice"), "pending")
        self.assertEqual(launch.call_count, 1)

    def test_running_instance_is_focused_without_launch(self):
        launch = Mock()
        launcher = MoriceLauncher(
            request=lambda _action: True,
            session_probe=lambda: True,
            launch=launch,
        )

        self.assertEqual(launcher.open("open_chat"), "focused")
        launch.assert_not_called()

    def test_resident_pet_host_is_spawned_only_once_while_starting(self):
        spawn = Mock()
        controller = PetProcessController(
            settings={"pet_enabled": "true"},
            spawn=spawn,
        )

        with (
            patch("morice.desktop_pet._send_pet_host_command", return_value=False),
            patch("morice.desktop_pet.QTimer.singleShot"),
        ):
            self.assertTrue(controller.start())
            self.assertTrue(controller.start())

        spawn.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

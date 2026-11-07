import unittest
import time
from unittest.mock import patch

from pixel_scanner import hex_to_rgb, rgb_to_hex, color_distance_pct, color_matches, BASE_PALETTE
from engine import AutoClickerEngine


class TestColorTrigger(unittest.TestCase):
    def test_hex_and_rgb_conversion(self):
        self.assertEqual(hex_to_rgb("#FF0000"), (255, 0, 0))
        self.assertEqual(hex_to_rgb("00FF00"), (0, 255, 0))
        self.assertEqual(hex_to_rgb("#0000FF"), (0, 0, 255))
        self.assertEqual(hex_to_rgb("#FFFFFF"), (255, 255, 255))
        self.assertEqual(hex_to_rgb("#000000"), (0, 0, 0))

        self.assertEqual(rgb_to_hex(255, 0, 0), "#FF0000")
        self.assertEqual(rgb_to_hex((0, 255, 0)), "#00FF00")
        self.assertEqual(rgb_to_hex((0, 0, 255)), "#0000FF")

    def test_color_distance_and_matching(self):
        # Exact match
        self.assertAlmostEqual(color_distance_pct((255, 0, 0), (255, 0, 0)), 0.0)
        self.assertTrue(color_matches((255, 0, 0), "#FF0000", tolerance_pct=0.0))

        # Black vs White is 100% distance
        self.assertAlmostEqual(color_distance_pct((0, 0, 0), (255, 255, 255)), 100.0, places=1)
        self.assertFalse(color_matches((0, 0, 0), "#FFFFFF", tolerance_pct=30.0))

        # Slight shade variation (e.g. Red 255, 0, 0 vs 230, 10, 10)
        dist = color_distance_pct((255, 0, 0), (230, 10, 10))
        self.assertTrue(dist < 10.0)
        self.assertTrue(color_matches((230, 10, 10), "#FF0000", tolerance_pct=30.0))
        self.assertFalse(color_matches((230, 10, 10), "#FF0000", tolerance_pct=3.0))

    def test_engine_queue_mode_color_trigger(self):
        engine = AutoClickerEngine()
        clicked = []
        engine.perform_click = lambda x, y, c_type, apply_jitter=False, restore_pos=False: clicked.append((x, y))

        engine.points = [
            {
                "label": "ColorTarget",
                "x": 100,
                "y": 100,
                "delay": 0.01,
                "click_type": "left",
                "repeat": 1,
                "enabled": True,
                "color_trigger": True,
                "target_color": "#FF0000",
                "color_mode": "queue",
                "color_tolerance": 30.0,
                "color_timeout": 0.0,
            }
        ]
        engine.default_delay = 0.01
        engine.use_max_cycles = True
        engine.max_cycles = 1

        # Simulate pixel color: initially Black (no match), then changes to Red (match), then back to Black
        mock_colors = [(0, 0, 0), (0, 0, 0), (255, 0, 0)]
        call_count = [0]

        def mock_get_pixel(x, y):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(mock_colors):
                return mock_colors[idx]
            return (0, 0, 0)

        with patch("engine.get_pixel_color", side_effect=mock_get_pixel):
            engine.start()
            time.sleep(0.3)

        self.assertFalse(engine.is_running())
        self.assertEqual(len(clicked), 1)
        self.assertEqual(clicked[0], (100, 100))

    def test_engine_color_trigger_stop_interruption(self):
        engine = AutoClickerEngine()
        engine.perform_click = lambda x, y, c_type, apply_jitter=False, restore_pos=False: None

        # Point waiting indefinitely for Red, but screen stays Black
        engine.points = [
            {
                "label": "WaitingColor",
                "x": 150,
                "y": 150,
                "delay": 0.01,
                "click_type": "left",
                "repeat": 1,
                "enabled": True,
                "color_trigger": True,
                "target_color": "#FF0000",
                "color_mode": "queue",
                "color_tolerance": 30.0,
                "color_timeout": 0.0,
            }
        ]

        with patch("engine.get_pixel_color", return_value=(0, 0, 0)):
            engine.start()
            time.sleep(0.1)
            self.assertTrue(engine.is_running())
            # Stop should immediately break out of the infinite color wait
            engine.stop()
            time.sleep(0.1)
            self.assertFalse(engine.is_running())
            self.assertEqual(engine.status, "STOPPED")

    def test_engine_instant_mode_sentinel(self):
        engine = AutoClickerEngine()
        clicked = []
        engine.perform_click = lambda x, y, c_type, apply_jitter=False, restore_pos=False: clicked.append((x, y))

        engine.points = [
            # Normal queue point
            {"label": "P1", "x": 10, "y": 10, "delay": 0.2, "click_type": "left", "repeat": 1, "enabled": True},
            # Instant sentinel color watcher point
            {
                "label": "InstantWatcher",
                "x": 500,
                "y": 500,
                "delay": 0.01,
                "click_type": "left",
                "repeat": 1,
                "enabled": True,
                "color_trigger": True,
                "target_color": "#34C759",  # Green
                "color_mode": "instant",
                "color_tolerance": 30.0,
                "color_timeout": 0.0,
            }
        ]
        engine.default_delay = 0.2
        engine.use_duration = True
        engine.duration_seconds = 0.5

        def mock_get_pixel(x, y):
            if (x, y) == (500, 500):
                return (52, 199, 89)  # Exact Green
            return (0, 0, 0)

        with patch("engine.get_pixel_color", side_effect=mock_get_pixel):
            engine.start()
            time.sleep(0.4)
            engine.stop()

        # The instant watcher should have triggered at (500, 500)
        self.assertIn((500, 500), clicked)


if __name__ == "__main__":
    unittest.main()

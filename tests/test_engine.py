import unittest
import time
import os
import shutil
from engine import AutoClickerEngine
from profile_manager import ProfileManager

class TestAutoClicker(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "test_profiles")
        self.profile_mgr = ProfileManager(profiles_dir=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_profile_save_and_load(self):
        default_data = self.profile_mgr.get_default_profile()
        saved_path = self.profile_mgr.save_profile("TestPreset", default_data)
        self.assertTrue(os.path.exists(saved_path))

        loaded_data = self.profile_mgr.load_profile("TestPreset")
        self.assertEqual(loaded_data["name"], "TestPreset")
        self.assertEqual(len(loaded_data["points"]), 3)
        self.assertEqual(loaded_data["points"][0]["label"], "Target Button #1")
        self.assertEqual(loaded_data["points"][0]["repeat"], 1)
        self.assertTrue(loaded_data["points"][0]["enabled"])

    def test_engine_duration_limit(self):
        engine = AutoClickerEngine()
        clicked_coords = []
        engine.perform_click = lambda x, y, c_type, apply_jitter=False, restore_pos=False: clicked_coords.append((x, y))

        engine.points = [
            {"label": "P1", "x": 100, "y": 100, "delay": 0.1, "click_type": "left", "repeat": 1, "enabled": True},
            {"label": "P2", "x": 200, "y": 200, "delay": 0.1, "click_type": "left", "repeat": 1, "enabled": True}
        ]
        engine.default_delay = 0.1
        engine.random_jitter = 0.0
        engine.use_duration = True
        engine.duration_seconds = 0.45

        engine.start()
        time.sleep(0.7)
        self.assertFalse(engine.is_running())
        self.assertEqual(engine.status, "COMPLETED")
        self.assertTrue(len(clicked_coords) >= 2)

    def test_engine_cycle_limit_and_burst_and_skip_disabled(self):
        engine = AutoClickerEngine()
        clicked_coords = []
        engine.perform_click = lambda x, y, c_type, apply_jitter=False, restore_pos=False: clicked_coords.append((x, y))

        engine.points = [
            {"label": "P1", "x": 100, "y": 100, "delay": 0.02, "click_type": "left", "repeat": 2, "enabled": True},
            {"label": "P2_Disabled", "x": 999, "y": 999, "delay": 0.02, "click_type": "left", "repeat": 1, "enabled": False},
            {"label": "P3", "x": 200, "y": 200, "delay": 0.02, "click_type": "left", "repeat": 1, "enabled": True}
        ]
        engine.default_delay = 0.02
        engine.random_jitter = 0.0
        engine.use_max_cycles = True
        engine.max_cycles = 2

        engine.start()
        time.sleep(0.5)
        self.assertFalse(engine.is_running())
        self.assertEqual(engine.status, "COMPLETED")
        self.assertEqual(engine.current_cycle, 2)
        # Per cycle: P1 (2 clicks) + P2 (skipped) + P3 (1 click) = 3 clicks * 2 cycles = 6 clicks
        self.assertEqual(len(clicked_coords), 6)
        self.assertNotIn((999, 999), clicked_coords)

    def test_engine_immediate_stop(self):
        engine = AutoClickerEngine()
        engine.perform_click = lambda x, y, c_type, apply_jitter=False, restore_pos=False: None
        engine.points = [
            {"label": "P1", "x": 100, "y": 100, "delay": 5.0, "click_type": "left", "repeat": 1, "enabled": True}
        ]
        engine.default_delay = 5.0

        engine.start()
        time.sleep(0.1)
        self.assertTrue(engine.is_running())
        engine.stop()
        self.assertFalse(engine.is_running())
        self.assertEqual(engine.status, "STOPPED")

    def test_engine_pause_compensation(self):
        engine = AutoClickerEngine()
        engine.perform_click = lambda x, y, c_type, apply_jitter=False, restore_pos=False: None
        engine.points = [
            {"label": "P1", "x": 100, "y": 100, "delay": 0.05, "click_type": "left", "repeat": 1, "enabled": True}
        ]
        engine.default_delay = 0.05
        engine.use_duration = True
        engine.duration_seconds = 0.4

        engine.start()
        time.sleep(0.1)
        engine.pause()
        self.assertEqual(engine.status, "PAUSED")
        # Pause for 0.3s (if pause wasn't compensated, duration 0.4s would expire right now)
        time.sleep(0.3)
        self.assertTrue(engine.is_running())
        engine.resume()
        self.assertEqual(engine.status, "RUNNING")
        # Active elapsed should be ~0.1s, not 0.4s!
        self.assertLess(engine.elapsed_time, 0.25)
        engine.stop()
        self.assertFalse(engine.is_running())

if __name__ == "__main__":
    unittest.main()

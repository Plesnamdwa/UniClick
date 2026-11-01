import json
import os
from typing import List, Dict, Any, Optional

DEFAULT_PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")

class ProfileManager:
    """Manages saving and loading of UniClick profiles with backward compatibility."""

    def __init__(self, profiles_dir: Optional[str] = None):
        self.profiles_dir = profiles_dir or DEFAULT_PROFILES_DIR
        os.makedirs(self.profiles_dir, exist_ok=True)

    def get_default_profile(self) -> Dict[str, Any]:
        return {
            "name": "Default Profile",
            "default_delay": 1.0,          # seconds (decimal)
            "use_jitter": False,           # enable time jitter (default off for pure accuracy)
            "random_jitter": 0.05,         # +/- random jitter seconds
            "use_pixel_jitter": False,     # enable anti-cheat coordinate jitter (default off)
            "pixel_jitter": 4,             # +/- random pixel offset radius
            "restore_cursor": False,       # Ghost Click: return cursor after clicking
            "use_duration": False,         # duration timer toggle
            "duration_seconds": 60.0,      # active duration limit in seconds
            "use_max_cycles": False,       # cycle limit toggle
            "max_cycles": 10,              # max repeat cycles
            "points": [
                {
                    "label": "Target Button #1",
                    "x": 650,
                    "y": 450,
                    "delay": 2.5,
                    "click_type": "left",
                    "repeat": 1,
                    "enabled": True
                },
                {
                    "label": "Target Button #2",
                    "x": 950,
                    "y": 250,
                    "delay": 1.0,
                    "click_type": "left",
                    "repeat": 1,
                    "enabled": True
                },
                {
                    "label": "Confirm / Next",
                    "x": 800,
                    "y": 600,
                    "delay": 1.5,
                    "click_type": "left",
                    "repeat": 1,
                    "enabled": True
                }
            ]
        }

    def normalize_profile(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures loaded profile data has all required keys with safe defaults."""
        defaults = self.get_default_profile()
        normalized = dict(defaults)
        normalized.update(data)

        norm_points = []
        for idx, pt in enumerate(data.get("points", [])):
            norm_pt = {
                "label": pt.get("label", f"Target #{idx + 1}"),
                "x": int(pt.get("x", 500)),
                "y": int(pt.get("y", 300)),
                "delay": float(pt.get("delay", normalized.get("default_delay", 1.0))),
                "click_type": pt.get("click_type", "left"),
                "repeat": max(1, int(pt.get("repeat", 1))),
                "enabled": bool(pt.get("enabled", True))
            }
            norm_points.append(norm_pt)
        normalized["points"] = norm_points
        return normalized

    def list_profiles(self) -> List[str]:
        if not os.path.exists(self.profiles_dir):
            return []
        files = os.listdir(self.profiles_dir)
        return sorted([f[:-5] for f in files if f.endswith(".json")])

    def save_profile(self, name: str, data: Dict[str, Any]) -> str:
        clean_name = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip()
        if not clean_name:
            clean_name = "profile"
        data["name"] = clean_name
        file_path = os.path.join(self.profiles_dir, f"{clean_name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return file_path

    def load_profile(self, name: str) -> Dict[str, Any]:
        file_path = os.path.join(self.profiles_dir, f"{name}.json")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Profile '{name}' not found at {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.normalize_profile(data)

    def delete_profile(self, name: str) -> bool:
        file_path = os.path.join(self.profiles_dir, f"{name}.json")
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False

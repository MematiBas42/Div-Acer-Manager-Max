"""Unit tests for HardwareManager fan control and state management."""

import os
import shutil
import tempfile
import unittest
from daemon.core.hardware_manager import HardwareManager


class TestHardwareManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.fan_file = os.path.join(self.test_dir, "fan_speed")
        self.profile_file = os.path.join(self.test_dir, "platform_profile")
        self.profile_choices = os.path.join(self.test_dir, "platform_profile_choices")

        with open(self.fan_file, "w") as f:
            f.write("0,0\n")
        with open(self.profile_file, "w") as f:
            f.write("balanced\n")
        with open(self.profile_choices, "w") as f:
            f.write("quiet balanced performance turbo\n")

        self.mgr = HardwareManager(base_override=self.test_dir)
        self.mgr.available_features.add("fan_speed")
        self.mgr.available_features.add("thermal_profile")

        # Mock profile file locations in HardwareManager
        self.orig_read_file = self.mgr._read_file
        self.orig_write_file = self.mgr._write_file

        def mocked_read(path):
            if "platform_profile_choices" in path:
                return self.orig_read_file(self.profile_choices)
            if "platform_profile" in path:
                return self.orig_read_file(self.profile_file)
            return self.orig_read_file(path)

        def mocked_write(path: str, value: str) -> bool:
            if "platform_profile" in path:
                return self.orig_write_file(self.profile_file, value)
            return self.orig_write_file(path, value)

        self.mgr._read_file = mocked_read
        self.mgr._write_file = mocked_write

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_fan_speed_auto_auto(self):
        self.mgr.set_fan_speed(0, 0)
        with open(self.fan_file, "r") as f:
            self.assertEqual(f.read().strip(), "0,0")

    def test_fan_speed_max_max(self):
        self.mgr.set_fan_speed(100, 100)
        with open(self.fan_file, "r") as f:
            self.assertEqual(f.read().strip(), "100,100")

    def test_fan_speed_cpu_auto_gpu_manual(self):
        # Crucial bug fix: Setting GPU fan to manual should NOT clamp CPU fan to 5 or 20!
        self.mgr.set_fan_speed(0, 70)
        with open(self.fan_file, "r") as f:
            self.assertEqual(f.read().strip(), "0,70")

    def test_fan_speed_gpu_auto_cpu_manual(self):
        # Setting CPU fan to manual should NOT clamp GPU fan to 5 or 20!
        self.mgr.set_fan_speed(60, 0)
        with open(self.fan_file, "r") as f:
            self.assertEqual(f.read().strip(), "60,0")

    def test_fan_speed_stall_prevention_on_manual(self):
        # Manual values below 20 must be clamped to safe 20% to avoid motor stall
        self.mgr.set_fan_speed(10, 15)
        with open(self.fan_file, "r") as f:
            self.assertEqual(f.read().strip(), "20,20")

    def test_nos_activation_and_deactivation(self):
        self.mgr.set_thermal_profile("quiet")
        self.mgr.set_fan_speed(0, 0)

        # Activate NOS
        self.assertTrue(self.mgr.activate_nos())
        self.assertTrue(self.mgr.is_nos_active)
        with open(self.fan_file, "r") as f:
            self.assertEqual(f.read().strip(), "100,100")
        with open(self.profile_file, "r") as f:
            self.assertEqual(f.read().strip(), "turbo")

        # Deactivate NOS
        self.assertTrue(self.mgr.deactivate_nos())
        self.assertFalse(self.mgr.is_nos_active)
        with open(self.fan_file, "r") as f:
            self.assertEqual(f.read().strip(), "0,0")
        with open(self.profile_file, "r") as f:
            self.assertEqual(f.read().strip(), "quiet")

    def test_cycle_profile_ac_power(self):
        # On AC power: 3 steps cycle (quiet -> balanced -> performance -> quiet)
        self.mgr.set_thermal_profile("quiet")
        p1 = self.mgr.cycle_profile(is_ac=True)
        self.assertEqual(p1, "balanced")
        p2 = self.mgr.cycle_profile(is_ac=True)
        self.assertEqual(p2, "performance")
        p3 = self.mgr.cycle_profile(is_ac=True)
        self.assertEqual(p3, "quiet")

    def test_cycle_profile_battery_power(self):
        # On Battery power: 2 steps cycle (low-power -> balanced -> low-power)
        # Add low-power to choices
        with open(self.profile_choices, "w") as f:
            f.write("low-power quiet balanced performance\n")

        self.mgr.set_thermal_profile("low-power")
        p1 = self.mgr.cycle_profile(is_ac=False)
        self.assertEqual(p1, "balanced")
        p2 = self.mgr.cycle_profile(is_ac=False)
        self.assertEqual(p2, "low-power")

    def test_cycle_profile_rapid_consecutive_clicks_no_race(self):
        # Rapid double click test: Even if sysfs mock returns stale value,
        # in-memory state ensures deterministic advance
        self.mgr.set_thermal_profile("quiet")
        p1 = self.mgr.cycle_profile(is_ac=True)
        self.assertEqual(p1, "balanced")
        
        # Second immediate click
        p2 = self.mgr.cycle_profile(is_ac=True)
        self.assertEqual(p2, "performance")


if __name__ == "__main__":
    unittest.main()

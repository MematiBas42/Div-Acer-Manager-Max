"""Unit tests for PowerOptimizer and BootBoostManager."""

import os
import shutil
import tempfile
import asyncio
import unittest
from daemon.core.power_optimizer import PowerOptimizer
from daemon.core.boot_boost import BootBoostManager


class TestPowerCore(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cpu0_epp = os.path.join(self.test_dir, "devices/system/cpu/cpu0/power/energy_performance_preference")
        self.aspm_policy = os.path.join(self.test_dir, "module/pcie_aspm/parameters/policy")
        self.intel_turbo = os.path.join(self.test_dir, "devices/system/cpu/intel_pstate/no_turbo")

        os.makedirs(os.path.dirname(self.cpu0_epp), exist_ok=True)
        os.makedirs(os.path.dirname(self.aspm_policy), exist_ok=True)
        os.makedirs(os.path.dirname(self.intel_turbo), exist_ok=True)

        for p in [self.cpu0_epp, self.aspm_policy, self.intel_turbo]:
            with open(p, "w") as f:
                f.write("\n")

        self.opt = PowerOptimizer(sysfs_root=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_apply_profile_quiet(self):
        res = self.opt.apply_profile("quiet")
        self.assertTrue(res["epp"])
        self.assertTrue(res["aspm"])
        self.assertTrue(res["turbo"])

        with open(self.cpu0_epp, "r") as f:
            self.assertEqual(f.read().strip(), "power")
        with open(self.aspm_policy, "r") as f:
            self.assertEqual(f.read().strip(), "powersave")
        with open(self.intel_turbo, "r") as f:
            self.assertEqual(f.read().strip(), "1")  # no_turbo = 1 (disabled)

    def test_apply_profile_performance(self):
        res = self.opt.apply_profile("performance")
        self.assertTrue(res["epp"])
        self.assertTrue(res["aspm"])
        self.assertTrue(res["turbo"])

        with open(self.cpu0_epp, "r") as f:
            self.assertEqual(f.read().strip(), "performance")
        with open(self.aspm_policy, "r") as f:
            self.assertEqual(f.read().strip(), "performance")
        with open(self.intel_turbo, "r") as f:
            self.assertEqual(f.read().strip(), "0")  # no_turbo = 0 (enabled)

    def test_boot_boost_execution(self):
        finished = False

        def on_finish():
            nonlocal finished
            finished = True

        boot = BootBoostManager(on_finish)
        boot.configure(enabled=True, delay_seconds=1)

        max_triggered = False

        def trigger_max():
            nonlocal max_triggered
            max_triggered = True

        async def run_test():
            await boot.start_boost(trigger_max)

        asyncio.run(run_test())
        self.assertTrue(max_triggered)
        self.assertTrue(finished)
        self.assertFalse(boot.is_active)


if __name__ == "__main__":
    unittest.main()

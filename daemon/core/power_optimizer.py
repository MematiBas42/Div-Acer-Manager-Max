"""System Power and Hardware Governor Optimizer for Acer laptops."""

import os
import glob
import logging
from typing import Dict, Optional

log = logging.getLogger("acersense.power")


class PowerOptimizer:
    """Manages low-level CPU EPP, PCIe ASPM, WiFi, and Turbo governors."""

    def __init__(self, sysfs_root: str = "/sys"):
        self.sysfs_root = sysfs_root

    def _write_safe(self, path: str, value: str) -> bool:
        try:
            if not os.path.exists(path):
                return False
            with open(path, "w", encoding="utf-8") as f:
                f.write(value.strip() + "\n")
            return True
        except Exception as e:
            log.debug(f"Failed to write '{value}' to {path}: {e}")
            return False

    def apply_profile(self, profile: str) -> Dict[str, bool]:
        """Apply system-level governors corresponding to the active thermal profile."""
        profile = profile.lower()
        results = {
            "epp": False,
            "aspm": False,
            "turbo": False,
        }

        # 1. CPU Energy Performance Preference (EPP)
        epp_val = "balance_performance"
        if profile in ["low-power", "quiet", "eco"]:
            epp_val = "power"
        elif profile in ["balanced"]:
            epp_val = "balance_performance"
        elif profile in ["performance", "turbo", "balanced-performance"]:
            epp_val = "performance"

        epp_success = False
        epp_files = glob.glob(os.path.join(self.sysfs_root, "devices/system/cpu/cpu*/power/energy_performance_preference"))
        for f in epp_files:
            if self._write_safe(f, epp_val):
                epp_success = True
        results["epp"] = epp_success

        # 2. PCIe Active State Power Management (ASPM)
        aspm_policy = os.path.join(self.sysfs_root, "module/pcie_aspm/parameters/policy")
        aspm_val = "default"
        if profile in ["low-power", "quiet", "eco"]:
            aspm_val = "powersave"
        elif profile in ["performance", "turbo"]:
            aspm_val = "performance"
        results["aspm"] = self._write_safe(aspm_policy, aspm_val)

        # 3. CPU Turbo Boost
        intel_turbo = os.path.join(self.sysfs_root, "devices/system/cpu/intel_pstate/no_turbo")
        amd_boost = os.path.join(self.sysfs_root, "devices/system/cpu/cpufreq/boost")
        
        if profile in ["low-power", "quiet", "eco"]:
            # Disable turbo on power-saving profiles
            self._write_safe(intel_turbo, "1")
            self._write_safe(amd_boost, "0")
            results["turbo"] = True
        else:
            # Enable turbo on balanced and performance
            self._write_safe(intel_turbo, "0")
            self._write_safe(amd_boost, "1")
            results["turbo"] = True

        log.info(f"Applied power optimizations for profile '{profile}': EPP={epp_val}, ASPM={aspm_val}")
        return results

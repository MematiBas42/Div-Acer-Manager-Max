"""Hardware Manager for Acer Nitro and Predator laptops via linuwu_sense and ENEK5130."""

import os
import glob
import logging
from typing import Dict, List, Optional, Set, Tuple
from daemon.core.laptop_type import LaptopType

log = logging.getLogger("acersense.hardware")

ENEK5130_HID_ID = "0003:0000048D:00005130"
ENEK5130_HID_NAME = "ITE Tech. Inc. ITE Device(8910)"
HWMON_BASE = "/sys/devices/platform/acer-wmi/hwmon"


class HardwareManager:
    """Manages interaction with kernel driver sysfs interfaces and HID reports."""

    def __init__(self, base_override: Optional[str] = None):
        self._base_override = base_override
        self.laptop_type = self._detect_laptop_type()
        self.base_path = self._get_base_path()
        self.has_four_zone_kb = self._check_four_zone_kb()
        self.enek5130_hid_device = self._find_enek5130_hid_device()
        self.available_features: Set[str] = self._detect_available_features()

        # NOS (Nitro Overclocking System) state preservation
        self.is_nos_active: bool = False
        self._pre_nos_profile: Optional[str] = None
        self._pre_nos_fan_speed: Optional[Tuple[int, int]] = None
        self._last_known_profile: Optional[str] = None

    def refresh(self) -> None:
        """Re-probe hardware features and paths."""
        self.laptop_type = self._detect_laptop_type()
        self.base_path = self._get_base_path()
        self.has_four_zone_kb = self._check_four_zone_kb()
        self.enek5130_hid_device = self._find_enek5130_hid_device()
        self.available_features = self._detect_available_features()

    def _detect_laptop_type(self) -> LaptopType:
        if self._base_override:
            if "nitro" in self._base_override.lower():
                return LaptopType.NITRO
            if "predator" in self._base_override.lower():
                return LaptopType.PREDATOR
            return LaptopType.UNKNOWN

        base = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi"
        if os.path.exists(os.path.join(base, "nitro_sense")):
            return LaptopType.NITRO
        if os.path.exists(os.path.join(base, "predator_sense")):
            return LaptopType.PREDATOR
        return LaptopType.UNKNOWN

    def _get_base_path(self) -> str:
        if self._base_override:
            return self._base_override
        base = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi"
        if self.laptop_type == LaptopType.NITRO:
            return os.path.join(base, "nitro_sense")
        if self.laptop_type == LaptopType.PREDATOR:
            return os.path.join(base, "predator_sense")
        return ""

    def _detect_available_features(self) -> Set[str]:
        features: Set[str] = set()

        if os.path.exists("/sys/firmware/acpi/platform_profile"):
            features.add("thermal_profile")

        if self.laptop_type != LaptopType.UNKNOWN and os.path.exists(self.base_path):
            candidates = [
                "backlight_timeout",
                "battery_calibration",
                "battery_limiter",
                "boot_animation_sound",
                "fan_speed",
                "lcd_override",
                "usb_charging",
            ]
            for feat in candidates:
                if os.path.exists(os.path.join(self.base_path, feat)):
                    features.add(feat)

        if self.has_four_zone_kb:
            features.add("four_zone_mode")
            features.add("per_zone_mode")

        if self.enek5130_hid_device:
            features.add("enek5130_hid_rgb")

        return features

    def _check_four_zone_kb(self) -> bool:
        four_zone_path = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb"
        if os.path.exists(four_zone_path):
            return True
        return bool(self._find_enek5130_hid_device())

    def _find_enek5130_hid_device(self) -> str:
        candidates = self._find_enek5130_hid_candidates()
        return candidates[0] if candidates else ""

    def _find_enek5130_hid_candidates(self) -> List[str]:
        candidates: List[str] = []
        for dev in sorted(glob.glob("/dev/hidraw*")):
            uevent_path = f"/sys/class/hidraw/{os.path.basename(dev)}/device/uevent"
            try:
                if os.path.exists(uevent_path):
                    with open(uevent_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if ENEK5130_HID_ID in content or ENEK5130_HID_NAME in content:
                            candidates.append(dev)
            except Exception:
                continue
        return candidates

    def _read_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            log.debug(f"Failed to read {path}: {e}")
            return ""

    def _write_file(self, path: str, value: str) -> bool:
        try:
            if not value.endswith("\n"):
                value += "\n"
            with open(path, "w", encoding="utf-8") as f:
                f.write(value)
            return True
        except Exception as e:
            log.error(f"Failed to write '{value.strip()}' to {path}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Thermal Profiles
    # -------------------------------------------------------------------------

    def get_thermal_profile(self) -> str:
        prof = self._read_file("/sys/firmware/acpi/platform_profile")
        if prof:
            self._last_known_profile = prof
            return prof
        return self._last_known_profile or ""

    def get_supported_profiles(self) -> List[str]:
        raw = self._read_file("/sys/firmware/acpi/platform_profile_choices")
        if raw:
            return raw.split()
        return ["quiet", "balanced", "performance"]

    def set_thermal_profile(self, profile: str) -> bool:
        supported = self.get_supported_profiles()
        if supported and profile not in supported:
            log.error(f"Unsupported thermal profile '{profile}'. Choices: {supported}")
            return False
        if self._write_file("/sys/firmware/acpi/platform_profile", profile):
            self._last_known_profile = profile
            return True
        return False

    def cycle_profile(self, is_ac: Optional[bool] = None) -> Optional[str]:
        """Cycle to the next available thermal profile according to power source.
        
        AC: 3 steps (quiet -> balanced -> performance/balanced-performance)
        Battery: 2 steps (low-power -> balanced)
        Uses in-memory cache to guarantee deterministic consecutive cycling without sysfs race conditions.
        """
        all_supported = self.get_supported_profiles()
        if not all_supported:
            return None

        if is_ac is None:
            from daemon.core.netlink_monitor import read_ac_online
            is_ac = read_ac_online()

        if is_ac:
            perf_choice = "balanced-performance" if "balanced-performance" in all_supported else "performance"
            target_order = ["quiet", "balanced", perf_choice]
            profiles = [p for p in target_order if p in all_supported]
        else:
            target_order = ["low-power", "balanced"]
            profiles = [p for p in target_order if p in all_supported]

        if not profiles:
            profiles = all_supported

        current = self._last_known_profile or self.get_thermal_profile()
        try:
            idx = profiles.index(current)
            next_profile = profiles[(idx + 1) % len(profiles)]
        except ValueError:
            next_profile = profiles[0]

        if self.set_thermal_profile(next_profile):
            return next_profile
        return None

    # -------------------------------------------------------------------------
    # Fan Control & Sensors
    # -------------------------------------------------------------------------

    def get_fan_speed(self) -> Tuple[str, str]:
        """Return configured CPU, GPU fan speeds (0-100 or Auto '0')."""
        raw = self._read_file(os.path.join(self.base_path, "fan_speed"))
        if "," in raw:
            c, g = raw.split(",", 1)
            return c.strip(), g.strip()
        return "0", "0"

    def get_fan_rpms(self) -> Tuple[int, int]:
        """Read live hardware fan RPMs from sysfs hwmon."""
        cpu_rpm, gpu_rpm = 0, 0
        try:
            hwmon_dirs = glob.glob(os.path.join(HWMON_BASE, "hwmon*"))
            if not hwmon_dirs:
                hwmon_dirs = glob.glob("/sys/class/hwmon/hwmon*")

            for h_dir in hwmon_dirs:
                f1 = os.path.join(h_dir, "fan1_input")
                f2 = os.path.join(h_dir, "fan2_input")
                if os.path.isfile(f1):
                    raw = self._read_file(f1)
                    if raw.isdigit():
                        cpu_rpm = int(raw)
                if os.path.isfile(f2):
                    raw = self._read_file(f2)
                    if raw.isdigit():
                        gpu_rpm = int(raw)
                if cpu_rpm > 0 or gpu_rpm > 0:
                    break
        except Exception as e:
            log.debug(f"Error reading fan RPMs: {e}")
        return cpu_rpm, gpu_rpm

    def set_fan_speed(self, cpu: int, gpu: int) -> bool:
        """
        Set CPU and GPU fan speeds.
        Preserves discrete 0 (Auto) vs manual percentage.
        Prevents fan motor stall by enforcing minimum safe PWM (20%) on manual values.
        """
        if "fan_speed" not in self.available_features:
            log.warning("fan_speed feature not available")
            return False

        # Validate input bounds
        cpu = max(0, min(100, int(cpu)))
        gpu = max(0, min(100, int(gpu)))

        if cpu == 0 and gpu == 0:
            # Full Auto Mode
            payload = "0,0"
        elif cpu == 100 and gpu == 100:
            # Full Max Mode
            payload = "100,100"
        elif cpu == 0 and gpu > 0:
            # CPU Auto, GPU Manual (Clamp GPU to minimum 20% to avoid stall)
            gpu_safe = max(20, gpu)
            payload = f"0,{gpu_safe}"
        elif cpu > 0 and gpu == 0:
            # CPU Manual (Clamp CPU to minimum 20%), GPU Auto
            cpu_safe = max(20, cpu)
            payload = f"{cpu_safe},0"
        else:
            # Both Manual
            cpu_safe = max(20, cpu)
            gpu_safe = max(20, gpu)
            payload = f"{cpu_safe},{gpu_safe}"

        log.info(f"Writing fan_speed payload: '{payload}' (requested cpu={cpu}, gpu={gpu})")
        return self._write_file(os.path.join(self.base_path, "fan_speed"), payload)

    # -------------------------------------------------------------------------
    # NOS (Nitro Overclocking System)
    # -------------------------------------------------------------------------

    def activate_nos(self) -> bool:
        """Enter NOS Mode: Maximum fan cooling and peak performance profile."""
        if self.is_nos_active:
            return True

        self._pre_nos_profile = self.get_thermal_profile()
        c_str, g_str = self.get_fan_speed()
        self._pre_nos_fan_speed = (int(c_str) if c_str.isdigit() else 0,
                                   int(g_str) if g_str.isdigit() else 0)

        # Force highest profile
        supported = self.get_supported_profiles()
        target_profile = "performance"
        for candidate in ["turbo", "performance", "balanced-performance"]:
            if candidate in supported:
                target_profile = candidate
                break

        self.set_thermal_profile(target_profile)
        self.set_fan_speed(100, 100)
        self.is_nos_active = True
        log.info("NOS mode activated (Max fans + Turbo profile)")
        return True

    def deactivate_nos(self) -> bool:
        """Exit NOS Mode: Restore previous profile and fan speed."""
        if not self.is_nos_active:
            return True

        if self._pre_nos_profile:
            self.set_thermal_profile(self._pre_nos_profile)
        if self._pre_nos_fan_speed:
            self.set_fan_speed(*self._pre_nos_fan_speed)
        else:
            self.set_fan_speed(0, 0)

        self.is_nos_active = False
        log.info("NOS mode deactivated (Restored previous settings)")
        return True

    # -------------------------------------------------------------------------
    # Miscellaneous Hardware Features
    # -------------------------------------------------------------------------

    def set_backlight_timeout(self, enabled: bool) -> bool:
        return self._write_file(os.path.join(self.base_path, "backlight_timeout"), "1" if enabled else "0")

    def get_backlight_timeout(self) -> str:
        return self._read_file(os.path.join(self.base_path, "backlight_timeout"))

    def set_battery_limiter(self, enabled: bool) -> bool:
        return self._write_file(os.path.join(self.base_path, "battery_limiter"), "1" if enabled else "0")

    def get_battery_limiter(self) -> str:
        return self._read_file(os.path.join(self.base_path, "battery_limiter"))

    def set_battery_calibration(self, enabled: bool) -> bool:
        return self._write_file(os.path.join(self.base_path, "battery_calibration"), "1" if enabled else "0")

    def get_battery_calibration(self) -> str:
        return self._read_file(os.path.join(self.base_path, "battery_calibration"))

    def set_boot_animation_sound(self, enabled: bool) -> bool:
        return self._write_file(os.path.join(self.base_path, "boot_animation_sound"), "1" if enabled else "0")

    def get_boot_animation_sound(self) -> str:
        return self._read_file(os.path.join(self.base_path, "boot_animation_sound"))

    def set_lcd_override(self, enabled: bool) -> bool:
        return self._write_file(os.path.join(self.base_path, "lcd_override"), "1" if enabled else "0")

    def get_lcd_override(self) -> str:
        return self._read_file(os.path.join(self.base_path, "lcd_override"))

    def set_usb_charging(self, level: int) -> bool:
        if level not in [0, 10, 20, 30]:
            return False
        return self._write_file(os.path.join(self.base_path, "usb_charging"), str(level))

    def get_usb_charging(self) -> str:
        return self._read_file(os.path.join(self.base_path, "usb_charging"))

    # -------------------------------------------------------------------------
    # Keyboard RGB (Sysfs + ENEK5130 HID)
    # -------------------------------------------------------------------------

    def set_per_zone_mode(self, zone1: str, zone2: str, zone3: str, zone4: str, brightness: int) -> bool:
        zones = [zone1, zone2, zone3, zone4]
        brightness = max(0, min(100, brightness))

        # Check ENEK5130 HID first
        if self.enek5130_hid_device:
            if self._set_enek5130_per_zone_color(zones, brightness):
                return True

        four_zone_path = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/per_zone_mode"
        payload = f"{zone1},{zone2},{zone3},{zone4},{brightness}"
        return self._write_file(four_zone_path, payload)

    def set_four_zone_mode(self, mode: int, speed: int, brightness: int, direction: int,
                           red: int, green: int, blue: int) -> bool:
        mode = max(0, min(7, mode))
        speed = max(0, min(9, speed))
        brightness = max(0, min(100, brightness))
        direction = max(1, min(2, direction))
        red, green, blue = max(0, min(255, red)), max(0, min(255, green)), max(0, min(255, blue))

        if self.enek5130_hid_device:
            if mode == 0:
                if self._set_enek5130_static_color(red, green, blue, brightness):
                    return True
            else:
                if self._set_enek5130_effect(mode, speed, brightness, direction, red, green, blue):
                    return True

        four_zone_path = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/four_zone_mode"
        payload = f"{mode},{speed},{brightness},{direction},{red},{green},{blue}"
        return self._write_file(four_zone_path, payload)

    def _set_enek5130_hid_report(self, effect: int, red: int, green: int, blue: int,
                                 brightness: int, speed: int, direction: int, zone_mask: int) -> bool:
        candidates = self._find_enek5130_hid_candidates()
        if self.enek5130_hid_device and self.enek5130_hid_device not in candidates:
            candidates.insert(0, self.enek5130_hid_device)
        if not candidates:
            return False

        packet = bytes([
            0xA4, 0x21,
            effect & 0xFF,
            brightness & 0xFF,
            speed & 0xFF,
            direction & 0xFF,
            red & 0xFF,
            green & 0xFF,
            blue & 0xFF,
            zone_mask & 0xFF,
            0x00
        ])

        for dev in candidates:
            try:
                fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
                try:
                    import fcntl
                    HIDIOCSFEATURE_11 = 0xC00B4806
                    fcntl.ioctl(fd, HIDIOCSFEATURE_11, packet)
                    self.enek5130_hid_device = dev
                    return True
                finally:
                    os.close(fd)
            except Exception as e:
                log.debug(f"ENEK5130 write attempt on {dev} failed: {e}")
                continue
        return False

    def _set_enek5130_per_zone_color(self, zones: List[str], brightness: int) -> bool:
        zone_masks = [0x01, 0x02, 0x04, 0x08]
        for zone, mask in zip(zones, zone_masks):
            if len(zone) >= 6:
                r = int(zone[0:2], 16)
                g = int(zone[2:4], 16)
                b = int(zone[4:6], 16)
                if not self._set_enek5130_hid_report(0x02, r, g, b, brightness, 0x00, 0x00, mask):
                    return False
        return True

    def _set_enek5130_static_color(self, red: int, green: int, blue: int, brightness: int) -> bool:
        return self._set_enek5130_hid_report(0x02, red, green, blue, brightness, 0x00, 0x00, 0x0F)

    def _set_enek5130_effect(self, mode: int, speed: int, brightness: int, direction: int,
                             red: int, green: int, blue: int) -> bool:
        # Mapping mode to HID effect codes
        mapping = {
            1: (0x01, False),  # Breathing
            2: (0x02, False),  # Neon
            3: (0x03, True),   # Wave
            4: (0x04, True),   # Shifting
            5: (0x05, True),   # Zoom
            6: (0x06, True),   # Meteor
            7: (0x07, True),   # Twinkling
        }
        if mode not in mapping:
            return False
        effect, _ = mapping[mode]
        hid_speed = speed if effect in [0x04, 0x05] else min(10, max(1, speed + 1))
        return self._set_enek5130_hid_report(effect, red, green, blue, brightness, hid_speed, direction, 0x0F)

#!/usr/bin/env python3
# AcerSense-Daemon - Manage Acer laptop features as root service communicating with Linuwu-sense drivers
# Compatible with Predator and Nitro laptops

import os
import subprocess
import sys
import json
import time
import argparse
import logging
import logging.handlers
import socket
import threading
import signal
import configparser
import traceback
import glob
import pwd
from pathlib import Path
from enum import Enum
from PowerSourceDetection import PowerSourceDetector 
from typing import Dict, List, Tuple, Set

# Constants
VERSION = "1.0"
SOCKET_PATH = "/var/run/AcerSense.sock"
LOG_PATH = "/var/log/AcerSenseDaemon.log"
CONFIG_PATH = "/etc/AcerSenseDaemon/config.ini"
PID_FILE = "/var/run/AcerSense-Daemon.pid"
MODPROBE_CONFIG_PATH = "/etc/modprobe.d/linuwu-sense.conf"

# Check if running as root
if os.geteuid() != 0:
    print("This daemon must run as root. Please use sudo or run as root.")
    sys.exit(1)

# Configure logging
log = logging.getLogger("AcerSenseDaemon")
log.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
log.addHandler(console_handler)

# File handler with rotation
file_handler = logging.handlers.RotatingFileHandler(
    LOG_PATH, maxBytes=1024*1024*5, backupCount=5)
file_handler.setFormatter(formatter)
log.addHandler(file_handler)

class LaptopType(Enum):
    UNKNOWN = 0
    PREDATOR = 1
    NITRO = 2

class AcerSenseManager:
    """Manages all the daemon features"""

    MAX_RESTART_ATTEMPTS = 20
    RESTART_COUNTER_FILE = "/tmp/acersense_daemon_restart_attempts"

    def __init__(self):
        '''The initial init (i know very nice description)'''
        log.info(f"** Starting AcerSense daemon v{VERSION} **")
        
        self.event_callback = None  # Callback for async broadcast

        # Check if linuwu_sense is installed
        if not os.path.exists("/sys/module/linuwu_sense"):
            log.error("linuwu_sense module not found. Please install the linuwu_sense driver first.")
        else:
            log.info("linuwu_sense module found. Proceeding with initialization.")
        
        self.laptop_type = self._detect_laptop_type()

        #added a delay so that driver sets up properly first
        time.sleep(0.2)

        # If unknown laptop type detected, try restarting drivers (with limit)
        if self.laptop_type == LaptopType.UNKNOWN:
            current_attempts = self._get_restart_attempts()
            
            if current_attempts < self.MAX_RESTART_ATTEMPTS:
                attempts = self._increment_restart_attempts()
                log.warning(f"Unknown laptop type detected, attempting driver restart (attempt {attempts}/{self.MAX_RESTART_ATTEMPTS})...")
                
                if self._restart_drivers_and_daemon():
                    # The daemon will restart itself, so we should exit this instance
                    log.info("Driver restart initiated, daemon will restart automatically")
                    sys.exit(0)
                else:
                    log.error(f"Failed to restart drivers (attempt {attempts}), continuing with limited functionality")
            else:
                log.error(f"Maximum restart attempts ({self.MAX_RESTART_ATTEMPTS}) reached, giving up on driver restart")
                log.info("Continuing with unknown laptop type and limited functionality")
        else:
            # Reset counter on successful detection
            self._reset_restart_attempts()
        
        self.base_path = self._get_base_path()
        self.has_four_zone_kb = self._check_four_zone_kb()
        self.current_modprobe_param = self._detect_current_modprobe_param()

        # Available features set
        self.available_features = self._detect_available_features()
        self.nos_active = False
        self.previous_profile_for_nos = None
        # Read the initial real state to prevent race conditions on start
        self.last_known_profile = self.get_thermal_profile()

        # Apply the correct default profile immediately and synchronously on startup
        self._load_defaults()
        self._apply_initial_profile()

    def register_event_callback(self, callback):
        """Register a callback function to be called when an event occurs"""
        self.event_callback = callback

    def _notify_event(self, event_type: str, data: Dict):
        """Notify registered callback of an event"""
        if self.event_callback:
            try:
                # The callback is responsible for being thread-safe or thread-aware
                self.event_callback(event_type, data)
            except Exception as e:
                log.error(f"Error in event callback: {e}")

    def _load_defaults(self):
        """Load default profile preferences and opacity settings from config"""
        self.default_ac_profile = "balanced"
        self.default_bat_profile = "low-power"
        
        # Opacity defaults
        self.ac_active_opacity = 0.97
        self.ac_inactive_opacity = 0.95
        self.bat_active_opacity = 1.0
        self.bat_inactive_opacity = 1.0
        
        try:
            if os.path.exists(CONFIG_PATH):
                config = configparser.ConfigParser()
                config.read(CONFIG_PATH)
                if 'General' in config:
                    self.default_ac_profile = config['General'].get('DefaultAcProfile', "balanced")
                    self.default_bat_profile = config['General'].get('DefaultBatProfile', "low-power")
                    self.hyprland_integration = config['General'].getboolean('HyprlandIntegration', fallback=False)
                    
                    self.ac_active_opacity = config['General'].getfloat('AcActiveOpacity', 0.97)
                    self.ac_inactive_opacity = config['General'].getfloat('AcInactiveOpacity', 0.95)
                    self.bat_active_opacity = config['General'].getfloat('BatActiveOpacity', 1.0)
                    self.bat_inactive_opacity = config['General'].getfloat('BatInactiveOpacity', 1.0)
        except Exception as e:
            log.error(f"Failed to load defaults: {e}")

    def set_hyprland_opacity_settings(self, ac_active: float, ac_inactive: float, bat_active: float, bat_inactive: float) -> bool:
        """Set Hyprland opacity settings"""
        try:
            self.ac_active_opacity = ac_active
            self.ac_inactive_opacity = ac_inactive
            self.bat_active_opacity = bat_active
            self.bat_inactive_opacity = bat_inactive
            
            config = configparser.ConfigParser()
            config.read(CONFIG_PATH)
            if 'General' not in config:
                config['General'] = {}
            
            config['General']['AcActiveOpacity'] = str(ac_active)
            config['General']['AcInactiveOpacity'] = str(ac_inactive)
            config['General']['BatActiveOpacity'] = str(bat_active)
            config['General']['BatInactiveOpacity'] = str(bat_inactive)
            
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
            
            log.info("Updated Hyprland opacity settings")
            # Apply immediately based on current profile
            self._update_hyprland_visuals(self.last_known_profile)
            return True
        except Exception as e:
            log.error(f"Failed to save opacity settings: {e}")
            return False

    def set_default_profile_preference(self, source: str, profile: str) -> bool:
        """Set default profile for AC or Battery"""
        try:
            config = configparser.ConfigParser()
            config.read(CONFIG_PATH)
            if 'General' not in config:
                config['General'] = {}

            if source == "ac":
                self.default_ac_profile = profile
                config['General']['DefaultAcProfile'] = profile
            elif source == "bat":
                self.default_bat_profile = profile
                config['General']['DefaultBatProfile'] = profile
            else:
                return False

            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
            
            log.info(f"Updated default profile for {source} to {profile}")
            return True
        except Exception as e:
            log.error(f"Failed to save default profile: {e}")
            return False

    def _apply_initial_profile(self):
        """Applies the default thermal profile based on the current power source at startup."""
        log.info("Applying initial default thermal profile...")
        try:
            is_ac_online_path = next((p for p in ["/sys/class/power_supply/AC/online", "/sys/class/power_supply/ACAD/online", "/sys/class/power_supply/ADP1/online", "/sys/class/power_supply/AC0/online"] if os.path.exists(p)), None)
            is_ac = self._read_file(is_ac_online_path) == "1" if is_ac_online_path else False
            
            profile_list = self.get_thermal_profile_choices()
            target_profile = self.default_ac_profile if is_ac else self.default_bat_profile

            if target_profile in profile_list:
                log.info(f"Setting initial default profile to: {target_profile}")
                self.set_thermal_profile(target_profile)
            else:
                log.warning(f"Initial default profile '{target_profile}' not available. Skipping.")
        except Exception as e:
            log.error(f"Failed to apply initial default profile: {e}")


        log.info(f"Detected laptop type: {self.laptop_type.name}")
        log.info(f"Base path: {self.base_path}")
        log.info(f"Four-zone keyboard: {'Yes' if self.has_four_zone_kb else 'No'}")
        log.info(f"Available features: {', '.join(self.available_features)}")

        # Check if paths exist
        if not os.path.exists(self.base_path) and self.laptop_type != LaptopType.UNKNOWN:
            log.error(f"Base path does not exist: {self.base_path}")
            raise FileNotFoundError(f"Base path does not exist: {self.base_path}")
        
        self.power_monitor = None

    def _get_restart_attempts(self) -> int:
        """Get current restart attempt count"""
        try:
            if os.path.exists(self.RESTART_COUNTER_FILE):
                with open(self.RESTART_COUNTER_FILE, 'r') as f:
                    return int(f.read().strip())
        except (ValueError, IOError):
            pass
        return 0

    def _increment_restart_attempts(self) -> int:
        """Increment and return restart attempt count"""
        attempts = self._get_restart_attempts() + 1
        try:
            with open(self.RESTART_COUNTER_FILE, 'w') as f:
                f.write(str(attempts))
        except IOError as e:
            log.error(f"Failed to write restart counter: {e}")
        return attempts

    def _reset_restart_attempts(self):
        """Reset restart attempt counter"""
        try:
            if os.path.exists(self.RESTART_COUNTER_FILE):
                os.unlink(self.RESTART_COUNTER_FILE)
        except IOError as e:
            log.error(f"Failed to reset restart counter: {e}")

    def _force_model_nitro(self):
        """Restart linuwu-sense driver and AcerSense daemon service with nitro_v4 parameter"""
        log.info("Forcing model detection to Nitro by restarting drivers and AcerSense daemon")

        try:
            # Remove the module
            subprocess.run(['sudo', 'rmmod', 'linuwu-sense'], check=True)
            log.info("Successfully removed linuwu-sense module")
            
            # Wait a moment
            time.sleep(2)
            
            # Reload the module
            subprocess.run(['sudo', 'modprobe', 'linuwu-sense', 'nitro_v4'], check=True)
            log.info("Successfully reloaded linuwu-sense module")
            
            # Wait a moment for module to initialize
            time.sleep(3)
            
            # Restart the daemon service
            log.info("Restarting AcerSense daemon service (may produce an error)")
            subprocess.run(['sudo', 'systemctl', 'restart', 'acersense-daemon.service'], check=True)

            return True
        
        except Exception as e:
            log.error(f"Unexpected error while Forcing Nitro Model: {e}")
            return False
        

    def _force_model_predator(self):
        """Restart linuwu-sense driver and AcerSense daemon service with nitro_v4 parameter"""
        log.info("Forcing model detection to Nitro by restarting drivers and daemon")

        try:
            # Remove the module
            subprocess.run(['sudo', 'rmmod', 'linuwu-sense'], check=True)
            log.info("Successfully removed linuwu-sense module")
            
            # Wait a moment
            time.sleep(2)
            
            # Reload the module
            subprocess.run(['sudo', 'modprobe', 'linuwu-sense', 'predator_v4'], check=True)
            log.info("Successfully reloaded linuwu-sense module")
            
            # Wait a moment for module to initialize
            time.sleep(3)
            
            # Restart the daemon service
            log.info("Restarting AcerSense daemon service (may produce an error)")
            subprocess.run(['sudo', 'systemctl', 'restart', 'acersense-daemon.service'], check=True)
            
            return True
        
        except Exception as e:
            log.error(f"Unexpected error while Forcing Nitro Model: {e}")
            return False
    
    def _force_enable_all(self):
        """Restart linuwu-sense driver and AcerSense daemon service with enable_all parameter"""
        log.info("Forcing all features by restarting daemon and drivers with parameter enable_all")

        try:
            # Remove the module
            subprocess.run(['sudo', 'rmmod', 'linuwu-sense'], check=True)
            log.info("Successfully removed linuwu-sense module")
            
            # Wait a moment
            time.sleep(2)
            
            # Reload the module
            subprocess.run(['sudo', 'modprobe', 'linuwu-sense', 'enable_all'], check=True)
            log.info("Successfully reloaded linuwu-sense module with enable_all parameter")
            
            # Wait a moment for module to initialize
            time.sleep(3)
            
            # Restart the daemon service
            log.info("Restarting AcerSense daemon service (may produce an error)")
            subprocess.run(['sudo', 'systemctl', 'restart', 'acersense-daemon.service'], check=True)

            return True
        
        except Exception as e:
            log.error(f"Unexpected error while Forcing All Features: {e}")
            return False
        
    def _detect_current_modprobe_param(self) -> str:
        """Detect which modprobe parameter is currently set"""
        try:
            if os.path.exists(MODPROBE_CONFIG_PATH):
                with open(MODPROBE_CONFIG_PATH, 'r') as f:
                    content = f.read().strip().lower()
                    if "nitro_v4" in content:
                        return "nitro_v4"
                    elif "predator_v4" in content:
                        return "predator_v4"
                    elif "enable_all" in content:
                        return "enable_all"
        except Exception as e:
            log.error(f"Failed to read modprobe config: {e}")
        return ""

    def _set_modprobe_parameter(self, param: str) -> bool:
        """Set modprobe parameter in config file"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(MODPROBE_CONFIG_PATH), exist_ok=True)
            
            # Write the config file
            with open(MODPROBE_CONFIG_PATH, 'w') as f:
                f.write(f"options linuwu_sense {param}=1\n")
            
            log.info(f"Set modprobe parameter: {param}")
            self.current_modprobe_param = param
            return True
        except Exception as e:
            log.error(f"Failed to set modprobe parameter: {e}")
            return False

    def _remove_modprobe_parameter(self) -> bool:
        """Remove modprobe parameter config file"""
        try:
            if os.path.exists(MODPROBE_CONFIG_PATH):
                os.unlink(MODPROBE_CONFIG_PATH)
                log.info("Removed modprobe parameter config")
            self.current_modprobe_param = ""
            return True
        except Exception as e:
            log.error(f"Failed to remove modprobe parameter: {e}")
            return False

    def get_modprobe_parameter(self) -> str:
        """Get current modprobe parameter"""
        return self.current_modprobe_param

    def set_modprobe_parameter(self, param: str) -> bool:
        """Set modprobe parameter and restart drivers"""
        if param not in ["nitro_v4", "predator_v4", "enable_all", ""]:
            log.error(f"Invalid modprobe parameter: {param}")
            return False
        
        if param == "":
            # Remove parameter
            if not self._remove_modprobe_parameter():
                return False
        else:
            # Set parameter
            if not self._set_modprobe_parameter(param):
                return False
        
        # Restart drivers and daemon
        return self._restart_drivers_and_daemon()
        
    def _restart_daemon(self):
        """Restart AcerSense daemon service alone"""
        attempts = self._get_restart_attempts()
        log.info(f"Attempting to restart AcerSense daemon")
        
        try:
            # Restart the daemon service
            log.info("Restarting AcerSense daemon service (may produce an error)")
            subprocess.run(['sudo', 'systemctl', 'restart', 'acersense-daemon.service'], check=True)
            
            return True
            
        except Exception as e:
            log.error(f"Unexpected error during restart (attempt {attempts}): {e}")
            return False
            

    def _restart_drivers_and_daemon(self):
        """Restart linuwu-sense driver and AcerSense daemon service"""
        attempts = self._get_restart_attempts()
        log.info(f"Attempting to restart drivers and daemon (attempt {attempts}/{self.MAX_RESTART_ATTEMPTS})...")
        
        try:
            # Remove the module
            subprocess.run(['sudo', 'rmmod', 'linuwu-sense'], check=True)
            log.info("Successfully removed linuwu-sense module")
            
            # Wait a moment
            time.sleep(2)
            
            # Reload the module
            subprocess.run(['sudo', 'modprobe', 'linuwu-sense'], check=True)
            log.info("Successfully reloaded linuwu-sense module")
            
            # Wait a moment for module to initialize
            time.sleep(3)
            
            # Restart the daemon service
            log.info("Restarting AcerSense daemon service (may produce an error)")
            subprocess.run(['sudo', 'systemctl', 'restart', 'acersense-daemon.service'], check=True)

            return True
            
        except Exception as e:
            log.error(f"Unexpected error during restart (attempt {attempts}): {e}")
            return False
            
    def _detect_laptop_type(self) -> LaptopType:
        """Detect whether this is a Predator or Nitro laptop"""
        predator_path = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/predator_sense"
        nitro_path = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/nitro_sense"

        if os.path.exists(predator_path):
            return LaptopType.PREDATOR
        elif os.path.exists(nitro_path):
            return LaptopType.NITRO
        else:
            return LaptopType.UNKNOWN

    def _get_base_path(self) -> str:
        """Get the base path for VFS access based on laptop type"""
        if self.laptop_type == LaptopType.PREDATOR:
            return "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/predator_sense"
        elif self.laptop_type == LaptopType.NITRO:
            return "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/nitro_sense"
        else:
            return ""

    def get_driver_version(self) -> str:
        """Get Driver version"""
        version_file = os.path.join(self.base_path, "version")
        if not os.path.isfile(version_file):
            return "Unknown Version"
        
        try:
            with open(version_file, "r") as f:
                return f.read().strip() or "Unknown Version"
        except (OSError, IOError):
            return "Unknown Version"
    

    def _detect_available_features(self) -> Set[str]:
        """Detect which features are available on the current laptop"""
        available = set()

        # Always check thermal profile since it's ACPI standard
        if os.path.exists("/sys/firmware/acpi/platform_profile"):
            available.add("thermal_profile")

        # Only check other features if laptop type is recognized
        if self.laptop_type != LaptopType.UNKNOWN and os.path.exists(self.base_path):
            feature_files = [
                ("backlight_timeout", "backlight_timeout"),
                ("battery_calibration", "battery_calibration"),
                ("battery_limiter", "battery_limiter"),
                ("boot_animation_sound", "boot_animation_sound"),
                ("fan_speed", "fan_speed"),
                ("lcd_override", "lcd_override"),
                ("usb_charging", "usb_charging"),
            ]

            for feature_name, file_name in feature_files:
                file_path = os.path.join(self.base_path, file_name)
                if os.path.exists(file_path):
                    available.add(feature_name)

        # Check keyboard features
        if self.has_four_zone_kb:
            kb_base = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb"
            if os.path.exists(os.path.join(kb_base, "per_zone_mode")):
                available.add("per_zone_mode")
            if os.path.exists(os.path.join(kb_base, "four_zone_mode")):
                available.add("four_zone_mode")

        return available

    def _check_four_zone_kb(self) -> bool:
        """Check if four-zone keyboard is available"""
        if self.laptop_type != LaptopType.UNKNOWN:
            kb_path = "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb"
            return os.path.exists(kb_path)
        return False

    def _read_file(self, path: str) -> str:
        """Read from a VFS file"""
        try:
            with open(path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            log.error(f"Failed to read from {path}: {e}")
            return ""

    def _write_file(self, path: str, value: str) -> bool:
        """Write to a VFS file"""
        try:
            with open(path, 'w') as f:
                f.write(str(value))
            return True
        except Exception as e:
            log.error(f"Failed to write to {path}: {e}")
            return False

    def get_thermal_profile(self) -> str:
        """Get current thermal profile"""
        if "thermal_profile" not in self.available_features:
            return ""
        return self._read_file("/sys/firmware/acpi/platform_profile")

    def set_thermal_profile(self, profile: str) -> bool:
        """Set thermal profile with validation and fallback"""
        if "thermal_profile" not in self.available_features:
            return False

        available_profiles = self.get_thermal_profile_choices()
        
        # Handle mapping/fallback if profile not directly supported
        if profile not in available_profiles:
            log.warning(f"Profile '{profile}' not supported by hardware. Attempting fallback...")
            if profile == "balanced-performance":
                if "performance" in available_profiles:
                    profile = "performance"
                elif "balanced" in available_profiles:
                    profile = "balanced"
            elif profile == "quiet":
                if "low-power" in available_profiles:
                    profile = "low-power"
            
            # Final check
            if profile not in available_profiles:
                log.error(f"Cannot map profile '{profile}' to any available choice: {available_profiles}")
                return False
            
            log.info(f"Mapped to valid profile: {profile}")

        success = self._write_file("/sys/firmware/acpi/platform_profile", profile)
        if success:
            self.last_known_profile = profile # Update internal state immediately
            self._update_hyprland_visuals(profile)
            self._apply_profile_optimizations(profile)
            
            # Broadcast Event
            self._notify_event("thermal_profile_changed", {"profile": profile})
            
        return success

    def _apply_profile_optimizations(self, profile: str):
        """Apply advanced power optimizations (CPU EPP, WiFi, Turbo) based on profile"""
        try:
            # 1. Detect Power Source
            is_ac = False
            # Check standard paths
            for p in ["/sys/class/power_supply/AC/online", "/sys/class/power_supply/ACAD/online", "/sys/class/power_supply/ADP1/online", "/sys/class/power_supply/AC0/online"]:
                if os.path.exists(p) and self._read_file(p) == "1":
                    is_ac = True
                    break
            
            # 2. Determine Settings
            epp = "balance_performance"
            wifi_power = "off"
            turbo = "0" # 0 = Enabled, 1 = Disabled
            
            if is_ac:
                if profile == "quiet":
                    epp = "balance_power"
                elif profile == "balanced":
                    epp = "balance_performance"
                elif profile in ["performance", "balanced-performance"]:
                    epp = "performance"
            else: # Battery
                wifi_power = "on"
                if profile == "balanced":
                    epp = "balance_power"
                elif profile == "low-power":
                    epp = "power"
                    turbo = "1" # Disable Turbo for max savings

            log.info(f"Applying Optimizations -> Profile: {profile}, AC: {is_ac}, EPP: {epp}, WiFi: {wifi_power}, Turbo: {'Off' if turbo=='1' else 'On'}")

            # 3. Apply CPU EPP (Energy Performance Preference)
            # AMD systems use 'scaling_governor' or separate EPP file usually.
            # Intel systems use 'energy_performance_preference'.
            # We try to apply to all CPUs
            cpus = glob.glob("/sys/devices/system/cpu/cpu[0-9]*")
            for cpu in cpus:
                epp_path = os.path.join(cpu, "cpufreq/energy_performance_preference")
                if os.path.exists(epp_path):
                    try:
                        with open(epp_path, 'w') as f:
                            f.write(epp)
                    except IOError:
                        pass # Some governors don't support EPP

            # 4. Apply Turbo Boost (Intel P-State)
            no_turbo_path = "/sys/devices/system/cpu/intel_pstate/no_turbo"
            if os.path.exists(no_turbo_path):
                try:
                    with open(no_turbo_path, 'w') as f:
                        f.write(turbo)
                except IOError as e:
                    log.warning(f"Failed to set Turbo Boost: {e}")

            # 5. Apply WiFi Power Save
            # Find wireless interfaces
            try:
                interfaces = os.listdir("/sys/class/net")
                for iface in interfaces:
                    # Check if wireless (wlan0, wlp*, etc)
                    if iface.startswith("wl"):
                        subprocess.run(["iw", "dev", iface, "set", "power_save", wifi_power], 
                                     check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                log.warning(f"Failed to set WiFi power save: {e}")

            # --- Advanced System Optimizations (TLP Replacement) ---
            
            # 6. Audio Power Save (snd_hda_intel)
            audio_power = "1" if not is_ac or profile == "quiet" else "0"
            self._write_file_safe("/sys/module/snd_hda_intel/parameters/power_save", audio_power)
            
            # 7. NMI Watchdog (Disable on battery to save CPU wakeups)
            nmi_watchdog = "1" if is_ac else "0"
            self._write_file_safe("/proc/sys/kernel/nmi_watchdog", nmi_watchdog)

            # 8. VM Writeback Timeout (Longer on battery to keep disk asleep)
            # 1500 (15s) on AC, 6000 (60s) on Battery
            vm_writeback = "1500" if is_ac else "6000"
            self._write_file_safe("/proc/sys/vm/dirty_writeback_centisecs", vm_writeback)

            # 9. PCIe ASPM (Active State Power Management)
            # 'default' (BIOS) on AC, 'powersave' on Battery
            # Note: Some systems might not allow changing this at runtime
            aspm_policy = "default" if is_ac else "powersave"
            self._write_file_safe("/sys/module/pcie_aspm/parameters/policy", aspm_policy)

            # 10. SATA/AHCI Link Power Management
            # 'max_performance' on AC, 'med_power_with_dipm' on Battery
            sata_policy = "max_performance" if is_ac else "med_power_with_dipm"
            sata_hosts = glob.glob("/sys/class/scsi_host/host*/link_power_management_policy")
            for host in sata_hosts:
                self._write_file_safe(host, sata_policy)

            # 11. USB Autosuspend (usbcore)
            # -1 = Disabled, 2 = Enable (2 seconds delay)
            usb_autosuspend = "-1" if is_ac else "2"
            self._write_file_safe("/sys/module/usbcore/parameters/autosuspend", usb_autosuspend)

        except Exception as e:
            log.error(f"Error applying optimizations: {e}")
            log.error(traceback.format_exc())

    def _write_file_safe(self, path, value):
        """Helper to write to a file only if it exists, suppressing errors"""
        if os.path.exists(path):
            try:
                with open(path, 'w') as f:
                    f.write(value)
            except IOError:
                pass # Permission denied or immutable

    def _get_hyprland_info(self):
        """Find the active Hyprland instance signature, user, and Wayland display dynamically"""
        base_run_dir = "/run/user"
        if not os.path.exists(base_run_dir):
            return None, None, None

        for user_dir in os.listdir(base_run_dir):
            if not user_dir.isdigit():
                continue
            
            uid = int(user_dir)
            user_run_path = os.path.join(base_run_dir, user_dir)
            hypr_dir = os.path.join(user_run_path, "hypr")
            
            # Find WAYLAND_DISPLAY
            wayland_display = None
            try:
                # Look for wayland-0, wayland-1, etc.
                for item in os.listdir(user_run_path):
                    if item.startswith("wayland-") and os.path.exists(os.path.join(user_run_path, item)) and "lock" not in item:
                         # Simple heuristic: pick the first one that looks like a socket
                         wayland_display = item
                         break
            except OSError:
                pass

            if os.path.isdir(hypr_dir):
                # Search for signature directories within this user's hypr dir
                for item in os.listdir(hypr_dir):
                    signature_path = os.path.join(hypr_dir, item)
                    if os.path.isdir(signature_path) and "." not in item:
                        try:
                            contents = os.listdir(signature_path)
                            if any(x.endswith(".sock") for x in contents):
                                # Found it!
                                try:
                                    username = pwd.getpwuid(uid).pw_name
                                    log.info(f"Found active Hyprland instance: User={username}, Sig={item}, Display={wayland_display}")
                                    return username, item, wayland_display
                                except KeyError:
                                    continue
                        except OSError:
                            continue
        
        log.warning("No active Hyprland instance found.")
        return None, None, None

    def _write_user_file_atomically(self, path: str, content: list, uid: int, gid: int) -> bool:
        """
        Securely and atomically write a file for a user.
        Handles symlinks by verifying ownership of the target file.
        """
        try:
            target_path = path

            # 1. Security Check: Symlink Handling
            if os.path.islink(path):
                # Resolve the symlink to the real path
                real_path = os.path.realpath(path)
                
                # Get stats of the real path
                try:
                    file_stat = os.stat(real_path)
                except OSError:
                    log.error(f"Cannot stat target of symlink {path}. Aborting.")
                    return False

                # SECURITY: Check if the target file is owned by the user we are writing for.
                # This prevents attacks where a user symlinks to a root-owned file (like /etc/shadow).
                if file_stat.st_uid != uid:
                    log.error(f"SECURITY ALERT: Symlink {path} points to {real_path} which is NOT owned by user {uid}. Aborting.")
                    return False
                
                log.debug(f"Followed safe symlink: {path} -> {real_path}")
                target_path = real_path

            # 2. Prepare Temp File (create it alongside the target to ensure same filesystem)
            tmp_path = target_path + ".tmp"
            
            # 3. Write to Temp File
            with open(tmp_path, 'w') as f:
                if isinstance(content, list):
                    f.writelines(content)
                else:
                    f.write(content)
            
            # 4. Set Permissions on Temp File
            os.chown(tmp_path, uid, gid)
            os.chmod(tmp_path, 0o644) 

            # 5. Atomic Move
            os.replace(tmp_path, target_path)
            return True

        except Exception as e:
            log.error(f"Failed to write file atomically to {path}: {e}")
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            return False

    def _get_user_config_dir(self, user_home: str) -> str:
        """Get the config directory respecting XDG_CONFIG_HOME"""
        # Since we run as root, we can't trust os.environ directly for the target user.
        # We assume standard locations relative to user_home unless we want to parse their shell env (too complex).
        # Standard fallback is reliable enough for this context.
        return os.path.join(user_home, ".config")

    def _ensure_aux_config_files(self, user_home, uid, gid):
        """Create auxiliary config files (bat/charge) if they don't exist"""
        config_dir = os.path.join(self._get_user_config_dir(user_home), "hypr")
        
        # 1. Battery Config
        bat_path = os.path.join(config_dir, "acersense_bat.conf")
        if not os.path.exists(bat_path):
            content = (
                "# AcerSense - Battery Mode Settings\n"
                "# This file is automatically sourced when the device is on BATTERY power.\n"
                "# You can edit this file to customize visuals (Blur, Shadows, Animations) for power saving.\n"
                "\n"
                "decoration {\n"
                "    blur {\n"
                "        enabled = false\n"
                "    }\n"
                "    # drop_shadow = false\n"
                "}\n"
                "\n"
                "# Note: Window Opacity is managed dynamically by the AcerSense App slider.\n"
            )
            if self._write_user_file_atomically(bat_path, content, uid, gid):
                log.info("Created default acersense_bat.conf")

        # 2. Charge/Performance Config
        charge_path = os.path.join(config_dir, "acersense_charge.conf")
        if not os.path.exists(charge_path):
            content = (
                "# AcerSense - Charging/Performance Mode Settings\n"
                "# This file is automatically sourced when the device is PLUGGED IN.\n"
                "# You can edit this file to customize visuals (Blur, Shadows, Animations) for high performance.\n"
                "\n"
                "decoration {\n"
                "    blur {\n"
                "        enabled = true\n"
                "        size = 8\n"
                "        passes = 2\n"
                "    }\n"
                "    # drop_shadow = true\n"
                "}\n"
                "\n"
                "# Note: Window Opacity is managed dynamically by the AcerSense App slider.\n"
            )
            if self._write_user_file_atomically(charge_path, content, uid, gid):
                log.info("Created default acersense_charge.conf")

    def _update_hyprland_visuals(self, profile: str):
        """Update the main acersense.conf to source the correct aux file and set opacity"""
        
        target_user, signature, _ = self._get_hyprland_info()
        if not target_user:
            return

        try:
            # Get User Home and UID/GID
            user_info = pwd.getpwnam(target_user)
            user_home = user_info.pw_dir
            uid = user_info.pw_uid
            gid = user_info.pw_gid
            
            # Ensure aux files exist first (safe to call repeatedly)
            self._ensure_aux_config_files(user_home, uid, gid)
            
            # Target config file (The Manager)
            config_dir = os.path.join(self._get_user_config_dir(user_home), "hypr")
            config_path = os.path.join(config_dir, "acersense.conf")
            
            # Ensure directory exists
            if not os.path.exists(config_dir):
                return
                
            # Content generation
            content = []
            content.append("# AUTO-GENERATED by AcerSense. DO NOT EDIT THIS FILE MANUALLY.\n")
            content.append("# This file switches between _bat.conf and _charge.conf based on power state.\n")
            content.append("# To customize visuals, edit 'acersense_bat.conf' or 'acersense_charge.conf'.\n\n")
            
            # Determine mode based on profile
            is_high_perf = profile in ["balanced", "balanced-performance", "performance", "turbo"]
            
            if is_high_perf:
                active = self.ac_active_opacity
                inactive = self.ac_inactive_opacity
                source_file = "acersense_charge.conf"
            else:
                active = self.bat_active_opacity
                inactive = self.bat_inactive_opacity
                source_file = "acersense_bat.conf"

            # 1. Source the appropriate environment file
            # We use absolute path or ~ relative if we are sure, but relative to config is safer for portability if user moves home (rare)
            # Standard Hyprland: source = ~/.config/hypr/file.conf
            content.append(f"source = ~/.config/hypr/{source_file}\n\n")
            
            # 2. Write Dynamic Opacity Rules (Managed by App)
            content.append(f"# Dynamic Opacity Rules (Managed by App)\n")
            content.append(f"windowrule = match:class .*, opacity {active} override {inactive} override\n")
            
            log.info(f"Updating Hyprland Config -> Sourcing: {source_file}, Opacity: {active}/{inactive}")

            # Secure Write
            if self._write_user_file_atomically(config_path, content, uid, gid):
                # Reload Hyprland
                cmd = [
                    "sudo", "-u", target_user, 
                    "env", 
                    f"XDG_RUNTIME_DIR=/run/user/{uid}", 
                    f"HYPRLAND_INSTANCE_SIGNATURE={signature}", 
                    "hyprctl", "reload"
                ]
                
                subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log.debug("Triggered Hyprland reload")

        except Exception as e:
            log.error(f"Failed to update Hyprland visuals: {e}")

    def _ensure_hyprland_config_source(self):
        """Ensure that acersense.conf is sourced in the main Hyprland config"""
        target_user, _, _ = self._get_hyprland_info()
        if not target_user:
            return

        try:
            user_info = pwd.getpwnam(target_user)
            user_home = user_info.pw_dir
            uid = user_info.pw_uid
            gid = user_info.pw_gid
            
            config_dir = os.path.join(self._get_user_config_dir(user_home), "hypr")
            hypr_config_path = os.path.join(config_dir, "hyprland.conf")
            source_line = "source = ~/.config/hypr/acersense.conf\n"
            
            if not os.path.exists(hypr_config_path):
                return

            # Note: We don't use atomic write here because we are APPENDING to a user-owned file 
            # that might be symlinked intentionally by the user (dotfiles managers like stow).
            # However, we should still check ownership to ensure we aren't writing to root-owned file in user home.
            
            if os.path.islink(hypr_config_path):
                # If it's a symlink, resolving it to real path is usually safer, 
                # but for now we just append if the target is writable.
                pass

            with open(hypr_config_path, 'r') as f:
                content = f.read()
                
            if "acersense.conf" not in content:
                log.info("Injecting source line into hyprland.conf")
                with open(hypr_config_path, 'a') as f:
                    if content and not content.endswith('\n'):
                        f.write('\n')
                    f.write(f"\n# Added by AcerSense for Opacity/Blur control\n{source_line}")
                # We do not chown here because we appended, file ownership shouldn't change.
                
        except Exception as e:
            log.error(f"Failed to ensure Hyprland config source: {e}")

    def _remove_hyprland_config_source(self):
        """Remove the source line from Hyprland config using sed (Direct & Reliable)"""
        target_user, _, _ = self._get_hyprland_info()
        if not target_user:
            log.warning("Cannot remove Hyprland config source: No active user found.")
            return

        try:
            user_info = pwd.getpwnam(target_user)
            user_home = user_info.pw_dir
            uid = user_info.pw_uid
            gid = user_info.pw_gid
            
            config_dir = os.path.join(self._get_user_config_dir(user_home), "hypr")
            hypr_config_path = os.path.join(config_dir, "hyprland.conf")
            
            if not os.path.exists(hypr_config_path):
                log.warning(f"Hyprland config not found at {hypr_config_path}")
                return

            log.info("Removing source line and comments from hyprland.conf using sed...")

            # 1. Delete lines containing "source" AND "acersense.conf"
            # Using sed -i which edits in place
            subprocess.run(["sed", "-i", "/source.*acersense.conf/d", hypr_config_path], check=True)
            
            # 2. Delete lines containing "Added by AcerSense"
            subprocess.run(["sed", "-i", "/Added by AcerSense/d", hypr_config_path], check=True)
            
            # 3. Ensure ownership is correct (sed might change it to root if not careful, though usually preserves)
            os.chown(hypr_config_path, uid, gid)
            
            # 4. Reload Hyprland
            signature = self._get_hyprland_info()[1]
            if signature:
                subprocess.run(["sudo", "-u", target_user, "env", 
                              f"XDG_RUNTIME_DIR=/run/user/{uid}", 
                              f"HYPRLAND_INSTANCE_SIGNATURE={signature}", 
                              "hyprctl", "reload"], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log.info("Hyprland config cleaned and reloaded.")

        except Exception as e:
            log.error(f"Failed to remove Hyprland config source: {e}")

    def set_hyprland_integration(self, enabled: bool) -> bool:
        """Set Hyprland integration status"""
        try:
            log.info(f"Hyprland integration set to: {enabled}")
            
            if enabled:
                log.info("Enabling Hyprland integration logic...")
                self._ensure_hyprland_config_source()
                self._update_hyprland_visuals(self.last_known_profile)
            else:
                log.info("Disabling Hyprland integration logic (Calling Remove)...")
                self._remove_hyprland_config_source()
            
            return True
        except Exception as e:
            log.error(f"Failed to set Hyprland integration: {e}")
            return False

    def get_thermal_profile_choices(self) -> List[str]:
        """Get available thermal profiles"""
        if "thermal_profile" not in self.available_features:
            return []

        choices = self._read_file("/sys/firmware/acpi/platform_profile_choices")
        return choices.split() if choices else []

    def handle_power_change(self, is_plugged_in: bool):
        """Handles power source changes by setting the appropriate default thermal profile."""
        log.info(f"Manager handling power change. Plugged in: {is_plugged_in}")
        
        profile_list = self.get_thermal_profile_choices()
        
        if is_plugged_in:
            target_profile = self.default_ac_profile
        else:
            target_profile = self.default_bat_profile

        # Immediately update visuals to prevent lag/flicker
        # If we are unplugged, force opaque immediately even before setting profile
        self._update_hyprland_visuals(target_profile)

        if target_profile in profile_list:
            log.info(f"Setting default profile to: {target_profile}")
            self.set_thermal_profile(target_profile)
            
            # Schedule a retry chain to enforce the profile (Total 3 attempts over 4-6 seconds)
            threading.Timer(2.0, lambda: self._enforce_profile(target_profile, retries=2)).start()
        else:
            log.warning(f"Default profile '{target_profile}' not available. Skipping auto-switch.")

    def _enforce_profile(self, profile, retries=0):
        """Retry setting profile and visuals to ensure it sticks"""
        log.info(f"Enforcing profile: {profile} (Retries left: {retries})")
        # Re-apply everything
        self.set_thermal_profile(profile)
        self._update_hyprland_visuals(profile)
        
        if retries > 0:
             threading.Timer(2.0, lambda: self._enforce_profile(profile, retries - 1)).start()

    def get_backlight_timeout(self) -> str:
        """Get backlight timeout status"""
        if "backlight_timeout" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "backlight_timeout"))

    def set_backlight_timeout(self, enabled: bool) -> bool:
        """Set backlight timeout status"""
        if "backlight_timeout" not in self.available_features:
            return False

        return self._write_file(
            os.path.join(self.base_path, "backlight_timeout"),
            "1" if enabled else "0"
        )

    def get_battery_calibration(self) -> str:
        """Get battery calibration status"""
        if "battery_calibration" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "battery_calibration"))

    def set_battery_calibration(self, enabled: bool) -> bool:
        """Start or stop battery calibration"""
        if "battery_calibration" not in self.available_features:
            return False

        return self._write_file(
            os.path.join(self.base_path, "battery_calibration"),
            "1" if enabled else "0"
        )

    def get_battery_limiter(self) -> str:
        """Get battery limiter status"""
        if "battery_limiter" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "battery_limiter"))

    def set_battery_limiter(self, enabled: bool) -> bool:
        """Set battery limiter status"""
        if "battery_limiter" not in self.available_features:
            return False

        return self._write_file(
            os.path.join(self.base_path, "battery_limiter"),
            "1" if enabled else "0"
        )

    def get_boot_animation_sound(self) -> str:
        """Get boot animation sound status"""
        if "boot_animation_sound" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "boot_animation_sound"))

    def set_boot_animation_sound(self, enabled: bool) -> bool:
        """Set boot animation sound status"""
        if "boot_animation_sound" not in self.available_features:
            return False

        return self._write_file(
            os.path.join(self.base_path, "boot_animation_sound"),
            "1" if enabled else "0"
        )

    def get_fan_speed(self) -> Tuple[str, str]:
        """Get CPU and GPU fan speeds"""
        if "fan_speed" not in self.available_features:
            return ("", "")

        file_path = os.path.join(self.base_path, "fan_speed")

        try:
            with open(file_path, 'r') as f:
                speeds = f.read().strip()

                if "," in speeds:
                    cpu, gpu = speeds.split(",", 1)
                    return (cpu.strip(), gpu.strip())
        except Exception as e:
            log.error(f"Error reading fan speed: {e}")

        return ("0", "0")  # Fallback

    def set_fan_speed(self, cpu: int, gpu: int) -> bool:
        """Set CPU and GPU fan speeds"""
        if "fan_speed" not in self.available_features:
            return False

        # Validate values
        if not (0 <= cpu <= 100 and 0 <= gpu <= 100):
            log.error(f"Invalid fan speeds. Values must be between 0 and 100: cpu={cpu}, gpu={gpu}")
            return False

        return self._write_file(
            os.path.join(self.base_path, "fan_speed"),
            f"{cpu},{gpu}"
        )


    def get_lcd_override(self) -> str:
        """Get LCD override status"""
        if "lcd_override" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "lcd_override"))

    def set_lcd_override(self, enabled: bool) -> bool:
        """Set LCD override status"""
        if "lcd_override" not in self.available_features:
            return False

        return self._write_file(
            os.path.join(self.base_path, "lcd_override"),
            "1" if enabled else "0"
        )

    def get_usb_charging(self) -> str:
        """Get USB charging status"""
        if "usb_charging" not in self.available_features:
            return ""

        return self._read_file(os.path.join(self.base_path, "usb_charging"))

    def set_usb_charging(self, level: int) -> bool:
        """Set USB charging level (0, 10, 20, 30)"""
        if "usb_charging" not in self.available_features:
            return False

        # Validate values
        if level not in [0, 10, 20, 30]:
            log.error(f"Invalid USB charging level. Must be 0, 10, 20, or 30: {level}")
            return False

        return self._write_file(
            os.path.join(self.base_path, "usb_charging"),
            str(level)
        )

    def get_per_zone_mode(self) -> str:
        """Get per-zone mode configuration"""
        if "per_zone_mode" not in self.available_features:
            return ""

        return self._read_file("/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/per_zone_mode")

    def set_per_zone_mode(self, zone1: str, zone2: str, zone3: str, zone4: str, brightness: int) -> bool:
        """Set per-zone mode configuration
        
        Args:
            zone1-zone4: RGB hex values (e.g., "4287f5")
            brightness: 0-100
        """
        if "per_zone_mode" not in self.available_features:
            return False

        # Validate hex values
        for i, zone in enumerate([zone1, zone2, zone3, zone4], 1):
            try:
                # Check if valid hex color
                int(zone, 16)
                if len(zone) != 6:
                    log.error(f"Invalid hex color for zone {i}: {zone}. Must be 6 characters.")
                    return False
            except ValueError:
                log.error(f"Invalid hex color for zone {i}: {zone}")
                return False

        # Validate brightness
        if not (0 <= brightness <= 100):
            log.error(f"Invalid brightness. Must be between 0 and 100: {brightness}")
            return False

        value = f"{zone1},{zone2},{zone3},{zone4},{brightness}"
        return self._write_file(
            "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/per_zone_mode",
            value
        )

    def get_four_zone_mode(self) -> str:
        """Get four-zone mode configuration"""
        if "four_zone_mode" not in self.available_features:
            return ""

        return self._read_file("/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/four_zone_mode")

    def set_four_zone_mode(self, mode: int, speed: int, brightness: int,
                           direction: int, red: int, green: int, blue: int) -> bool:
        """Set four-zone mode configuration
        
        Args:
            mode: 0-7 (lighting effect type)
            speed: 0-9 (effect speed)
            brightness: 0-100 (light intensity)
            direction: 1-2 (1=right to left, 2=left to right)
            red, green, blue: 0-255 (RGB color values)
        """
        if "four_zone_mode" not in self.available_features:
            return False

        # Validate values
        if not (0 <= mode <= 7):
            log.error(f"Invalid mode. Must be between 0 and 7: {mode}")
            return False

        if not (0 <= speed <= 9):
            log.error(f"Invalid speed. Must be between 0 and 9: {speed}")
            return False

        if not (0 <= brightness <= 100):
            log.error(f"Invalid brightness. Must be between 0 and 100: {brightness}")
            return False

        if direction not in [1, 2]:
            log.error(f"Invalid direction. Must be 1 or 2: {direction}")
            return False

        if not all(0 <= color <= 255 for color in [red, green, blue]):
            log.error(f"Invalid RGB values. Must be between 0 and 255: {red},{green},{blue}")
            return False

        value = f"{mode},{speed},{brightness},{direction},{red},{green},{blue}"
        return self._write_file(
            "/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/four_zone_mode",
            value
        )

    def get_hyprland_integration(self) -> bool:
        """Get Hyprland integration status"""
        return getattr(self, 'hyprland_integration', False)

    def _ensure_hyprland_config_source(self):
        """Ensure that the acersense.conf is sourced in the main Hyprland config"""
        target_user, _, _ = self._get_hyprland_info()
        if not target_user:
            return

        try:
            # Get User Home
            user_info = pwd.getpwnam(target_user)
            user_home = user_info.pw_dir
            uid = user_info.pw_uid
            gid = user_info.pw_gid
            
            # Paths
            hypr_config_path = os.path.join(user_home, ".config/hypr/hyprland.conf")
            source_line = "source = ~/.config/hypr/acersense.conf\n"
            
            if not os.path.exists(hypr_config_path):
                log.warning(f"Main Hyprland config not found at {hypr_config_path}")
                return

            # Check if source line exists
            with open(hypr_config_path, 'r') as f:
                content = f.read()
                
            if "acersense.conf" not in content:
                log.info("Injecting source line into hyprland.conf")
                
                # Append to file
                with open(hypr_config_path, 'a') as f:
                    if not content.endswith('\n'):
                        f.write('\n')
                    f.write(f"\n# Added by AcerSense for Opacity/Blur control\n{source_line}")
                
                # Ensure ownership is correct
                os.chown(hypr_config_path, uid, gid)
                
        except Exception as e:
            log.error(f"Failed to ensure Hyprland config source: {e}")

    def set_hyprland_integration(self, enabled: bool) -> bool:
        """Set Hyprland integration status"""
        # 1. Strict Boolean Conversion
        if isinstance(enabled, str):
            is_enabled = enabled.lower() in ('true', '1', 'yes', 'on')
        else:
            is_enabled = bool(enabled)

        log.info(f"set_hyprland_integration requested. Input: {enabled} -> Resolved: {is_enabled}")
        self.hyprland_integration = is_enabled

        try:
            # 2. Update Config File
            config = configparser.ConfigParser()
            config.read(CONFIG_PATH)
            
            if 'General' not in config:
                config['General'] = {}
            
            config['General']['HyprlandIntegration'] = str(is_enabled)
            
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
            
            # 3. Execute Logic
            if is_enabled:
                log.info("Status: ENABLED. Activating Hyprland integration...")
                try:
                    self._ensure_hyprland_config_source()
                    self._update_hyprland_visuals(self.last_known_profile)
                except Exception as e:
                    log.error(f"Error during activation: {e}")
            else:
                log.info("Status: DISABLED. Deactivating Hyprland integration...")
                try:
                    self._remove_hyprland_config_source()
                except Exception as e:
                    log.error(f"Error during deactivation: {e}")
            
            return True

        except Exception as e:
            log.error(f"Critical error in set_hyprland_integration: {e}")
            return False

    def get_all_settings(self) -> Dict:
        """Get all AcerSense daemon settings as a dictionary"""
        settings = {
            "laptop_type": self.laptop_type.name,
            "has_four_zone_kb": self.has_four_zone_kb,
            "available_features": list(self.available_features),
            "version": VERSION,
            "driver_version": self.get_driver_version(),
            "modprobe_parameter": self.current_modprobe_param,
            "hyprland_integration": self.hyprland_integration,
            "default_ac_profile": self.default_ac_profile,
            "default_bat_profile": self.default_bat_profile,
            "ac_active_opacity": self.ac_active_opacity,
            "ac_inactive_opacity": self.ac_inactive_opacity,
            "bat_active_opacity": self.bat_active_opacity,
            "bat_inactive_opacity": self.bat_inactive_opacity
        }

        # Only include thermal profile if available
        if "thermal_profile" in self.available_features:
            settings["thermal_profile"] = {
                "current": self.get_thermal_profile(),
                "available": self.get_thermal_profile_choices()
            }
        else:
            # Include an empty entry for compatibility
            settings["thermal_profile"] = {
                "current": "",
                "available": []
            }

        # Add all other features if available
        if "backlight_timeout" in self.available_features:
            settings["backlight_timeout"] = self.get_backlight_timeout()

        if "battery_calibration" in self.available_features:
            settings["battery_calibration"] = self.get_battery_calibration()

        if "battery_limiter" in self.available_features:
            settings["battery_limiter"] = self.get_battery_limiter()

        if "boot_animation_sound" in self.available_features:
            settings["boot_animation_sound"] = self.get_boot_animation_sound()

        if "fan_speed" in self.available_features:
            cpu_fan, gpu_fan = self.get_fan_speed()
            settings["fan_speed"] = {
                "cpu": cpu_fan,
                "gpu": gpu_fan
            }

        if "lcd_override" in self.available_features:
            settings["lcd_override"] = self.get_lcd_override()

        if "usb_charging" in self.available_features:
            settings["usb_charging"] = self.get_usb_charging()

        if "per_zone_mode" in self.available_features:
            settings["per_zone_mode"] = self.get_per_zone_mode()

        if "four_zone_mode" in self.available_features:
            settings["four_zone_mode"] = self.get_four_zone_mode()

        return settings


import asyncio

class DaemonServer:
    """Asyncio Unix Socket server for IPC with the GUI client"""

    def __init__(self, manager: AcerSenseManager):
        self.manager = manager
        self.server = None
        self.clients = set() # Set of (reader, writer) tuples
        self.running = False
        
        # Register ourselves as the event handler for the manager
        # Since manager calls this from sync context (threads), we need a bridge.
        # We will use loop.call_soon_threadsafe if needed, but for now we'll set it up in start()
        self.loop = None

    async def start(self):
        """Start the Async Unix socket server"""
        self.loop = asyncio.get_running_loop()
        
        # Register callback bridge
        # When manager calls this, we schedule the broadcast on the event loop
        def sync_callback(event_type, data):
            if self.loop and self.running:
                self.loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.broadcast_event(event_type, data))
                )
        
        self.manager.register_event_callback(sync_callback)

        # Remove socket if it already exists
        try:
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)
        except OSError as e:
            log.error(f"Failed to remove existing socket: {e}")
            return False

        try:
            self.running = True
            self.server = await asyncio.start_unix_server(
                self.handle_client, path=SOCKET_PATH
            )
            
            # Ensure socket permissions
            os.chmod(SOCKET_PATH, 0o666)
            
            log.info(f"Async Server listening on {SOCKET_PATH}")
            
            async with self.server:
                await self.server.serve_forever()

        except asyncio.CancelledError:
            log.info("Server cancelled.")
        except Exception as e:
            log.error(f"Failed to start server: {e}")
            return False
        finally:
            self.cleanup_socket()

    def stop(self):
        """Stop the server"""
        log.info("Stopping server...")
        self.running = False
        if self.server:
            self.server.close()
        
        # Close all clients
        for _, writer in list(self.clients):
            try:
                writer.close()
            except:
                pass
        self.cleanup_socket()

    def cleanup_socket(self):
        """Clean up the socket file"""
        try:
            if os.path.exists(SOCKET_PATH):
                os.unlink(SOCKET_PATH)
                log.info(f"Removed socket file: {SOCKET_PATH}")
        except Exception as e:
            log.error(f"Failed to remove socket file: {e}")

    async def handle_client(self, reader, writer):
        """Handle async communication with a client"""
        client_peer = writer.get_extra_info('peername')
        # log.debug(f"New connection: {client_peer}")
        self.clients.add((reader, writer))

        try:
            while self.running:
                data = await reader.read(4096)
                if not data:
                    break

                try:
                    message = data.decode('utf-8')
                    # Support multiple JSON objects in one packet (if they stick together)
                    # For now assume one line/packet per command or handle basic structure
                    
                    request = json.loads(message)
                    command = request.get("command", "")
                    params = request.get("params", {})

                    # Process command (Sync logic for now)
                    response = self.process_command(command, params)

                    # Send response
                    response_data = json.dumps(response).encode('utf-8')
                    writer.write(response_data)
                    await writer.drain()

                except json.JSONDecodeError:
                    log.error("Invalid JSON received")
                except Exception as e:
                    log.error(f"Error processing request: {e}")
                    log.error(traceback.format_exc())
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Client connection error: {e}")
        finally:
            self.clients.discard((reader, writer))
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass

    async def broadcast_event(self, event_type: str, data: Dict):
        """Send a JSON event to all connected clients"""
        if not self.clients:
            return

        payload = {
            "type": "event",
            "event": event_type,
            "data": data
        }
        
        try:
            message = json.dumps(payload).encode('utf-8')
            log.debug(f"Broadcasting event: {event_type} to {len(self.clients)} clients")
            
            stale_clients = []
            
            for reader, writer in self.clients:
                try:
                    writer.write(message)
                    await writer.drain()
                except Exception:
                    stale_clients.append((reader, writer))
            
            # Cleanup disconnected clients found during broadcast
            for client in stale_clients:
                self.clients.discard(client)
                
        except Exception as e:
            log.error(f"Broadcast error: {e}")

    def process_command(self, command: str, params: Dict) -> Dict:
        """Process a command from the client"""
        
        # Filter noise from repetitive polling commands
        NOISY_COMMANDS = ["get_thermal_profile", "get_fan_speed", "get_all_settings", "get_supported_features"]
        
        if command in NOISY_COMMANDS:
            log.debug(f"Processing command: {command} with params: {params}")
        else:
            log.info(f"Processing command: {command} with params: {params}")

        try:
            if command == "get_all_settings":
                settings = self.manager.get_all_settings()
                return {
                    "success": True,
                    "data": settings
                }

            elif command == "get_thermal_profile":
                # Check if feature is available
                if "thermal_profile" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Thermal profile is not supported on this device"
                    }

                profile = self.manager.get_thermal_profile()
                choices = self.manager.get_thermal_profile_choices()
                return {
                    "success": True,
                    "data": {
                        "current": profile,
                        "available": choices
                    }
                }

            elif command == "set_thermal_profile":
                # Check if feature is available
                if "thermal_profile" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Thermal profile is not supported on this device"
                    }

                profile = params.get("profile", "")
                success = self.manager.set_thermal_profile(profile)
                return {
                    "success": success,
                    "data": {"profile": profile} if success else None,
                    "error": "Failed to set thermal profile" if not success else None
                }

            elif command == "set_backlight_timeout":
                # Check if feature is available
                if "backlight_timeout" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Backlight timeout is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_backlight_timeout(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set backlight timeout" if not success else None
                }

            elif command == "set_battery_calibration":
                # Check if feature is available
                if "battery_calibration" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Battery calibration is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_battery_calibration(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set battery calibration" if not success else None
                }

            elif command == "set_battery_limiter":
                # Check if feature is available
                if "battery_limiter" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Battery limiter is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_battery_limiter(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set battery limiter" if not success else None
                }

            elif command == "set_boot_animation_sound":
                # Check if feature is available
                if "boot_animation_sound" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Boot animation sound is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_boot_animation_sound(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set boot animation sound" if not success else None
                }

            elif command == "set_fan_speed":
                # Check if feature is available
                if "fan_speed" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Fan speed control is not supported on this device"
                    }

                cpu = params.get("cpu", 0)
                gpu = params.get("gpu", 0)
                success = self.manager.set_fan_speed(cpu, gpu)
                return {
                    "success": success,
                    "data": {"cpu": cpu, "gpu": gpu} if success else None,
                    "error": "Failed to set fan speed" if not success else None
                }

            elif command == "set_lcd_override":
                # Check if feature is available
                if "lcd_override" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "LCD override is not supported on this device"
                    }

                enabled = params.get("enabled", False)
                success = self.manager.set_lcd_override(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set LCD override" if not success else None
                }

            elif command == "set_usb_charging":
                # Check if feature is available
                if "usb_charging" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "USB charging control is not supported on this device"
                    }

                level = params.get("level", 0)
                success = self.manager.set_usb_charging(level)
                return {
                    "success": success,
                    "data": {"level": level} if success else None,
                    "error": "Failed to set USB charging" if not success else None
                }

            elif command == "set_per_zone_mode":
                # Check if feature is available
                if "per_zone_mode" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Per-zone keyboard mode is not supported on this device"
                    }

                zone1 = params.get("zone1", "000000")
                zone2 = params.get("zone2", "000000")
                zone3 = params.get("zone3", "000000")
                zone4 = params.get("zone4", "000000")
                brightness = params.get("brightness", 100)
                success = self.manager.set_per_zone_mode(zone1, zone2, zone3, zone4, brightness)
                return {
                    "success": success,
                    "data": {
                        "zone1": zone1,
                        "zone2": zone2,
                        "zone3": zone3,
                        "zone4": zone4,
                        "brightness": brightness
                    } if success else None,
                    "error": "Failed to set per-zone mode" if not success else None
                }

            elif command == "set_four_zone_mode":
                # Check if feature is available
                if "four_zone_mode" not in self.manager.available_features:
                    return {
                        "success": False,
                        "error": "Four-zone keyboard mode is not supported on this device"
                    }

                mode = params.get("mode", 0)
                speed = params.get("speed", 0)
                brightness = params.get("brightness", 100)
                direction = params.get("direction", 1)
                red = params.get("red", 0)
                green = params.get("green", 0)
                blue = params.get("blue", 0)
                success = self.manager.set_four_zone_mode(mode, speed, brightness, direction, red, green, blue)
                return {
                    "success": success,
                    "data": {
                        "mode": mode,
                        "speed": speed,
                        "brightness": brightness,
                        "direction": direction,
                        "red": red,
                        "green": green,
                        "blue": blue
                    } if success else None,
                    "error": "Failed to set four-zone mode" if not success else None
                }

            elif command == "set_hyprland_integration":
                enabled = params.get("enabled", False)
                success = self.manager.set_hyprland_integration(enabled)
                return {
                    "success": success,
                    "data": {"enabled": enabled} if success else None,
                    "error": "Failed to set Hyprland integration" if not success else None
                }

            elif command == "set_default_profile_preference":
                source = params.get("source", "")
                profile = params.get("profile", "")
                success = self.manager.set_default_profile_preference(source, profile)
                return {
                    "success": success,
                    "data": {"source": source, "profile": profile} if success else None,
                    "error": "Failed to set default profile preference" if not success else None
                }

            elif command == "set_hyprland_opacity_settings":
                ac_active = float(params.get("ac_active", 0.97))
                ac_inactive = float(params.get("ac_inactive", 0.95))
                bat_active = float(params.get("bat_active", 1.0))
                bat_inactive = float(params.get("bat_inactive", 1.0))
                success = self.manager.set_hyprland_opacity_settings(ac_active, ac_inactive, bat_active, bat_inactive)
                return {
                    "success": success,
                    "data": None,
                    "error": "Failed to set opacity settings" if not success else None
                }

            elif command == "get_supported_features":
                return {
                    "success": True,
                    "data": {
                        "available_features": list(self.manager.available_features),
                        "laptop_type": self.manager.laptop_type.name,
                        "has_four_zone_kb": self.manager.has_four_zone_kb
                    }
                }

            elif command == "get_version":
                return {
                    "success": True,
                    "data": {
                        "version": VERSION
                    }
                }
            
            # Force Models and Features
            elif command == "force_nitro_model":
                # Force Nitro model into driver
                success = self.manager._force_model_nitro()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully forced Nitro model into driver"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to force Nitro model into driver"
                    }
                
            elif command == "force_predator_model":
                # Force Predator model into driver
                success = self.manager._force_model_predator()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully forced Predator model into driver"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to force Predator model into driver (Model may not support it)"
                    }

            elif command == "force_enable_all":
                # Force Enable All Features into driver
                success = self.manager._force_enable_all()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully forced all features into driver"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to force all features into driver (Model may not support it)"
                    }
                
            elif command == "get_modprobe_parameter":
                print (self.manager.get_modprobe_parameter())
                return {
                    "success": True,
                    "data": {
                        "parameter": self.manager.get_modprobe_parameter()
                    }
                }

            # Force Model and Parameters Permanantly
            elif command == "set_modprobe_parameter_nitro":
                success = self.manager.set_modprobe_parameter("nitro_v4")
                return {
                    "success": success,
                    "data": {"parameter": param} if success else None,
                    "error": "Failed to set modprobe parameter" if not success else None
                }
            
            elif command == "set_modprobe_parameter_predator":
                param = params.get("parameter", "")
                success = self.manager.set_modprobe_parameter("predator_v4")
                return {
                    "success": success,
                    "data": {"parameter": param} if success else None,
                    "error": "Failed to set modprobe parameter" if not success else None
                }
            
            elif command == "set_modprobe_parameter_enable_all":
                param = params.get("parameter", "")
                success = self.manager.set_modprobe_parameter("enable_all")
                return {
                    "success": success,
                    "data": {"parameter": param} if success else None,
                    "error": "Failed to set modprobe parameter" if not success else None
                }

            elif command == "remove_modprobe_parameter":
                success = self.manager._remove_modprobe_parameter()
                return {
                    "success": success,
                    "message": "Successfully removed modprobe parameter" if success else None,
                    "error": "Failed to remove modprobe parameter" if not success else None
                }
            
            elif command == "restart_daemon":
                # Force Nitro model into driver
                success = self.manager._restart_daemon()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully restarted AcerSense daemon"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to Restart AcerSense daemon (Check logs for details)"
                    }           

            elif command == "restart_drivers_and_daemon":
                # Restart linuwu-sense driver and AcerSense daemon service
                success = self.manager._restart_drivers_and_daemon()
                if success:
                    return {
                        "success": True,
                        "message": "Successfully restarted drivers and AcerSense daemon"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Failed to restart drivers and AcerSense daemon"
                    }
            
            elif command == "cycle_profile":
                # Trust our internal state first to prevent race conditions
                current_profile = self.manager.last_known_profile
                
                # Fallback to reading real state if internal state is missing
                if not current_profile:
                    current_profile = self.manager.get_thermal_profile()
                
                if not current_profile:
                    return {"success": False, "error": "Could not read current thermal profile."}

                is_ac_online_path = next((p for p in ["/sys/class/power_supply/AC/online", "/sys/class/power_supply/ACAD/online", "/sys/class/power_supply/ADP1/online", "/sys/class/power_supply/AC0/online"] if os.path.exists(p)), None)
                is_ac = self.manager._read_file(is_ac_online_path) == "1" if is_ac_online_path else False
                
                all_profiles = self.manager.get_thermal_profile_choices()
                profiles_ac = [p for p in all_profiles if p in ["quiet", "balanced", "balanced-performance"]]
                profiles_battery = [p for p in all_profiles if p in ["low-power", "balanced"]]
                profiles = profiles_ac if is_ac else profiles_battery
                
                if not profiles:
                    return {"success": False, "error": "No profiles available for cycling."}

                # Find current index based on the real profile
                try:
                    current_idx = profiles.index(current_profile)
                except ValueError:
                    # If current profile is not in the list (e.g. 'performance'), start from the beginning
                    current_idx = -1
                
                next_idx = (current_idx + 1) % len(profiles)
                next_profile = profiles[next_idx]

                # TLP and custom logic removed - Manager handles optimizations now
                self.manager.set_thermal_profile(next_profile)
                
                return {"success": True, "data": {"new_profile": next_profile}}

            elif command == "activate_nos":
                if not self.manager.nos_active:
                    self.manager.nos_active = True
                    self.manager.previous_profile_for_nos = self.manager.get_thermal_profile()
                    if "fan_speed" in self.manager.available_features:
                        self.manager.set_fan_speed(100, 100)
                    self.manager.set_thermal_profile("balanced-performance")
                    return {"success": True, "message": "NOS Mode Activated"}
                return {"success": False, "message": "NOS already active"}

            elif command == "deactivate_nos":
                if self.manager.nos_active:
                    self.manager.nos_active = False
                    if hasattr(self.manager, 'previous_profile_for_nos') and self.manager.previous_profile_for_nos:
                        self.manager.set_thermal_profile(self.manager.previous_profile_for_nos)
                    if "fan_speed" in self.manager.available_features:
                        self.manager.set_fan_speed(0, 0) # Assuming 0 is auto, might need adjustment
                    return {"success": True, "message": "NOS Mode Deactivated"}
                return {"success": False, "message": "NOS not active"}

            else:
                return {
                    "success": False,
                    "error": f"Unknown command: {command}"
                }

        except Exception as e:
            log.error(f"Error processing command {command}: {e}")
            log.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }


class AcerSenseDaemon:
    """Main daemon class that manages the lifecycle"""

    def __init__(self):
        self.running = False
        self.manager = None
        self.server = None
        self.config = None

    def load_config(self):
        """Load configuration from file"""
        config = configparser.ConfigParser()

        # Create default config if it doesn't exist
        if not os.path.exists(CONFIG_PATH):
            log.info(f"Creating default config at {CONFIG_PATH}")
            config['General'] = {
                'LogLevel': 'INFO',
                'AutoDetectFeatures': 'True'
            }

            # Create config directory if it doesn't exist
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

            # Write default config
            with open(CONFIG_PATH, 'w') as f:
                config.write(f)
        else:
            # Load existing config
            config.read(CONFIG_PATH)

        self.config = config
        
        # Load Hyprland Integration Setting
        # Note: This attribute is stored on the daemon instance, but we need to pass it to the manager later or access it globally.
        # For simplicity, we will set a class variable on AcerSenseManager if possible, or handle it during setup.
        self.hyprland_integration = False
        if 'General' in config and 'HyprlandIntegration' in config['General']:
             self.hyprland_integration = config.getboolean('General', 'HyprlandIntegration', fallback=False)
             log.info(f"Hyprland Integration: {'Enabled' if self.hyprland_integration else 'Disabled'}")

        # Set log level from config
        if 'General' in config and 'LogLevel' in config['General']:
            log_level = config['General']['LogLevel'].upper()
            if log_level in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
                #log.setLevel(getattr(logging, log_level))
                log.setLevel(logging.DEBUG)
                
                log.info(f"Log level set to {log_level}")

        return config

    def setup(self):
        """Set up the daemon"""
        # Load configuration first
        self.load_config()

        try:
            # Initialize daemon manager
            self.manager = AcerSenseManager()
            # Pass config setting to manager
            self.manager.hyprland_integration = getattr(self, 'hyprland_integration', False)

            # Initialize power monitor
            self.power_monitor = PowerSourceDetector(self.manager)
            self.power_monitor.start_monitoring()

            # Log detected features
            features_str = ", ".join(sorted(self.manager.available_features))
            log.info(f"Detected features: {features_str}")

            return True
        except Exception as e:
            log.error(f"Failed to set up daemon: {e}")
            log.error(traceback.format_exc())
            return False
    


    async def run(self):
        """Run the daemon"""
        # Write PID file
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        # Set up and run the server
        try:
            self.running = True
            self.server = DaemonServer(self.manager)
            
            # Start power monitor
            if self.power_monitor:
                self.power_monitor.start_monitoring()
            
            # Start Async Server
            await self.server.start()
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Error running daemon: {e}")
            log.error(traceback.format_exc())
        finally:
            self.cleanup()

    async def shutdown(self):
        """Handle shutdown signal"""
        log.info("Received stop signal, shutting down...")
        self.running = False
        if self.server:
            self.server.stop()
        # Cancel all running tasks
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def cleanup(self):
        """Clean up resources"""
        log.info("Cleaning up resources...")
    
        # Stop server and clean up socket
        if self.server:
            self.server.stop()
    
        if self.power_monitor:
            self.power_monitor.stop_monitoring()
    
        # Remove PID file
        try:
            if os.path.exists(PID_FILE):
                os.unlink(PID_FILE)
        except:
            pass
    
        log.info("Daemon stopped")

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="AcerSense Daemon")
    parser.add_argument('-v', '--verbose', action='store_true', help="Enable verbose logging")
    parser.add_argument('--version', action='version', version=f"AcerSense-Daemon v{VERSION}")
    parser.add_argument('--debug', action='store_true', help="Enable debug mode")
    parser.add_argument('--config', type=str, help=f"Path to config file (default: {CONFIG_PATH})")
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_args()

    # Set log level based on verbosity
    if args.verbose:
        log.setLevel(logging.DEBUG)
        log.debug("Debug logging enabled")

    # Use custom config path if provided
    global CONFIG_PATH
    if args.config:
        CONFIG_PATH = args.config

    daemon = AcerSenseDaemon()
    if daemon.setup():
        try:
            log.info(f"Driver Version: {daemon.manager.get_driver_version()}")
            asyncio.run(daemon.run())
        except KeyboardInterrupt:
            pass # Handled by signal handler usually
        except Exception as e:
            log.error(f"Fatal error: {e}")
            sys.exit(1)
    else:
        log.error("Failed to set up daemon, exiting...")
        sys.exit(1)

if __name__ == "__main__":
    main()
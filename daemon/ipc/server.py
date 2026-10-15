"""Asynchronous Unix Domain Socket Server with Event Broadcasting and Request-Response Handling."""

import os
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set
from daemon.core.hardware_manager import HardwareManager
from daemon.core.power_optimizer import PowerOptimizer
from daemon.core.boot_boost import BootBoostManager
from daemon.core.laptop_type import (
    set_modprobe_parameter,
    remove_modprobe_parameter,
    detect_current_modprobe_param
)
from daemon.ipc.protocol import (
    decode_message,
    make_response,
    make_event
)

log = logging.getLogger("acersense.server")

DEFAULT_SOCKET_PATH = "/var/run/AcerSense.sock"
COMPAT_SOCKET_PATH = "/var/run/DAMX.sock"


class AcerSenseServer:
    """Asyncio Unix Domain Socket Server handling client commands and event broadcasting."""

    def __init__(
        self,
        hardware: HardwareManager,
        power: PowerOptimizer,
        boot_boost: BootBoostManager,
        socket_path: str = DEFAULT_SOCKET_PATH,
        compat_symlink: Optional[str] = COMPAT_SOCKET_PATH,
    ):
        self.hardware = hardware
        self.power = power
        self.boot_boost = boot_boost
        self.socket_path = socket_path
        self.compat_symlink = compat_symlink

        self.server: Optional[asyncio.AbstractServer] = None
        self._clients: Set[asyncio.StreamWriter] = set()
        self.is_running = False

        # Configuration store for default profile preferences
        self.ac_default_profile = "performance"
        self.bat_default_profile = "quiet"
        self.disable_logging = False

    async def start(self) -> None:
        """Bind socket and start accepting connections."""
        if self.is_running:
            return

        # Clean existing socket
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except Exception as e:
                log.warning(f"Could not unlink existing socket {self.socket_path}: {e}")

        # Ensure directory exists
        os.makedirs(os.path.dirname(self.socket_path), exist_ok=True)

        self.server = await asyncio.start_unix_server(
            self._handle_client,
            path=self.socket_path
        )
        self.is_running = True

        # Set permissive permissions so regular users can control hardware via GUI
        try:
            os.chmod(self.socket_path, 0o666)
        except Exception as e:
            log.warning(f"Failed to chmod socket: {e}")

        # Create compatibility symlink (e.g. /var/run/DAMX.sock -> /var/run/AcerSense.sock)
        if self.compat_symlink:
            try:
                if os.path.islink(self.compat_symlink) or os.path.exists(self.compat_symlink):
                    os.unlink(self.compat_symlink)
                os.symlink(self.socket_path, self.compat_symlink)
            except Exception as e:
                log.debug(f"Could not create compat symlink {self.compat_symlink}: {e}")

        log.info(f"IPC Server running on {self.socket_path}")

    async def stop(self) -> None:
        """Stop server and disconnect clients."""
        self.is_running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

        for writer in list(self._clients):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self._clients.clear()

        for path in [self.socket_path, self.compat_symlink]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except Exception:
                    pass
        log.info("IPC Server stopped")

    def broadcast_event(self, event_name: str, data: Any) -> None:
        """Broadcast an asynchronous event to all connected clients."""
        if not self._clients:
            return

        msg_bytes = make_event(event_name, data)
        for writer in list(self._clients):
            try:
                writer.write(msg_bytes)
            except Exception as e:
                log.debug(f"Failed to write event to client: {e}")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle incoming connection and read newline-delimited JSON commands."""
        self._clients.add(writer)
        try:
            while self.is_running and not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break

                line_str = line.decode("utf-8", errors="ignore")
                ok, req, err = decode_message(line_str)
                if not ok or not req:
                    writer.write(make_response(False, error=err or "Invalid request"))
                    await writer.drain()
                    continue

                cmd = req.get("command", "")
                params = req.get("params", {}) or {}
                resp_bytes = await self._dispatch_command(cmd, params)
                writer.write(resp_bytes)
                await writer.drain()
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            log.error(f"Error handling client connection: {e}")
        finally:
            self._clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch_command(self, cmd: str, params: Dict[str, Any]) -> bytes:
        """Dispatch a single JSON-RPC command."""
        try:
            if cmd == "ping":
                return make_response(True, "pong")

            if cmd == "get_version":
                return make_response(True, {
                    "version": "1.0.0",
                    "driver_version": "25.701",
                    "laptop_type": self.hardware.laptop_type.name,
                })

            if cmd == "get_supported_features":
                return make_response(True, {
                    "available_features": sorted(list(self.hardware.available_features)),
                    "has_four_zone_kb": self.hardware.has_four_zone_kb,
                    "laptop_type": self.hardware.laptop_type.name,
                })

            if cmd == "get_all_settings":
                c_fan, g_fan = self.hardware.get_fan_speed()
                return make_response(True, {
                    "version": "1.0.0",
                    "driver_version": "25.701",
                    "laptop_type": self.hardware.laptop_type.name,
                    "available_features": sorted(list(self.hardware.available_features)),
                    "has_four_zone_kb": self.hardware.has_four_zone_kb,
                    "thermal_profile": {"current": self.hardware.get_thermal_profile()},
                    "fan_speed": {"cpu": c_fan, "gpu": g_fan},
                    "battery_limiter": self.hardware.get_battery_limiter(),
                    "battery_calibration": self.hardware.get_battery_calibration(),
                    "boot_animation_sound": self.hardware.get_boot_animation_sound(),
                    "lcd_override": self.hardware.get_lcd_override(),
                    "usb_charging": self.hardware.get_usb_charging(),
                    "modprobe_parameter": detect_current_modprobe_param(),
                    "is_nos_active": self.hardware.is_nos_active,
                    "boot_boost_enabled": self.boot_boost.enabled,
                    "boot_boost_delay": self.boot_boost.delay_seconds,
                    "ac_default_profile": self.ac_default_profile,
                    "bat_default_profile": self.bat_default_profile,
                })

            # Fan control
            if cmd == "set_fan_speed":
                cpu = params.get("cpu", 0)
                gpu = params.get("gpu", 0)
                success = self.hardware.set_fan_speed(cpu, gpu)
                if success:
                    c_spd, g_spd = self.hardware.get_fan_speed()
                    self.broadcast_event("fan_speed_changed", {"cpu": c_spd, "gpu": g_spd})
                return make_response(success, {"cpu": cpu, "gpu": gpu})

            if cmd == "get_fan_rpms":
                cpu_rpm, gpu_rpm = self.hardware.get_fan_rpms()
                return make_response(True, {"cpu": str(cpu_rpm), "gpu": str(gpu_rpm)})

            # Thermal profiles
            if cmd == "get_thermal_profile":
                return make_response(True, {"profile": self.hardware.get_thermal_profile()})

            if cmd == "set_thermal_profile":
                prof = params.get("profile", "")
                success = self.hardware.set_thermal_profile(prof)
                if success:
                    self.power.apply_profile(prof)
                    self.broadcast_event("thermal_profile_changed", {"profile": prof})
                return make_response(success, {"profile": prof})

            if cmd == "cycle_profile":
                new_prof = self.hardware.cycle_profile()
                if new_prof:
                    self.power.apply_profile(new_prof)
                    self.broadcast_event("thermal_profile_changed", {"profile": new_prof})
                    return make_response(True, {"profile": new_prof})
                return make_response(False, error="Failed to cycle profile")

            # NOS mode
            if cmd == "activate_nos":
                success = self.hardware.activate_nos()
                if success:
                    self.broadcast_event("nos_state_changed", {"active": True})
                    self.broadcast_event("fan_speed_changed", {"cpu": "100", "gpu": "100"})
                    self.broadcast_event("thermal_profile_changed", {"profile": self.hardware.get_thermal_profile()})
                return make_response(success, {"active": True})

            if cmd == "deactivate_nos":
                success = self.hardware.deactivate_nos()
                if success:
                    c_spd, g_spd = self.hardware.get_fan_speed()
                    self.broadcast_event("nos_state_changed", {"active": False})
                    self.broadcast_event("fan_speed_changed", {"cpu": c_spd, "gpu": g_spd})
                    self.broadcast_event("thermal_profile_changed", {"profile": self.hardware.get_thermal_profile()})
                return make_response(success, {"active": False})

            # Battery & System
            if cmd == "set_battery_limiter":
                enabled = bool(params.get("enabled", False))
                return make_response(self.hardware.set_battery_limiter(enabled), {"enabled": enabled})

            if cmd == "set_battery_calibration":
                enabled = bool(params.get("enabled", False))
                return make_response(self.hardware.set_battery_calibration(enabled), {"enabled": enabled})

            if cmd == "set_boot_animation_sound":
                enabled = bool(params.get("enabled", False))
                return make_response(self.hardware.set_boot_animation_sound(enabled), {"enabled": enabled})

            if cmd == "set_lcd_override":
                enabled = bool(params.get("enabled", False))
                return make_response(self.hardware.set_lcd_override(enabled), {"enabled": enabled})

            if cmd == "set_usb_charging":
                level = int(params.get("level", 0))
                return make_response(self.hardware.set_usb_charging(level), {"level": level})

            # RGB Lighting
            if cmd == "set_per_zone_mode":
                z1 = params.get("zone1", "000000")
                z2 = params.get("zone2", "000000")
                z3 = params.get("zone3", "000000")
                z4 = params.get("zone4", "000000")
                b = int(params.get("brightness", 100))
                return make_response(self.hardware.set_per_zone_mode(z1, z2, z3, z4, b))

            if cmd == "set_four_zone_mode":
                mode = int(params.get("mode", 0))
                speed = int(params.get("speed", 5))
                brightness = int(params.get("brightness", 100))
                direction = int(params.get("direction", 1))
                r = int(params.get("red", 255))
                g = int(params.get("green", 255))
                b = int(params.get("blue", 255))
                return make_response(self.hardware.set_four_zone_mode(mode, speed, brightness, direction, r, g, b))

            # Boot Boost
            if cmd == "set_boot_boost":
                enabled = bool(params.get("enabled", False))
                self.boot_boost.enabled = enabled
                return make_response(True, {"enabled": enabled})

            if cmd == "set_boot_boost_delay":
                delay = int(params.get("delay", 5))
                self.boot_boost.delay_seconds = delay
                return make_response(True, {"delay": delay})

            if cmd == "end_boot_boost":
                self.boot_boost.cancel()
                return make_response(True)

            # Preferences
            if cmd == "set_default_profile_preference":
                source = params.get("source", "").lower()
                profile = params.get("profile", "")
                if source == "ac":
                    self.ac_default_profile = profile
                elif source in ["bat", "battery"]:
                    self.bat_default_profile = profile
                return make_response(True, {"source": source, "profile": profile})

            if cmd == "set_logging_state":
                disabled = bool(params.get("disabled", False))
                self.disable_logging = disabled
                return make_response(True, {"disabled": disabled})

            # Modprobe parameters
            if cmd == "set_modprobe_parameter_nitro":
                return make_response(set_modprobe_parameter("force_model=nitro"))

            if cmd == "set_modprobe_parameter_predator":
                return make_response(set_modprobe_parameter("force_model=predator"))

            if cmd == "set_modprobe_parameter_enable_all":
                return make_response(set_modprobe_parameter("enable_all=1"))

            if cmd == "remove_modprobe_parameter":
                return make_response(remove_modprobe_parameter())

            return make_response(False, error=f"Unknown command: '{cmd}'")
        except Exception as e:
            log.error(f"Error executing command '{cmd}': {e}")
            return make_response(False, error=str(e))

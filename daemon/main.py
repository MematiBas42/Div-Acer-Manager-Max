"""AcerSense Daemon main entrypoint."""

import os
import sys
import signal
import asyncio
import logging
from typing import Optional

from daemon.core.laptop_type import reset_restart_attempts
from daemon.core.hardware_manager import HardwareManager
from daemon.core.power_optimizer import PowerOptimizer
from daemon.core.boot_boost import BootBoostManager
from daemon.core.netlink_monitor import NetlinkPowerMonitor, read_ac_online
from daemon.services.hyprland_bridge import HyprlandBridge
from daemon.ipc.server import AcerSenseServer, DEFAULT_SOCKET_PATH, COMPAT_SOCKET_PATH

LOG_PATH = "/var/log/AcerSenseDaemon.log"


def setup_logging(silent: bool = False) -> None:
    level = logging.WARNING if silent else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)

    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter(fmt))
        logging.getLogger().addHandler(fh)
    except Exception:
        pass


class AcerSenseDaemon:
    """Orchestrates hardware managers, power monitoring, and the IPC server."""

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH):
        self.hardware = HardwareManager()
        self.power = PowerOptimizer()
        self.boot_boost = BootBoostManager(on_finish_callback=self._on_boot_boost_finish)
        self.hyprland = HyprlandBridge()
        self.server = AcerSenseServer(
            hardware=self.hardware,
            power=self.power,
            boot_boost=self.boot_boost,
            socket_path=socket_path,
            compat_symlink=COMPAT_SOCKET_PATH if socket_path == DEFAULT_SOCKET_PATH else None,
            hyprland=self.hyprland,
        )
        self.netlink = NetlinkPowerMonitor(callback=self._on_power_state_changed)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = asyncio.Event()

    def _on_power_state_changed(self, is_ac: bool) -> None:
        """Handle kernel uevent when AC charger is plugged or unplugged."""
        logging.info(f"Power state updated: AC={is_ac}")
        target_profile = self.server.ac_default_profile if is_ac else self.server.bat_default_profile

        if not self.hardware.is_nos_active:
            self.hardware.set_thermal_profile(target_profile)
            self.power.apply_profile(target_profile)
            if self.hyprland.enabled:
                self.hyprland.sync_visuals(target_profile, is_ac)

        self.server.broadcast_event("power_state_changed", {"plugged_in": is_ac})
        self.server.broadcast_event("thermal_profile_changed", {"profile": self.hardware.get_thermal_profile()})

    def _on_boot_boost_finish(self) -> None:
        """Apply default profile once boot boost concludes."""
        is_ac = read_ac_online()
        default_profile = self.server.ac_default_profile if is_ac else self.server.bat_default_profile
        self.hardware.set_thermal_profile(default_profile)
        self.hardware.set_fan_speed(0, 0)
        self.power.apply_profile(default_profile)
        self.server.broadcast_event("thermal_profile_changed", {"profile": default_profile})
        self.server.broadcast_event("fan_speed_changed", {"cpu": "0", "gpu": "0"})

    def _trigger_boot_boost_fans(self) -> None:
        self.hardware.set_thermal_profile("performance")
        self.hardware.set_fan_speed(100, 100)

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()

        # Signal handlers for clean termination
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self.loop.add_signal_handler(sig, self._request_shutdown)
            except NotImplementedError:
                pass

        await self.server.start()
        self.netlink.start(self.loop)

        # Successful start resets driver restart counter
        reset_restart_attempts()

        # Initial power alignment
        is_ac = read_ac_online()
        initial_profile = self.server.ac_default_profile if is_ac else self.server.bat_default_profile
        self.hardware.set_thermal_profile(initial_profile)
        self.power.apply_profile(initial_profile)
        if self.hyprland.enabled:
            self.hyprland.sync_visuals(initial_profile, is_ac)

        # Boot boost trigger
        if self.boot_boost.enabled:
            asyncio.create_task(self.boot_boost.start_boost(self._trigger_boot_boost_fans))

        logging.info("AcerSense Daemon running successfully")
        await self._stop_event.wait()

        # Teardown
        self.netlink.stop(self.loop)
        await self.server.stop()
        logging.info("AcerSense Daemon shut down cleanly")

    def _request_shutdown(self) -> None:
        logging.info("Shutdown requested")
        self._stop_event.set()


def main() -> None:
    setup_logging()
    daemon = AcerSenseDaemon()
    try:
        asyncio.run(daemon.run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()

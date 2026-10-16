"""Asynchronous Kernel Netlink UEvent Power Source Monitor."""

import os
import glob
import socket
import asyncio
import logging
from typing import Callable, Optional

log = logging.getLogger("acersense.netlink")


def read_ac_online(sysfs_root: str = "/sys") -> bool:
    """Check if laptop is connected to AC power."""
    candidates = glob.glob(os.path.join(sysfs_root, "class/power_supply/AC*/online"))
    if not candidates:
        candidates = glob.glob(os.path.join(sysfs_root, "class/power_supply/ACAD/online"))
        if not candidates:
            candidates = glob.glob(os.path.join(sysfs_root, "class/power_supply/ADP*/online"))

    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                if f.read().strip() == "1":
                    return True
        except Exception:
            continue

    # If no AC adapter found, check if a battery exists.
    # If no battery exists (e.g., VM, desktop or test environment), default to AC (True).
    bat_candidates = glob.glob(os.path.join(sysfs_root, "class/power_supply/BAT*"))
    if not bat_candidates:
        return True

    return False


class NetlinkPowerMonitor:
    """Listens for kernel power_supply uevents via Netlink socket with 0% CPU polling."""

    def __init__(self, callback: Callable[[bool], None], sysfs_root: str = "/sys"):
        self.callback = callback
        self.sysfs_root = sysfs_root
        self.is_running = False
        self._sock: Optional[socket.socket] = None
        self._last_ac_state: Optional[bool] = None

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Start listening for netlink events."""
        if self.is_running:
            return

        self._last_ac_state = read_ac_online(self.sysfs_root)
        try:
            # 15 = NETLINK_KOBJECT_UEVENT
            self._sock = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, 15)
            self._sock.bind((os.getpid(), 1))
            self._sock.setblocking(False)
            self.is_running = True

            current_loop = loop or asyncio.get_event_loop()
            current_loop.add_reader(self._sock.fileno(), self._on_netlink_read)
            log.info("Netlink power source monitor started")
        except Exception as e:
            log.warning(f"Failed to bind Netlink socket ({e}). Fallback to periodic check if needed.")
            self.is_running = False

    def _on_netlink_read(self) -> None:
        if not self._sock:
            return
        try:
            data = self._sock.recv(4096)
            msg = data.decode("utf-8", errors="ignore")
            if "power_supply" in msg or "SUBSYSTEM=power_supply" in msg:
                current_ac = read_ac_online(self.sysfs_root)
                if current_ac != self._last_ac_state:
                    self._last_ac_state = current_ac
                    log.info(f"Power supply changed: AC connected = {current_ac}")
                    self.callback(current_ac)
        except Exception as e:
            log.debug(f"Netlink read error: {e}")

    def stop(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """Stop listening and clean up netlink socket."""
        if not self.is_running:
            return
        self.is_running = False
        if self._sock:
            try:
                current_loop = loop or asyncio.get_event_loop()
                current_loop.remove_reader(self._sock.fileno())
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        log.info("Netlink power source monitor stopped")

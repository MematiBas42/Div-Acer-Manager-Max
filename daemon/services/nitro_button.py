"""Deterministic Nitro/Predator hardware button handler.
Zero /tmp files, zero shell forks, single event-loop state machine.
"""

import os
import sys

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_DAEMON_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))
if _DAEMON_ROOT not in sys.path:
    sys.path.insert(0, _DAEMON_ROOT)

import glob
import time
import struct
import asyncio
import logging
from typing import Callable, Optional, Tuple

from daemon.ipc.protocol import encode_message, decode_message

log = logging.getLogger("acersense.button")

CONFIG_PATH = "/etc/acersense/nitro_button.conf"
LEGACY_CONFIG_PATH = "/etc/damx/nitro_key.conf"

# Linux input_event struct format:
# 64-bit systems: timeval (tv_sec: 8B, tv_usec: 8B), type: 2B, code: 2B, value: 4B -> 24 bytes
EVENT_FORMAT = "qqHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

EV_KEY = 1
KEY_UP = 0
KEY_DOWN = 1
KEY_HOLD = 2

LONG_PRESS_THRESHOLD_SEC = 0.6


class NitroButtonStateMachine:
    """Pure deterministic state machine for short-press and long-press differentiation."""

    def __init__(
        self,
        on_short_press: Callable[[], None],
        on_long_press: Callable[[], None],
        threshold_sec: float = LONG_PRESS_THRESHOLD_SEC,
    ):
        self.on_short_press = on_short_press
        self.on_long_press = on_long_press
        self.threshold_sec = threshold_sec

        self._press_time: Optional[float] = None
        self._timer_task: Optional[asyncio.Task] = None
        self._long_press_fired: bool = False

    def handle_event(self, value: int, now: Optional[float] = None) -> None:
        """Handle key event state (0=UP, 1=DOWN, 2=HOLD)."""
        current_time = now if now is not None else time.monotonic()

        if value == KEY_DOWN:
            self._press_time = current_time
            self._long_press_fired = False

            # Cancel any lingering timer
            if self._timer_task and not self._timer_task.done():
                self._timer_task.cancel()

            # Schedule long press check
            try:
                loop = asyncio.get_running_loop()
                self._timer_task = loop.create_task(self._wait_for_long_press())
            except RuntimeError:
                pass

        elif value == KEY_HOLD:
            # Ignore auto-repeat key events
            pass

        elif value == KEY_UP:
            if self._timer_task and not self._timer_task.done():
                self._timer_task.cancel()

            if not self._long_press_fired and self._press_time is not None:
                duration = current_time - self._press_time
                if duration < self.threshold_sec:
                    self.on_short_press()

            self._press_time = None
            self._long_press_fired = False

    async def _wait_for_long_press(self) -> None:
        try:
            await asyncio.sleep(self.threshold_sec)
            self._long_press_fired = True
            self.on_long_press()
        except asyncio.CancelledError:
            pass


class NitroButtonService:
    """Service listening to keyboard evdev and commanding AcerSense daemon."""

    def __init__(self, socket_path: str = "/var/run/AcerSense.sock"):
        self.socket_path = socket_path
        self.device_path: Optional[str] = None
        self.target_keycode: int = 425  # Standard Nitro keycode
        self.is_running: bool = False
        self._state_machine = NitroButtonStateMachine(
            on_short_press=self._handle_short_press,
            on_long_press=self._handle_long_press
        )

    def load_config(self) -> None:
        for conf in [CONFIG_PATH, LEGACY_CONFIG_PATH]:
            if os.path.exists(conf):
                try:
                    with open(conf, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("DEVICE="):
                                self.device_path = line.split("=", 1)[1].strip().strip('"\'')
                            elif line.startswith("KEY="):
                                k_str = line.split("=", 1)[1].strip()
                                if k_str.isdigit():
                                    self.target_keycode = int(k_str)
                except Exception as e:
                    log.warning(f"Error reading button config {conf}: {e}")

    def find_keyboard_device(self) -> Optional[str]:
        if self.device_path and os.path.exists(self.device_path):
            return self.device_path

        # Look for AT Translated Set 2 keyboard
        by_path = glob.glob("/dev/input/by-path/*-event-kbd")
        if by_path:
            return by_path[0]

        # Fallback to scanning /dev/input/event*
        events = sorted(glob.glob("/dev/input/event*"))
        return events[0] if events else None

    def _handle_short_press(self) -> None:
        log.info("Short press detected -> Cycling Thermal Profile")
        asyncio.create_task(self._send_command("cycle_profile"))

    def _handle_long_press(self) -> None:
        log.info("Long press detected (>600ms) -> Toggling NOS Mode")
        asyncio.create_task(self._toggle_nos())

    async def _send_command(self, cmd: str, params: Optional[dict] = None) -> Optional[dict]:
        try:
            reader, writer = await asyncio.open_unix_connection(self.socket_path)
            req = encode_message({"command": cmd, "params": params or {}})
            writer.write(req)
            await writer.drain()

            while True:
                line = await reader.readline()
                if not line:
                    break
                ok, res, _ = decode_message(line.decode())
                if ok and res and "success" in res:
                    writer.close()
                    await writer.wait_closed()
                    return res
        except Exception as e:
            log.warning(f"Failed to communicate with daemon socket: {e}")
        return None

    async def _toggle_nos(self) -> None:
        info = await self._send_command("get_all_settings")
        if info and info.get("success"):
            data = info.get("data", {})
            is_nos_active = data.get("is_nos_active", False)
            if is_nos_active:
                await self._send_command("deactivate_nos")
            else:
                await self._send_command("activate_nos")
        else:
            # Fallback toggle
            await self._send_command("activate_nos")

    async def run(self) -> None:
        self.load_config()
        dev_path = self.find_keyboard_device()
        if not dev_path or not os.path.exists(dev_path):
            log.error("No valid keyboard input device found for Nitro button service")
            return

        log.info(f"Monitoring Nitro key on device {dev_path} (target keycode={self.target_keycode})")
        self.is_running = True

        try:
            fd = os.open(dev_path, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            log.error(f"Permission denied accessing {dev_path}. Must run with root/input privileges.")
            return

        loop = asyncio.get_running_loop()
        reader_queue: asyncio.Queue[bytes] = asyncio.Queue()

        def on_read():
            try:
                chunk = os.read(fd, EVENT_SIZE * 16)
                if chunk:
                    reader_queue.put_nowait(chunk)
            except (BlockingIOError, OSError):
                pass

        loop.add_reader(fd, on_read)

        try:
            while self.is_running:
                chunk = await reader_queue.get()
                offset = 0
                while offset + EVENT_SIZE <= len(chunk):
                    evt_data = chunk[offset:offset + EVENT_SIZE]
                    offset += EVENT_SIZE
                    tv_sec, tv_usec, ev_type, ev_code, ev_value = struct.unpack(EVENT_FORMAT, evt_data)
                    if ev_type == EV_KEY and ev_code == self.target_keycode:
                        self._state_machine.handle_event(ev_value)
        finally:
            loop.remove_reader(fd)
            os.close(fd)

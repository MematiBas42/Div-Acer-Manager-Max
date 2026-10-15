"""Boot Boost Manager for initial thermal cooling on startup."""

import asyncio
import logging
from typing import Callable, Optional

log = logging.getLogger("acersense.boot_boost")


class BootBoostManager:
    """Provides temporary maximum cooling during boot before applying default profiles."""

    def __init__(self, on_finish_callback: Callable[[], None]):
        self.enabled: bool = False
        self.delay_seconds: int = 5
        self.is_active: bool = False
        self._task: Optional[asyncio.Task] = None
        self._on_finish_callback = on_finish_callback

    def configure(self, enabled: bool, delay_seconds: int = 5) -> None:
        self.enabled = enabled
        self.delay_seconds = max(1, min(60, delay_seconds))

    async def start_boost(self, trigger_max_fans: Callable[[], None]) -> None:
        """Trigger boost sequence if enabled."""
        if not self.enabled or self.is_active:
            return

        self.is_active = True
        log.info(f"Starting Boot Boost for {self.delay_seconds} seconds")
        trigger_max_fans()

        try:
            await asyncio.sleep(self.delay_seconds)
            log.info("Boot Boost duration expired, transitioning to default profile")
        except asyncio.CancelledError:
            log.info("Boot Boost cancelled prematurely")
        finally:
            self.is_active = False
            self._on_finish_callback()

    def cancel(self) -> None:
        """Cancel active boot boost immediately."""
        if self._task and not self._task.done():
            self._task.cancel()
        self.is_active = False

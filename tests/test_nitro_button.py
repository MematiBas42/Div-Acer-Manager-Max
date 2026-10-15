"""Unit tests for NitroButtonStateMachine deterministic input handling."""

import asyncio
import unittest
from daemon.services.nitro_button import NitroButtonStateMachine, KEY_DOWN, KEY_UP, KEY_HOLD


class TestNitroButtonStateMachine(unittest.IsolatedAsyncioTestCase):
    async def test_short_press(self):
        short_count = 0
        long_count = 0

        def on_short():
            nonlocal short_count
            short_count += 1

        def on_long():
            nonlocal long_count
            long_count += 1

        sm = NitroButtonStateMachine(
            on_short_press=on_short,
            on_long_press=on_long,
            threshold_sec=0.1
        )

        t0 = 1000.0
        sm.handle_event(KEY_DOWN, now=t0)
        # Release 50ms later (well below 100ms threshold)
        sm.handle_event(KEY_UP, now=t0 + 0.05)

        # Allow any pending async tasks to settle
        await asyncio.sleep(0.15)

        self.assertEqual(short_count, 1)
        self.assertEqual(long_count, 0)

    async def test_long_press(self):
        short_count = 0
        long_count = 0

        def on_short():
            nonlocal short_count
            short_count += 1

        def on_long():
            nonlocal long_count
            long_count += 1

        sm = NitroButtonStateMachine(
            on_short_press=on_short,
            on_long_press=on_long,
            threshold_sec=0.1
        )

        t0 = 1000.0
        sm.handle_event(KEY_DOWN, now=t0)
        # Wait until long press threshold triggers
        await asyncio.sleep(0.15)

        # Release afterwards
        sm.handle_event(KEY_UP, now=t0 + 0.20)

        self.assertEqual(short_count, 0)
        self.assertEqual(long_count, 1)

    async def test_autorepeat_ignored(self):
        short_count = 0
        long_count = 0

        def on_short():
            nonlocal short_count
            short_count += 1

        def on_long():
            nonlocal long_count
            long_count += 1

        sm = NitroButtonStateMachine(
            on_short_press=on_short,
            on_long_press=on_long,
            threshold_sec=0.1
        )

        t0 = 1000.0
        sm.handle_event(KEY_DOWN, now=t0)
        sm.handle_event(KEY_HOLD, now=t0 + 0.02)
        sm.handle_event(KEY_HOLD, now=t0 + 0.04)
        sm.handle_event(KEY_UP, now=t0 + 0.06)

        await asyncio.sleep(0.15)

        self.assertEqual(short_count, 1)
        self.assertEqual(long_count, 0)


if __name__ == "__main__":
    unittest.main()

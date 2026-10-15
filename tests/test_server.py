"""Unit tests for AcerSenseServer Asyncio IPC Unix Domain Socket."""

import os
import json
import shutil
import tempfile
import asyncio
import unittest

from daemon.core.hardware_manager import HardwareManager
from daemon.core.power_optimizer import PowerOptimizer
from daemon.core.boot_boost import BootBoostManager
from daemon.ipc.server import AcerSenseServer
from daemon.ipc.protocol import encode_message, decode_message


class TestAcerSenseServer(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.sock_path = os.path.join(self.test_dir, "test_acersense.sock")
        self.fan_file = os.path.join(self.test_dir, "fan_speed")
        self.profile_file = os.path.join(self.test_dir, "platform_profile")
        self.profile_choices = os.path.join(self.test_dir, "platform_profile_choices")

        with open(self.fan_file, "w") as f:
            f.write("0,0\n")
        with open(self.profile_file, "w") as f:
            f.write("balanced\n")
        with open(self.profile_choices, "w") as f:
            f.write("quiet balanced performance turbo\n")

        self.hardware = HardwareManager(base_override=self.test_dir)
        self.hardware.available_features.add("fan_speed")
        self.hardware.available_features.add("thermal_profile")

        self.power = PowerOptimizer(sysfs_root=self.test_dir)
        self.boot_boost = BootBoostManager(lambda: None)

        self.server = AcerSenseServer(
            hardware=self.hardware,
            power=self.power,
            boot_boost=self.boot_boost,
            socket_path=self.sock_path,
            compat_symlink=None
        )
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()
        shutil.rmtree(self.test_dir)

    async def test_ping(self):
        reader, writer = await asyncio.open_unix_connection(self.sock_path)
        req = encode_message({"command": "ping"})
        writer.write(req)
        await writer.drain()

        line = await reader.readline()
        ok, res, _ = decode_message(line.decode())
        self.assertTrue(ok)
        assert res is not None
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("data"), "pong")

        writer.close()
        await writer.wait_closed()

    async def test_fan_speed_and_events(self):
        reader, writer = await asyncio.open_unix_connection(self.sock_path)

        # Set fan speed 0, 75 (CPU auto, GPU manual)
        req = encode_message({"command": "set_fan_speed", "params": {"cpu": 0, "gpu": 75}})
        writer.write(req)
        await writer.drain()

        # Read responses (could include broadcast event first, then command response)
        got_response = False
        while True:
            line = await reader.readline()
            if not line:
                break
            ok, res, _ = decode_message(line.decode())
            self.assertTrue(ok)
            assert res is not None
            if res.get("type") == "event":
                self.assertEqual(res.get("event"), "fan_speed_changed")
                continue
            if "success" in res:
                self.assertTrue(res.get("success"))
                got_response = True
                break

        self.assertTrue(got_response)

        # Check sysfs fan file
        with open(self.fan_file, "r") as f:
            self.assertEqual(f.read().strip(), "0,75")

        writer.close()
        await writer.wait_closed()

    async def test_get_all_settings(self):
        reader, writer = await asyncio.open_unix_connection(self.sock_path)
        req = encode_message({"command": "get_all_settings"})
        writer.write(req)
        await writer.drain()

        line = await reader.readline()
        ok, res, _ = decode_message(line.decode())
        self.assertTrue(ok)
        assert res is not None
        self.assertTrue(res.get("success"))
        data = res.get("data", {})
        self.assertEqual(data.get("version"), "1.0.0")
        self.assertEqual(data.get("driver_version"), "25.701")
        self.assertIn("thermal_profile", data)

        writer.close()
        await writer.wait_closed()

    async def test_hyprland_settings_commands(self):
        reader, writer = await asyncio.open_unix_connection(self.sock_path)

        # set_hyprland_integration
        req = encode_message({"command": "set_hyprland_integration", "parameters": {"enabled": True}})
        writer.write(req)
        await writer.drain()
        line = await reader.readline()
        ok, res, _ = decode_message(line.decode())
        self.assertTrue(ok)
        self.assertTrue(res.get("success"))

        # set_hyprland_opacity_settings
        req = encode_message({
            "command": "set_hyprland_opacity_settings",
            "parameters": {
                "ac_active": 0.98,
                "ac_inactive": 0.92,
                "bat_active": 1.0,
                "bat_inactive": 1.0
            }
        })
        writer.write(req)
        await writer.drain()
        line = await reader.readline()
        ok, res, _ = decode_message(line.decode())
        self.assertTrue(ok)
        self.assertTrue(res.get("success"))

        writer.close()
        await writer.wait_closed()

    async def test_malformed_json(self):
        reader, writer = await asyncio.open_unix_connection(self.sock_path)
        writer.write(b"NOT A VALID JSON\n")
        await writer.drain()

        line = await reader.readline()
        ok, res, _ = decode_message(line.decode())
        self.assertTrue(ok)
        assert res is not None
        self.assertFalse(res.get("success"))
        self.assertIn("Malformed JSON", res.get("error", ""))

        writer.close()
        await writer.wait_closed()


if __name__ == "__main__":
    unittest.main()

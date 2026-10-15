import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
import shutil
import pwd

from daemon.services.hyprland_bridge import HyprlandBridge

class TestHyprlandBridge(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.bridge = HyprlandBridge()
        self.bridge.configure(enabled=True, ac_active=1.0, ac_inactive=0.9, bat_active=0.8, bat_inactive=0.7)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_sync_visuals_conf(self):
        hypr_dir = os.path.join(self.test_dir, ".config", "hypr")
        os.makedirs(hypr_dir)

        fake_pwnam = MagicMock(pw_name="testuser", pw_uid=1000, pw_gid=1000, pw_dir=self.test_dir)
        with patch.object(self.bridge, "get_hyprland_session", return_value=("testuser", 1000, "sig123", "wayland-1")), \
             patch("pwd.getpwuid", return_value=fake_pwnam), \
             patch.object(self.bridge, "_reload_hyprland") as mock_reload, \
             patch("os.chown"):
            
            ok = self.bridge.sync_visuals("Performance", is_ac=True)
            self.assertTrue(ok)
            mock_reload.assert_called_once_with("sig123", "wayland-1", 1000)

            conf_path = os.path.join(hypr_dir, "acersense.conf")
            self.assertTrue(os.path.exists(conf_path))
            with open(conf_path, "r") as f:
                content = f.read()
            self.assertIn("decoration:active_opacity = 1.00", content)
            self.assertIn("decoration:inactive_opacity = 0.90", content)

    def test_sync_visuals_lua(self):
        hypr_dir = os.path.join(self.test_dir, ".config", "hypr")
        os.makedirs(hypr_dir)
        with open(os.path.join(hypr_dir, "hyprland.lua"), "w") as f:
            f.write("-- dummy\n")

        fake_pwnam = MagicMock(pw_name="testuser", pw_uid=1000, pw_gid=1000, pw_dir=self.test_dir)
        with patch.object(self.bridge, "get_hyprland_session", return_value=("testuser", 1000, None, None)), \
             patch("pwd.getpwuid", return_value=fake_pwnam), \
             patch("os.chown"):
            
            ok = self.bridge.sync_visuals("Eco", is_ac=False)
            self.assertTrue(ok)

            lua_path = os.path.join(hypr_dir, "custom", "acersense.lua")
            self.assertTrue(os.path.exists(lua_path))
            with open(lua_path, "r") as f:
                content = f.read()
            self.assertIn("local active_opacity = 0.80", content)
            self.assertIn("local inactive_opacity = 0.70", content)

    def test_disabled_bridge_no_op(self):
        self.bridge.enabled = False
        ok = self.bridge.sync_visuals("Performance", is_ac=True)
        self.assertFalse(ok)

if __name__ == '__main__':
    unittest.main()

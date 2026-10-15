"""Hyprland Desktop Bridge for AcerSense.
Dynamically synchronizes window opacity, animations, and visual modes based on thermal and power states.
Includes strict security checks: atomic file writes, user UID verification, and symlink validation.
"""

import os
import pwd
import glob
import subprocess
import logging
from typing import Dict, List, Optional, Set, Tuple

log = logging.getLogger("acersense.hyprland")


class HyprlandBridge:
    """Manages secure generation of Hyprland configuration and IPC reload."""

    def __init__(self):
        self.enabled: bool = False
        self.ac_active_opacity: float = 1.0
        self.ac_inactive_opacity: float = 1.0
        self.bat_active_opacity: float = 0.95
        self.bat_inactive_opacity: float = 0.90

    def configure(
        self,
        enabled: bool,
        ac_active: float = 1.0,
        ac_inactive: float = 1.0,
        bat_active: float = 0.95,
        bat_inactive: float = 0.90,
    ) -> None:
        self.enabled = enabled
        self.ac_active_opacity = max(0.1, min(1.0, ac_active))
        self.ac_inactive_opacity = max(0.1, min(1.0, ac_inactive))
        self.bat_active_opacity = max(0.1, min(1.0, bat_active))
        self.bat_inactive_opacity = max(0.1, min(1.0, bat_inactive))

    def get_hyprland_session(self) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]:
        """
        Returns (username, uid, instance_signature, wayland_display).
        Detects active user running Hyprland from /run/user/<uid>/hypr.
        """
        base_run = "/run/user"
        if not os.path.exists(base_run):
            return None, None, None, None

        for user_dir in os.listdir(base_run):
            if not user_dir.isdigit():
                continue
            uid = int(user_dir)
            user_path = os.path.join(base_run, user_dir)
            hypr_dir = os.path.join(user_path, "hypr")

            wayland_disp = None
            try:
                for item in os.listdir(user_path):
                    if item.startswith("wayland-") and "lock" not in item:
                        wayland_disp = item
                        break
            except OSError:
                pass

            if os.path.isdir(hypr_dir):
                try:
                    for sig in os.listdir(hypr_dir):
                        sig_path = os.path.join(hypr_dir, sig)
                        if os.path.isdir(sig_path) and not sig.startswith("."):
                            if any(x.endswith(".sock") for x in os.listdir(sig_path)):
                                user_info = pwd.getpwuid(uid)
                                return user_info.pw_name, uid, sig, wayland_disp
                except OSError:
                    continue

        # Fallback to standard 1000 user
        try:
            for p in pwd.getpwall():
                if 1000 <= p.pw_uid < 60000 and "nologin" not in p.pw_shell and "false" not in p.pw_shell:
                    return p.pw_name, p.pw_uid, None, None
        except Exception:
            pass

        return None, None, None, None

    def _atomic_write_user_file(self, path: str, content: str, uid: int, gid: int) -> bool:
        """Write file atomically and enforce that destination is owned by the user (prevent symlink hijacking)."""
        try:
            target_path = path
            if os.path.islink(path):
                real_path = os.path.realpath(path)
                stat = os.stat(real_path)
                if stat.st_uid != uid:
                    log.error(f"Security: Target of symlink {path} is not owned by uid {uid}")
                    return False
                target_path = real_path

            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            tmp_path = target_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)

            os.chown(tmp_path, uid, gid)
            os.chmod(tmp_path, 0o644)
            os.replace(tmp_path, target_path)
            return True
        except Exception as e:
            log.error(f"Failed to write file {path}: {e}")
            return False

    def sync_visuals(self, profile: str, is_ac: bool) -> bool:
        """Generate and update Hyprland mode config according to power state."""
        if not self.enabled:
            return False

        username, uid, sig, display = self.get_hyprland_session()
        if not username or uid is None:
            return False

        try:
            user_entry = pwd.getpwuid(uid)
            user_home = user_entry.pw_dir
            gid = user_entry.pw_gid
        except KeyError:
            return False

        config_dir = os.path.join(user_home, ".config/hypr")
        is_lua = os.path.exists(os.path.join(config_dir, "hyprland.lua"))

        active_op = self.ac_active_opacity if is_ac else self.bat_active_opacity
        inactive_op = self.ac_inactive_opacity if is_ac else self.bat_inactive_opacity

        if is_lua:
            lua_content = (
                "-- AcerSense Auto-Generated Hyprland Config\n"
                f'local profile = "{profile}"\n'
                f'local is_ac = {str(is_ac).lower()}\n'
                f'local active_opacity = {active_op:.2f}\n'
                f'local inactive_opacity = {inactive_op:.2f}\n\n'
                'return {\n'
                '    decoration = {\n'
                '        active_opacity = active_opacity,\n'
                '        inactive_opacity = inactive_opacity,\n'
                '    }\n'
                '}\n'
            )
            out_file = os.path.join(config_dir, "custom/acersense.lua")
            self._atomic_write_user_file(out_file, lua_content, uid, gid)
        else:
            conf_content = (
                "# AcerSense Auto-Generated Hyprland Config\n"
                f"# Profile: {profile} | AC: {is_ac}\n"
                f"decoration:active_opacity = {active_op:.2f}\n"
                f"decoration:inactive_opacity = {inactive_op:.2f}\n"
            )
            out_file = os.path.join(config_dir, "acersense.conf")
            self._atomic_write_user_file(out_file, conf_content, uid, gid)

        # Trigger reload if active instance is detected
        if sig and display:
            self._reload_hyprland(sig, display, uid)

        return True

    def _reload_hyprland(self, signature: str, display: str, uid: int) -> None:
        try:
            env = os.environ.copy()
            env["HYPRLAND_INSTANCE_SIGNATURE"] = signature
            env["WAYLAND_DISPLAY"] = display
            env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"

            subprocess.run(
                ["hyprctl", "reload"],
                env=env,
                capture_output=True,
                timeout=2,
                user=uid
            )
        except Exception as e:
            log.debug(f"Could not trigger hyprctl reload: {e}")

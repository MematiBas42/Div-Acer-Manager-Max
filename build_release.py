#!/usr/bin/env python3
"""
Builds and packages the complete AcerSense suite from source.
This script compiles the GUI and daemon, and assembles them with
installer scripts into a local release folder.
Note: This version DOES NOT include drivers. Drivers must be installed separately (e.g. via DKMS).
"""

import os
import sys
import subprocess
import shutil
import re
from pathlib import Path

def run_command(cmd, cwd='.', check=True):
    """Run a command and exit if it fails."""
    print(f"\n--- Running: {' '.join(cmd)} in {cwd} ---")
    try:
        result = subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("Stderr:")
            print(result.stderr)
        return result
    except FileNotFoundError as e:
        print(f"Error: Command '{cmd[0]}' not found. Is it installed and in your PATH?")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: Command failed with exit code {e.returncode}")
        print(f"Stdout:\n{e.stdout}")
        print(f"Stderr:\n{e.stderr}")
        sys.exit(1)

class ReleaseBuilder:
    def __init__(self):
        self.project_root = Path(__file__).parent.absolute()
        self.gui_dir = self.project_root / "AcerSense"
        self.daemon_dir = self.project_root / "Daemon"
        self.publish_dir = self.project_root / "Publish"
        self.setup_template = self.project_root / "scripts" / "setup_template.sh"

        print(f"Project Root: {self.project_root}")

    def get_version(self):
        """Get version from csproj file."""
        csproj_path = self.gui_dir / "AcerSense.csproj"
        try:
            with open(csproj_path, 'r') as f:
                content = f.read()
            match = re.search(r'<Version>(.*?)<\/Version>', content)
            if match:
                version = match.group(1)
                print(f"Detected version: {version}")
                return version
        except FileNotFoundError:
            pass
        print("Warning: Could not detect version. Using '1.0.0'.")
        return "1.0.0"

    def build_gui(self):
        print("\n=== Building GUI ===")
        cmd = [
            "dotnet", "publish",
            "-c", "Release",
            "-f", "net9.0",
            "-r", "linux-x64",
            "--self-contained", "true",
            "/p:PublishSingleFile=true",
            "/p:IncludeNativeLibrariesForSelfExtract=true",
            "/p:IncludeAllContentForSelfExtract=true"
        ]
        run_command(cmd, cwd=self.gui_dir)

    def build_daemon(self):
        print("\n=== Building Daemon ===")
        daemon_script = self.daemon_dir / "AcerSense-Daemon.py"
        if not daemon_script.exists():
            print(f"Error: Could not find daemon script in {self.daemon_dir}")
            sys.exit(1)

        cmd = ["pyinstaller", "--onefile", "--clean", daemon_script.name]
        run_command(cmd, cwd=self.daemon_dir)

    def assemble_package(self, version):
        print(f"\n=== Assembling Package v{version} ===")
        package_dir = self.publish_dir / f"AcerSense-Release-v{version}"

        if package_dir.exists():
            print(f"Removing existing package directory: {package_dir}")
            shutil.rmtree(package_dir)
        
        print(f"Creating package structure in: {package_dir}")
        gui_target = package_dir / "AcerSense-GUI"
        daemon_target = package_dir / "AcerSense-Daemon"
        
        gui_target.mkdir(parents=True)
        daemon_target.mkdir(parents=True)

        # 1. Copy Setup Script
        if self.setup_template.exists():
            shutil.copy2(self.setup_template, package_dir / "setup.sh")
            print("Copied setup script.")
        else:
            print("Error: setup_template.sh not found. Package will be incomplete.")

        # 2. Copy GUI
        gui_source_dir = self.gui_dir / "bin/Release/net9.0/linux-x64/publish"
        if (gui_source_dir / "AcerSense").exists():
            shutil.copy2(gui_source_dir / "AcerSense", gui_target / "AcerSense")
            for icon_name in ["icon.png", "iconTransparent.png"]:
                icon_path = self.gui_dir / icon_name
                if icon_path.exists():
                    shutil.copy2(icon_path, gui_target)
            print("Copied GUI and icons.")
        else:
            print("Error: Compiled GUI not found.")

        # 3. Copy Daemon
        daemon_dist = self.daemon_dir / "dist" / "AcerSense-Daemon"
        if daemon_dist.exists():
            shutil.copy2(daemon_dist, daemon_target / "AcerSense-Daemon")
            print("Copied Daemon.")
        else:
            print("Error: Compiled Daemon not found.")

        # 4. Ensure setup script is executable
        (package_dir / "setup.sh").chmod(0o755)

        # 5. Create release.txt
        release_info = f"""AcerSense Release Information
========================
Version: {version}
Build Date: {subprocess.check_output(['date'], text=True).strip()}
"""
        with open(package_dir / "release.txt", 'w') as f:
            f.write(release_info)

        print(f"\n🎉 Successfully created release package at: {package_dir}")


def main():
    builder = ReleaseBuilder()
    version = builder.get_version()
    builder.build_gui()
    builder.build_daemon()
    builder.assemble_package(version)

if __name__ == "__main__":
    main()

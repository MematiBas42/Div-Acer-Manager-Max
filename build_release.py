#!/usr/bin/env python3
"""
Builds and packages the complete AcerSense suite from source.
This script compiles the GUI and daemon, and assembles them with drivers
and installer scripts into a local release folder.
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
        self.drivers_dir = self.project_root / "Linuwu-Sense"
        self.template_dir = self.project_root / "build_template"
        self.publish_dir = self.project_root / "Publish"

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
            pass # Fallback
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
        # Assuming the main script is named after the directory
        daemon_script = self.daemon_dir / (self.daemon_dir.name + ".py")
        if not daemon_script.exists(): # Fallback to common name
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
        gui_target = package_dir / "DAMX-GUI"
        daemon_target = package_dir / "DAMX-Daemon"
        drivers_target = package_dir / "Linuwu-Sense"
        
        gui_target.mkdir(parents=True)
        daemon_target.mkdir(parents=True)

        # 1. Copy GUI
        gui_source_dir = self.gui_dir / "bin/Release/net9.0/linux-x64/publish"
        shutil.copy2(gui_source_dir / "AcerSense", gui_target / "AcerSense")
        # Copy icons if they exist
        for icon_name in ["icon.png", "iconTransparent.png"]:
            icon_path = self.gui_dir / icon_name
            if icon_path.exists():
                shutil.copy2(icon_path, gui_target)
        print("Copied GUI and icons.")

        # 2. Copy Daemon
        daemon_executable_name = "AcerSense-Daemon"  # The actual name of the compiled executable
        shutil.copy2(self.daemon_dir / "dist" / daemon_executable_name, daemon_target / daemon_executable_name)
        print("Copied Daemon.")

        # 3. Copy Drivers
        shutil.copytree(self.drivers_dir, drivers_target)
        print("Copied Drivers.")

        # 4. Copy setup script
        setup_script_path = self.template_dir / "setup.sh"
        if not setup_script_path.exists():
            print(f"Error: setup.sh not found in {self.template_dir}")
            sys.exit(1)
        shutil.copy2(setup_script_path, package_dir)
        # Make it executable
        (package_dir / "setup.sh").chmod(0o755)
        print("Copied setup script.")

        # 5. Create release.txt
        release_info = f"""AcerSense Release Information
========================
Version: {version}
Build Date: {subprocess.check_output(['date'], text=True).strip()}
"""
        with open(package_dir / "release.txt", 'w') as f:
            f.write(release_info)
        print("Created release.txt.")

        print(f"\n🎉 Successfully created release package at: {package_dir}")


def main():
    builder = ReleaseBuilder()
    version = builder.get_version()
    builder.build_gui()
    builder.build_daemon()
    builder.assemble_package(version)

if __name__ == "__main__":
    main()

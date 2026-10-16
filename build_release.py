#!/usr/bin/env python3
"""Build and package AcerSense Suite for Linux.
Executes test suites, builds Avalonia GUI (self-contained), and structures release files.
"""

import os
import sys
import shutil
import subprocess
import unittest

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(REPO_DIR, "dist")

def run_tests() -> bool:
    print("==> [1/4] Running test suite...")
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(REPO_DIR, "tests"))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

def build_gui() -> bool:
    print("==> [2/4] Building Avalonia GUI (.NET 10 self-contained)...")
    gui_proj = os.path.join(REPO_DIR, "DivAcerManagerMax", "DivAcerManagerMax.csproj")
    out_dir = os.path.join(DIST_DIR, "gui")
    
    cmd = [
        "dotnet", "publish", gui_proj,
        "-c", "Release",
        "-r", "linux-x64",
        "--self-contained", "true",
        "-p:PublishSingleFile=true",
        "-p:IncludeNativeLibrariesForSelfExtract=true",
        "-o", out_dir
    ]
    
    try:
        res = subprocess.run(cmd, check=True)
        return res.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"Warning: dotnet publish failed or dotnet is not available locally: {e}")
        print("Note: GUI can be published on Arch machine with dotnet SDK.")
        return False

def package_daemon() -> None:
    print("==> [3/4] Packaging Daemon & Services...")
    daemon_out = os.path.join(DIST_DIR, "daemon")
    os.makedirs(daemon_out, exist_ok=True)
    
    # Copy daemon package
    src_daemon = os.path.join(REPO_DIR, "daemon")
    for root, dirs, files in os.walk(src_daemon):
        # Ignore pycache
        if "__pycache__" in root:
            continue
        rel_path = os.path.relpath(root, src_daemon)
        dest_dir = os.path.join(daemon_out, rel_path)
        os.makedirs(dest_dir, exist_ok=True)
        for f in files:
            if not f.endswith(".pyc") and not f.endswith(".service"):
                shutil.copy2(os.path.join(root, f), os.path.join(dest_dir, f))
                
    # Copy systemd units
    systemd_out = os.path.join(DIST_DIR, "systemd")
    os.makedirs(systemd_out, exist_ok=True)
    for s in ["acersense-daemon.service", "acersense-nitro-button.service"]:
        src_s = os.path.join(src_daemon, s)
        if os.path.exists(src_s):
            shutil.copy2(src_s, os.path.join(systemd_out, s))

    # Copy helper scripts
    scripts_out = os.path.join(DIST_DIR, "scripts")
    os.makedirs(scripts_out, exist_ok=True)
    post_qshell = os.path.join(REPO_DIR, "scripts", "post_update_fixqshell.sh")
    if os.path.exists(post_qshell):
        shutil.copy2(post_qshell, os.path.join(scripts_out, "post_update_fixqshell.sh"))

    # Copy application icon
    icon_src = os.path.join(REPO_DIR, "DivAcerManagerMax", "icon.png")
    if os.path.exists(icon_src):
        shutil.copy2(icon_src, os.path.join(DIST_DIR, "icon.png"))

def generate_installer() -> None:
    print("==> [4/4] Generating deployment installer...")
    installer_path = os.path.join(DIST_DIR, "install.sh")
    content = """#!/usr/bin/env bash
set -e

if [ "$EUID" -ne 0 ]; then
    echo "Hata: Kurulum için root izinleri gereklidir (sudo bash install.sh)."
    exit 1
fi

INSTALL_DIR="/opt/acersense"
SYSTEMD_DIR="/etc/systemd/system"
DESKTOP_DIR="/usr/share/applications"
ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Gerekli python modülleri kontrol ediliyor..."
if ! python3 -c "import evdev" &>/dev/null; then
    echo "==> evdev modülü kuruluyor..."
    if command -v pacman &>/dev/null; then
        pacman -S --noconfirm --needed python-evdev
    elif command -v apt-get &>/dev/null; then
        apt-get update -y && apt-get install -y python3-evdev
    elif command -v dnf &>/dev/null; then
        dnf install -y python3-evdev
    else
        python3 -m pip install --break-system-packages evdev || true
    fi
fi

echo "==> AcerSense kurulumu yapılıyor: ${INSTALL_DIR}"
systemctl stop acersense-nitro-button.service 2>/dev/null || true
systemctl stop acersense-daemon.service 2>/dev/null || true
systemctl stop damx-daemon.service 2>/dev/null || true

mkdir -p "${INSTALL_DIR}"
cp -rf "${SCRIPT_DIR}/daemon" "${INSTALL_DIR}/"
if [ -d "${SCRIPT_DIR}/gui" ]; then
    cp -rf "${SCRIPT_DIR}/gui" "${INSTALL_DIR}/"
    chmod +x "${INSTALL_DIR}/gui/DivAcerManagerMax" 2>/dev/null || true
    ln -sf "${INSTALL_DIR}/gui/DivAcerManagerMax" /usr/local/bin/acersense-gui || true
    ln -sf "${INSTALL_DIR}/gui/DivAcerManagerMax" /usr/local/bin/acersense || true
    # Eski kalıntıları temizle
    rm -f /usr/local/bin/damx /usr/local/bin/damx-gui 2>/dev/null || true
fi
if [ -d "${SCRIPT_DIR}/scripts" ]; then
    cp -rf "${SCRIPT_DIR}/scripts" "${INSTALL_DIR}/"
fi

# Masaüstü ikonu ve .desktop kaydı (Eski damx kalıntıları temizlenir)
rm -f "${DESKTOP_DIR}/damx.desktop" "${DESKTOP_DIR}/DAMX.desktop" "${ICON_DIR}/damx.png" 2>/dev/null || true
if [ -f "${SCRIPT_DIR}/icon.png" ]; then
    mkdir -p "${ICON_DIR}"
    cp -f "${SCRIPT_DIR}/icon.png" "${ICON_DIR}/acersense.png"
fi

mkdir -p "${DESKTOP_DIR}"
cat > "${DESKTOP_DIR}/acersense.desktop" << 'EOF'
[Desktop Entry]
Name=AcerSense
Comment=Acer Predator & Nitro Hardware Control Center
Exec=/opt/acersense/gui/DivAcerManagerMax
Icon=acersense
Terminal=false
Type=Application
Categories=Utility;Settings;System;
StartupNotify=true
EOF

# Systemd servislerini bağla
if [ -d "${SCRIPT_DIR}/systemd" ]; then
    cp -f "${SCRIPT_DIR}/systemd/"*.service "${SYSTEMD_DIR}/"
    systemctl daemon-reload
    systemctl enable --now acersense-daemon.service
    systemctl enable --now acersense-nitro-button.service
fi

echo "==> Kurulum başarıyla tamamlandı!"
systemctl status acersense-daemon.service --no-pager || true
"""
    with open(installer_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(installer_path, 0o755)

def main():
    if not run_tests():
        print("Tests failed! Aborting release build.")
        sys.exit(1)
        
    os.makedirs(DIST_DIR, exist_ok=True)
    build_gui()
    package_daemon()
    generate_installer()
    print("\n[SUCCESS] Build and packaging complete in dist/")

if __name__ == '__main__':
    main()

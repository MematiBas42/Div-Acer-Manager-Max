#!/bin/bash

# AcerSense Installer Script
# This script installs, uninstalls, or updates the AcerSense Suite for Acer laptops on Linux
# Components: AcerSense-Daemon and AcerSense-GUI
# Requirement: linuwu-sense driver (DKMS recommended)

# Constants
SCRIPT_VERSION="1.1.0"
INSTALL_DIR="/opt/acersense"
BIN_DIR="/usr/local/bin"
SYSTEMD_DIR="/etc/systemd/system"
DAEMON_SERVICE_NAME="acersense-daemon.service"
TARGET_USER="${SUDO_USER:-$USER}"
DESKTOP_FILE_DIR="/usr/share/applications"
ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
NITRO_BUTTON_DESKTOP_NAME="nitrobutton.desktop"
USER_HOME=$(getent passwd $TARGET_USER | cut -d: -f6)
USER_CONFIG_DIR="$USER_HOME/.config/autostart"

# Legacy paths for cleanup (DAMX)
LEGACY_INSTALL_DIR="/opt/damx"
LEGACY_DAEMON_SERVICE_NAME="damx-daemon.service"

# Change to script directory
cd "$(dirname "$0")"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

LOG_FILE="/var/log/acersense_install.log"

log() {
    echo -e "$1"
    if [ -w "$LOG_FILE" ] || [ ! -e "$LOG_FILE" ] && [ "$EUID" -eq 0 ]; then
        # Only write if writable or if we are root and file doesn't exist (will be created later)
        # Actually, the file is created after check_root. So let's just check writability.
        if [ -f "$LOG_FILE" ]; then
             echo "$(date) - $(echo "$1" | sed 's/\x1b\[[0-9;]*m//g')" >> "$LOG_FILE"
        fi
    fi
}

pause() {
  echo -e "${BLUE}Press any key to continue...${NC}"
  read -n 1 -s -r
}

check_root() {
  if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}This script requires root privileges.${NC}"
    if command -v sudo &> /dev/null; then
      echo -e "${BLUE}Attempting to run with sudo...${NC}"
      exec sudo "$0" "$@"
      exit $?
    else
      echo -e "${RED}Error: sudo not found. Please run this script as root.${NC}"
      pause
      exit 1
    fi
  fi
}

print_banner() {
  clear
  echo -e "${BLUE}==========================================${NC}"
  echo -e "${BLUE}      AcerSense Suite Installer v${SCRIPT_VERSION}      ${NC}"
  echo -e "${BLUE}    Acer Laptop Control Center for Linux  ${NC}"
  echo -e "${BLUE}==========================================${NC}"
  echo ""
}

cleanup_legacy_installation() {
  echo -e "${YELLOW}Checking for legacy (DAMX) installations...${NC}"
  local cleanup_performed=false

  # Clean up old DAMX service
  if [ -f "${SYSTEMD_DIR}/${LEGACY_DAEMON_SERVICE_NAME}" ]; then
    echo "Stopping legacy service: ${LEGACY_DAEMON_SERVICE_NAME}..."
    systemctl stop ${LEGACY_DAEMON_SERVICE_NAME} 2>/dev/null
    systemctl disable ${LEGACY_DAEMON_SERVICE_NAME} 2>/dev/null
    rm -f "${SYSTEMD_DIR}/${LEGACY_DAEMON_SERVICE_NAME}"
    cleanup_performed=true
  fi

  # Clean up old DAMX directory
  if [ -d "${LEGACY_INSTALL_DIR}" ]; then
    echo "Removing legacy directory: ${LEGACY_INSTALL_DIR}..."
    rm -rf "${LEGACY_INSTALL_DIR}"
    cleanup_performed=true
  fi

  # Clean up old binaries/shortcuts
  rm -f "${BIN_DIR}/DAMX" "${BIN_DIR}/damx"
  rm -f "${DESKTOP_FILE_DIR}/damx.desktop"
  rm -f "${ICON_DIR}/damx.png"

  if [ "$cleanup_performed" = true ]; then
    systemctl daemon-reload
    echo -e "${GREEN}Legacy cleanup completed.${NC}"
  fi
}

comprehensive_cleanup() {
  log "${YELLOW}Performing comprehensive cleanup...${NC}"

  log "Removing DKMS driver if present..."
  if command -v dkms &> /dev/null; then
      if dkms status 2>/dev/null | grep -q "linuwu-sense"; then
          dkms remove linuwu-sense/1.0.0 --all >> "$LOG_FILE" 2>&1
          log "Removed linuwu-sense from DKMS."
      fi
  fi
  
  rmmod linuwu_sense >> "$LOG_FILE" 2>&1 || true
  rm -rf /usr/src/linuwu-sense-1.0.0

  if systemctl is-active --quiet ${DAEMON_SERVICE_NAME} 2>/dev/null; then
    systemctl stop ${DAEMON_SERVICE_NAME} >> "$LOG_FILE" 2>&1
  fi
  if systemctl is-enabled --quiet ${DAEMON_SERVICE_NAME} 2>/dev/null; then
    systemctl disable ${DAEMON_SERVICE_NAME}
  fi

  rm -f "${SYSTEMD_DIR}/${DAEMON_SERVICE_NAME}"
  cleanup_legacy_installation

  # Remove current installed files
  log "Removing current installation files..."
  rm -rf ${INSTALL_DIR}
  rm -rf /etc/AcerSenseDaemon
  rm -f ${BIN_DIR}/acersense
  rm -f ${DESKTOP_FILE_DIR}/acersense.desktop
  rm -f ${ICON_DIR}/acersense.png

  log "Removing configuration and log files..."
  rm -f /etc/modules-load.d/linuwu-sense.conf
  rm -f /etc/modprobe.d/blacklist-acer-wmi.conf
  rm -f /etc/udev/rules.d/01-nitro-keyboard.rules
  rm -f /var/log/AcerSenseDaemon.log

  systemctl daemon-reload >> "$LOG_FILE" 2>&1
  echo -e "${GREEN}Cleanup completed.${NC}"
}

install_dkms_driver() {
  CURRENT_DIR=$(pwd)
  log "${BLUE}Attempting to install linuwu-sense-dkms...${NC}"
  
  # 1. Detect Package Manager
  PKG_MANAGER=""
  if command -v apt-get &> /dev/null; then
    PKG_MANAGER="apt-get"
    INSTALL_CMD="apt-get install -y"
    HEADERS_PKG="linux-headers-$(uname -r)"
  elif command -v pacman &> /dev/null; then
    PKG_MANAGER="pacman"
    # Note: makepkg should not be run as root, but we are root. 
    # We will use 'sudo -u $TARGET_USER makepkg'
    INSTALL_CMD="pacman -S --noconfirm --needed"
    
    # Detect kernel flavor for Arch
    KERNEL_RELEASE=$(uname -r)
    if [[ "$KERNEL_RELEASE" == *"zen"* ]]; then
        HEADERS_PKG="linux-zen-headers"
    elif [[ "$KERNEL_RELEASE" == *"lts"* ]]; then
        HEADERS_PKG="linux-lts-headers"
    elif [[ "$KERNEL_RELEASE" == *"hardened"* ]]; then
        HEADERS_PKG="linux-hardened-headers"
    else
        HEADERS_PKG="linux-headers"
    fi
    log "Detected Arch Kernel: $KERNEL_RELEASE -> Required Headers: $HEADERS_PKG"
  elif command -v dnf &> /dev/null; then
    PKG_MANAGER="dnf"
    INSTALL_CMD="dnf install -y"
    HEADERS_PKG="kernel-devel"
  else
    log "${RED}Unsupported package manager. Please install drivers manually.${NC}"
    cd "$CURRENT_DIR"
    return 1
  fi

  # 2. Verify Target User for makepkg
  if [ "$TARGET_USER" == "root" ] || [ -z "$TARGET_USER" ]; then
      # Try to find the first normal user (UID 1000)
      TARGET_USER=$(id -nu 1000 2>/dev/null)
      if [ -z "$TARGET_USER" ]; then
          log "${RED}Error: Cannot determine non-root user for makepkg. Please run setup as a normal user with sudo.${NC}"
          cd "$CURRENT_DIR"
          return 1
      fi
  fi
  log "Building package as user: $TARGET_USER"

  log "${YELLOW}Installing dependencies (git, dkms, headers)...${NC}"
  # Run install command and log output
  if ! { $INSTALL_CMD git dkms $HEADERS_PKG build-essential || $INSTALL_CMD git dkms base-devel; } >> "$LOG_FILE" 2>&1; then
      log "${RED}Failed to install dependencies. Check log.${NC}"
      cd "$CURRENT_DIR"
      return 1
  fi

  # Clone Repo
  TEMP_DIR=$(mktemp -d)
  # Ensure the target user can read this dir
  chmod 777 "$TEMP_DIR"
  log "Cloning repository to $TEMP_DIR..."
  if ! sudo -u "$TARGET_USER" git clone https://github.com/ZauJulio/linuwu-sense-dkms.git "$TEMP_DIR" >> "$LOG_FILE" 2>&1; then
      log "${RED}Failed to clone repository.${NC}"
      rm -rf "$TEMP_DIR"
      cd "$CURRENT_DIR"
      return 1
  fi
  
  cd "$TEMP_DIR"
  
  if [ "$PKG_MANAGER" == "pacman" ]; then
    log "${YELLOW}Installing Arch dependencies and building package with makepkg...${NC}"
    
    # Fix permissions for the build user
    chown -R "$TARGET_USER" .
    
    # Run makepkg as the normal user (makepkg forbids root)
    if ! sudo -u "$TARGET_USER" makepkg -si --noconfirm >> "$LOG_FILE" 2>&1; then
        log "${RED}makepkg failed. Check $LOG_FILE for details.${NC}"
        rm -rf "$TEMP_DIR"
        cd "$CURRENT_DIR"
        return 1
    fi
    RESULT=0
  else
    # Non-Arch (Manual DKMS)
    log "${YELLOW}Installing dependencies (git, dkms, headers)...${NC}"
    # $INSTALL_CMD already ran above
    
    if [ -f "install.sh" ]; then
      log "Found install.sh, executing..."
      chmod +x install.sh
      if ! ./install.sh >> "$LOG_FILE" 2>&1; then
          log "${RED}install.sh failed. Check log.${NC}"
          rm -rf "$TEMP_DIR"
          cd "$CURRENT_DIR"
          return 1
      fi
      RESULT=0
    else
      # Fallback manual DKMS install
      log "No install script found. Attempting manual DKMS install..."
      # Assuming dkms.conf is present
      if [ -f "dkms.conf" ]; then
          MODULE_NAME="linuwu-sense"
          MODULE_VERSION=$(grep "^PACKAGE_VERSION" dkms.conf | cut -d"=" -f2 | tr -d '"')
          
          TARGET_SRC="/usr/src/${MODULE_NAME}-${MODULE_VERSION}"
          
          # Clean up existing source if present
          if [ -d "$TARGET_SRC" ]; then
              log "Removing existing source at $TARGET_SRC..."
              rm -rf "$TARGET_SRC"
          fi
          
          log "Copying source to $TARGET_SRC..."
          cp -r . "$TARGET_SRC"
          
          log "Adding DKMS module..."
          dkms add -m "$MODULE_NAME" -v "$MODULE_VERSION" >> "$LOG_FILE" 2>&1
          
          log "Building DKMS module..."
          if ! dkms build -m "$MODULE_NAME" -v "$MODULE_VERSION" >> "$LOG_FILE" 2>&1; then
               log "${RED}DKMS Build failed. Check $LOG_FILE for details.${NC}"
               # Try to remove if failed
               dkms remove -m "$MODULE_NAME" -v "$MODULE_VERSION" --all >> "$LOG_FILE" 2>&1
               rm -rf "$TEMP_DIR"
               cd "$CURRENT_DIR"
               return 1
          fi
          
          log "Installing DKMS module..."
          if ! dkms install -m "$MODULE_NAME" -v "$MODULE_VERSION" >> "$LOG_FILE" 2>&1; then
               log "${RED}DKMS Install failed. Check log.${NC}"
               rm -rf "$TEMP_DIR"
               cd "$CURRENT_DIR"
               return 1
          fi
          RESULT=0
      else
          log "${RED}Error: Invalid driver repository structure (no dkms.conf).${NC}"
          RESULT=1
      fi
    fi
  fi
  
  rm -rf "$TEMP_DIR"
  
  if [ $RESULT -eq 0 ]; then
    log "${GREEN}Driver installed successfully!${NC}"
    
    # Blacklist acer-wmi to prevent conflict
    if [ ! -f /etc/modprobe.d/blacklist-acer-wmi.conf ]; then
        echo "blacklist acer-wmi" > /etc/modprobe.d/blacklist-acer-wmi.conf
        log "Blacklisted acer-wmi to prevent conflicts."
    fi

    # Unload acer-wmi if loaded
    rmmod acer_wmi 2>/dev/null

    # Ensure module loads on boot
    echo "linuwu_sense" > /etc/modules-load.d/linuwu-sense.conf
    log "Configured linuwu_sense to load on boot."

    modprobe linuwu_sense >> "$LOG_FILE" 2>&1
    cd "$CURRENT_DIR"
    return 0
  else
    log "${RED}Driver installation failed.${NC}"
    cd "$CURRENT_DIR"
    return 1
  fi
}

check_drivers() {
  log "${YELLOW}Checking for linuwu-sense kernel module...${NC}"
  
  if modinfo linuwu_sense &> /dev/null; then
    log "${GREEN}Driver found!${NC}"
    
    # Check if managed by DKMS and INSTALLED
    DKMS_STATUS=$(dkms status 2>/dev/null | grep "linuwu-sense")
    
    if [[ -z "$DKMS_STATUS" ]] || [[ "$DKMS_STATUS" != *"installed"* ]]; then
        if [[ -z "$DKMS_STATUS" ]]; then
            echo -e "${YELLOW}Warning: Driver is installed manually (Not DKMS).${NC}"
        else
            echo -e "${RED}Warning: Driver is in DKMS but NOT INSTALLED (Build failed?).${NC}"
        fi
        
        echo -e "This means it will stop working after a kernel update."
        echo -e "Would you like to switch to/fix the DKMS version? (Recommended)"
        read -p "Fix/Switch to DKMS? [Y/n]: " choice
        case "${choice:-Y}" in
            y|Y )
                log "Removing existing driver installation..."
                rmmod linuwu_sense 2>/dev/null
                
                # Try to find and remove the module file
                MODULE_PATH=$(modinfo -n linuwu_sense 2>/dev/null)
                if [ -f "$MODULE_PATH" ]; then
                    rm -f "$MODULE_PATH"
                    log "Removed $MODULE_PATH"
                fi
                
                # Clean up broken DKMS entry if exists
                if [[ -n "$DKMS_STATUS" ]]; then
                    dkms remove linuwu-sense/1.0.0 --all 2>/dev/null
                fi
                
                depmod -a
                
                install_dkms_driver
                return $?
                ;;
            * )
                log "Keeping current driver state."
                return 0
                ;;
        esac
    else
        log "${GREEN}Driver is correctly installed and managed by DKMS.${NC}"
    fi

    # Ensure module is loaded
    if ! lsmod | grep -q "linuwu_sense"; then
        log "Loading module..."
        modprobe linuwu_sense >> "$LOG_FILE" 2>&1
    fi
    return 0
  else
    log "${RED}Error: linuwu-sense driver not found!${NC}"
    echo -e "This application requires the linuwu-sense kernel module."
    echo -e "Would you like to automatically install the DKMS version from GitHub?"
    
    read -p "Install Driver? [Y/n]: " choice
    case "${choice:-Y}" in 
      y|Y ) 
        install_dkms_driver
        return $?
        ;;
      * ) 
        log "${YELLOW}Skipping driver installation.${NC}"
        return 1 
        ;;
    esac
  fi
}

install_daemon() {
  echo -e "${YELLOW}Installing AcerSense-Daemon...${NC}"
  if [ ! -d "AcerSense-Daemon" ]; then
    echo -e "${RED}Error: AcerSense-Daemon directory not found!${NC}"
    return 1
  fi

  # Create installation directory
  mkdir -p ${INSTALL_DIR}/daemon

  # Copy daemon binary
  cp -f AcerSense-Daemon/AcerSense-Daemon ${INSTALL_DIR}/daemon/
  chmod 755 ${INSTALL_DIR}/daemon/AcerSense-Daemon

  # Config directory (Preserve existing config if possible, or create default)
  mkdir -p /etc/AcerSenseDaemon
  if [ ! -f /etc/AcerSenseDaemon/config.ini ]; then
      echo "[General]" > /etc/AcerSenseDaemon/config.ini
      echo "LogLevel = INFO" >> /etc/AcerSenseDaemon/config.ini
      echo "AutoDetectFeatures = True" >> /etc/AcerSenseDaemon/config.ini
      echo "HyprlandIntegration = False" >> /etc/AcerSenseDaemon/config.ini
      echo "DefaultAcProfile = balanced" >> /etc/AcerSenseDaemon/config.ini
      echo "DefaultBatProfile = low-power" >> /etc/AcerSenseDaemon/config.ini
  fi

  cat > ${SYSTEMD_DIR}/${DAEMON_SERVICE_NAME} << EOL
[Unit]
Description=AcerSense Daemon for Acer laptops
After=network.target

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/daemon/AcerSense-Daemon
Restart=on-failure
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOL

  # Udev rule for input devices (Helpful for non-root access if needed later)
  cat > /etc/udev/rules.d/01-nitro-keyboard.rules << EOL
SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="*keyboard*|*Keyboard*", MODE="0660", GROUP="input"
EOL
  
  # Reload udev rules
  udevadm control --reload-rules
  udevadm trigger

  systemctl daemon-reload >> "$LOG_FILE" 2>&1
  systemctl enable ${DAEMON_SERVICE_NAME} >> "$LOG_FILE" 2>&1
  systemctl start ${DAEMON_SERVICE_NAME} >> "$LOG_FILE" 2>&1

  if systemctl is-active --quiet ${DAEMON_SERVICE_NAME}; then
    echo -e "${GREEN}Daemon installed and started!${NC}"
    return 0
  else
    echo -e "${RED}Warning: Service failed to start. Check logs.${NC}"
    return 1
  fi
}

install_gui() {
  echo -e "${YELLOW}Installing AcerSense-GUI...${NC}"
  if [ ! -d "AcerSense-GUI" ]; then
    echo -e "${RED}Error: AcerSense-GUI directory not found!${NC}"
    return 1
  fi

  mkdir -p ${INSTALL_DIR}/gui
  cp -rf AcerSense-GUI/* ${INSTALL_DIR}/gui/
  chmod 755 ${INSTALL_DIR}/gui/AcerSense

  mkdir -p ${ICON_DIR}
  cp -f AcerSense-GUI/icon.png ${ICON_DIR}/acersense.png

  cat > ${DESKTOP_FILE_DIR}/acersense.desktop << EOL
[Desktop Entry]
Name=AcerSense
Comment=Acer Laptop Control Center
Exec=${INSTALL_DIR}/gui/AcerSense
Icon=acersense
Terminal=false
Type=Application
Categories=Utility;System;
Keywords=acer;laptop;system;control;fan;rgb;
EOL
  chmod 644 ${DESKTOP_FILE_DIR}/acersense.desktop

  cat > ${BIN_DIR}/acersense << EOL
#!/bin/bash
${INSTALL_DIR}/gui/AcerSense "\$@"
EOL
  chmod +x ${BIN_DIR}/acersense

  echo -e "${GREEN}GUI installed successfully!${NC}"
  return 0
}

perform_install() {
  local check_driver=$1
  local is_update=$2

  if [ "$is_update" = true ]; then
    comprehensive_cleanup
  else
    cleanup_legacy_installation
  fi

  mkdir -p ${INSTALL_DIR}

  if [ "$check_driver" = true ]; then
    if ! check_drivers; then
        echo -e "${RED}Installation Aborted.${NC}"
        return 1
    fi
  fi

  install_daemon
  DAEMON_RESULT=$?

  install_gui
  GUI_RESULT=$?

  if [ $DAEMON_RESULT -eq 0 ] && [ $GUI_RESULT -eq 0 ]; then
    chmod -R 755 "${INSTALL_DIR}"
    chmod 755 "${BIN_DIR}/acersense"
    echo -e "${GREEN}AcerSense installation completed!${NC}"
    echo -e "Run using command: ${BLUE}acersense${NC}"
    pause
    return 0
  else
    echo -e "${RED}Installation failed.${NC}"
    pause
    return 1
  fi
}

stop_all_processes() {
  log "${YELLOW}Stopping all AcerSense services and processes...${NC}"
  
  # 1. Stop Systemd Service
  if systemctl is-active --quiet ${DAEMON_SERVICE_NAME}; then
      systemctl stop ${DAEMON_SERVICE_NAME} >> "$LOG_FILE" 2>&1
      log "Stopped systemd service."
  fi

  # 2. Kill GUI Process (User Mode)
  # Trying to kill any process named "AcerSense" (The GUI binary)
  if pgrep -f "AcerSense" > /dev/null; then
      log "Killing running GUI instances..."
      pkill -f "AcerSense" || true
      sleep 1
  fi

  # 3. Force Kill Daemon (If stuck)
  if pgrep -f "AcerSense-Daemon" > /dev/null; then
      log "Force killing daemon process..."
      pkill -f "AcerSense-Daemon" || true
  fi
}

check_and_update_driver() {
  log "${BLUE}Checking for driver updates...${NC}"
  
  # 1. Check if DKMS is even installed/used
  if ! command -v dkms &> /dev/null; then
      log "${YELLOW}DKMS not found. Skipping auto-update check (Manual install detected).${NC}"
      return 0
  fi

  # 2. Get Current Version
  # Fix: Parse the module version, not the kernel version
  # Format: linuwu-sense/1.0.0, 6.18.6-zen1-1-zen, x86_64: installed
  CURRENT_VER=$(dkms status linuwu-sense | head -n 1 | cut -d'/' -f2 | cut -d',' -f1 | tr -d ' ')
  
  if [ -z "$CURRENT_VER" ]; then
      log "${YELLOW}Driver not installed via DKMS. Installing latest...${NC}"
      install_dkms_driver
      return $?
  fi
  
  log "Current Installed Version: $CURRENT_VER"

  # 3. Get Remote Version (Clone config only to save bandwidth/time if possible, but full clone is safer/easier)
  TEMP_CHECK_DIR=$(mktemp -d)
  
  # We need git to check
  if ! command -v git &> /dev/null; then
      log "${RED}Git not found. Cannot check for updates.${NC}"
      rm -rf "$TEMP_CHECK_DIR"
      return 0
  fi

  # Clone depth 1 for speed
  if ! git clone --depth 1 https://github.com/ZauJulio/linuwu-sense-dkms.git "$TEMP_CHECK_DIR" > /dev/null 2>&1; then
      log "${RED}Failed to check for updates (Internet/Git error). Skipping driver update.${NC}"
      rm -rf "$TEMP_CHECK_DIR"
      return 0
  fi

  if [ -f "$TEMP_CHECK_DIR/dkms.conf" ]; then
      REMOTE_VER=$(grep "^PACKAGE_VERSION" "$TEMP_CHECK_DIR/dkms.conf" | cut -d"=" -f2 | tr -d '"')
      log "Latest Available Version: $REMOTE_VER"
      
      if [ "$CURRENT_VER" != "$REMOTE_VER" ]; then
          echo -e "${GREEN}New driver version found! ($CURRENT_VER -> $REMOTE_VER)${NC}"
          log "Updating driver..."
          
          # We can reuse the cloned dir or just call the standard install function.
          # Calling standard function ensures consistency with dependencies/permissions.
          install_dkms_driver
          RESULT=$?
      else
          log "${GREEN}Driver is up to date.${NC}"
          RESULT=0
      fi
  else
      log "${RED}Remote repo invalid (no dkms.conf). Skipping.${NC}"
      RESULT=1
  fi

  rm -rf "$TEMP_CHECK_DIR"
  return $RESULT
}

perform_update() {
  log "${BLUE}Starting Update Procedure...${NC}"
  
  # 1. Stop Everything
  stop_all_processes

  # 2. Backup Configuration (Just in case, though install_daemon respects existence)
  if [ -d "/etc/AcerSenseDaemon" ]; then
      log "Backing up configuration..."
      cp -r /etc/AcerSenseDaemon /tmp/acersense_config_backup
  fi

  # 3. Check and Update Drivers
  check_and_update_driver
  if [ $? -ne 0 ]; then
      echo -e "${YELLOW}Driver update had issues, but proceeding with application update...${NC}"
  fi

  # 4. Remove binaries only (Clean state for code, keep config)
  rm -f ${BIN_DIR}/acersense
  rm -rf ${INSTALL_DIR}/gui
  rm -rf ${INSTALL_DIR}/daemon
  # Do NOT remove /etc/AcerSenseDaemon here

  # 5. Install New Components
  install_daemon
  DAEMON_RESULT=$?

  install_gui
  GUI_RESULT=$?

  # 6. Restore Config if needed (If install_daemon somehow wiped it, unlikely but safe)
  if [ ! -f "/etc/AcerSenseDaemon/config.ini" ] && [ -d "/tmp/acersense_config_backup" ]; then
      log "Restoring configuration from backup..."
      cp -r /tmp/acersense_config_backup/* /etc/AcerSenseDaemon/
  fi
  rm -rf /tmp/acersense_config_backup

  if [ $DAEMON_RESULT -eq 0 ] && [ $GUI_RESULT -eq 0 ]; then
    chmod -R 755 "${INSTALL_DIR}"
    chmod 755 "${BIN_DIR}/acersense"
    
    # Restart Service
    systemctl daemon-reload
    systemctl restart ${DAEMON_SERVICE_NAME}
    
    echo -e "${GREEN}AcerSense updated successfully!${NC}"
    echo -e "Your configuration has been preserved."
    pause
    return 0
  else
    echo -e "${RED}Update failed.${NC}"
    pause
    return 1
  fi
}

uninstall() {
  comprehensive_cleanup
  echo -e "${GREEN}Uninstalled successfully.${NC}"
  pause
}

check_system() {
  if ! command -v systemctl &> /dev/null; then
    echo -e "${RED}Error: systemd required.${NC}"
    return 1
  fi
  return 0
}

main_menu() {
  if ! check_system; then exit 1; fi

  while true; do
    print_banner
    echo -e "1) Install AcerSense"
    echo -e "2) Install AcerSense (Skip Driver Check)"
    echo -e "3) Uninstall"
    echo -e "4) Update/Reinstall (Preserves Config)"
    echo -e "q) Quit"
    echo ""
    read -p "Select [1-4, q]: " choice

    case $choice in
      1) perform_install true false ;;
      2) perform_install false false ;;
      3) uninstall ;;
      4) perform_update ;;
      q|Q) exit 0 ;;
      *) echo "Invalid option." ;;
    esac
  done
}

check_root "$@"

# Initialize Log (After root check)
echo "--- AcerSense Installer Started: $(date) ---" > "$LOG_FILE"
chmod 666 "$LOG_FILE"

main_menu
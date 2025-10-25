#!/bin/bash

# Acer Sense Installer Script
# This script installs, uninstalls, or updates the Acer Sense
# Components: Linuwu-Sense (drivers), Daemon, and AcerSense GUI

# Constants
SCRIPT_VERSION="1.0.0"
INSTALL_DIR="/opt/acersense"
BIN_DIR="/usr/local/bin"
SYSTEMD_DIR="/etc/systemd/system"
DAEMON_SERVICE_NAME="acersense-daemon.service"
DESKTOP_FILE_DIR="/usr/share/applications"
ICON_DIR="/usr/share/icons/hicolor/256x256/apps"

# Legacy paths for cleanup (uppercase naming convention)
LEGACY_INSTALL_DIR="/opt/ACERSENSE"
LEGACY_DAEMON_SERVICE_NAME="ACERSENSE-Daemon.service"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to pause script execution
pause() {
  echo -e "${BLUE}Press any key to continue...${NC}"
  read -n 1 -s -r
}

# Function to check and elevate privileges
check_root() {
  if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}This script requires root privileges.${NC}"

    # Check if sudo is available
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
  echo -e "${BLUE}       AcerSense Installer v${SCRIPT_VERSION}        ${NC}"
  echo -e "${BLUE}    Acer Laptop WMI Controls for Linux  ${NC}"
  echo -e "${BLUE}==========================================${NC}"
  echo ""
}

# Function to detect and clean up legacy installations
cleanup_legacy_installation() {
  echo -e "${YELLOW}Checking for legacy installations...${NC}"
  local cleanup_performed=false

  # Check for legacy service file (uppercase naming)
  if [ -f "${SYSTEMD_DIR}/${LEGACY_DAEMON_SERVICE_NAME}" ]; then
    echo -e "${BLUE}Found legacy service file: ${LEGACY_DAEMON_SERVICE_NAME}${NC}"

    # Stop the legacy service if it's running
    if systemctl is-active --quiet ${LEGACY_DAEMON_SERVICE_NAME} 2>/dev/null; then
      echo "Stopping legacy service..."
      systemctl stop ${LEGACY_DAEMON_SERVICE_NAME}
    fi

    # Disable the legacy service if it's enabled
    if systemctl is-enabled --quiet ${LEGACY_DAEMON_SERVICE_NAME} 2>/dev/null; then
      echo "Disabling legacy service..."
      systemctl disable ${LEGACY_DAEMON_SERVICE_NAME}
    fi

    # Remove the legacy service file
    echo "Removing legacy service file..."
    rm -f "${SYSTEMD_DIR}/${LEGACY_DAEMON_SERVICE_NAME}"
    cleanup_performed=true
  fi

  # Check for legacy installation directory (uppercase naming)
  if [ -d "${LEGACY_INSTALL_DIR}" ]; then
    echo -e "${BLUE}Found legacy installation directory: ${LEGACY_INSTALL_DIR}${NC}"
    echo "Removing legacy installation directory..."
    rm -rf "${LEGACY_INSTALL_DIR}"
    cleanup_performed=true
  fi

  # Check for other potential legacy artifacts
  local legacy_artifacts=(
    "/usr/local/bin/AcerSense-Daemon"
    "/usr/share/applications/AcerSense.desktop"
    "/usr/share/icons/hicolor/256x256/apps/AcerSense.png"
  )

  for artifact in "${legacy_artifacts[@]}"; do
    if [ -f "$artifact" ] || [ -d "$artifact" ]; then
      echo "Removing legacy artifact: $artifact"
      rm -rf "$artifact"
      cleanup_performed=true
    fi
  done

  # Reload systemd daemon if any service changes were made
  if [ "$cleanup_performed" = true ]; then
    echo "Reloading systemd daemon configuration..."
    systemctl daemon-reload
    echo -e "${GREEN}Legacy installation cleanup completed.${NC}"
  else
    echo -e "${GREEN}No legacy installations found.${NC}"
  fi

  return 0
}

# Function to perform comprehensive cleanup for uninstall/reinstall
comprehensive_cleanup() {
  echo -e "${YELLOW}Performing comprehensive cleanup...${NC}"

  # Stop and disable current daemon service
  if systemctl is-active --quiet ${DAEMON_SERVICE_NAME} 2>/dev/null; then
    echo "Stopping current Daemon service..."
    systemctl stop ${DAEMON_SERVICE_NAME}
  fi

  if systemctl is-enabled --quiet ${DAEMON_SERVICE_NAME} 2>/dev/null; then
    echo "Disabling current Daemon service..."
    systemctl disable ${DAEMON_SERVICE_NAME}
  fi

  # Remove current service file
  if [ -f "${SYSTEMD_DIR}/${DAEMON_SERVICE_NAME}" ]; then
    echo "Removing current service file..."
    rm -f "${SYSTEMD_DIR}/${DAEMON_SERVICE_NAME}"
  fi

  # Clean up legacy installations
  cleanup_legacy_installation

  # Remove current installed files
  echo "Removing current installation files..."
  rm -rf ${INSTALL_DIR}
  rm -f ${BIN_DIR}/AcerSense
  rm -f ${DESKTOP_FILE_DIR}/acersense.desktop
  rm -f ${ICON_DIR}/acersense.png

  # Uninstall drivers if Linuwu-Sense folder exists
  if [ -d "Linuwu-Sense" ]; then
    echo "Uninstalling drivers..."
    cd Linuwu-Sense
    if [ -f "Makefile" ]; then
      make uninstall 2>/dev/null || true
      make clean 2>/dev/null || true
    fi
    cd ..
  fi

  # Final systemd daemon reload
  systemctl daemon-reload

  echo -e "${GREEN}Comprehensive cleanup completed.${NC}"
  return 0
}

install_drivers() {
  echo -e "${YELLOW}Installing Linuwu-Sense drivers...${NC}"

  if [ ! -d "Linuwu-Sense" ]; then
    echo -e "${RED}Error: Linuwu-Sense directory not found!${NC}"
    echo "Please make sure the script is run from the same directory containing Linuwu-Sense folder."
    pause
    return 1
  fi

  cd Linuwu-Sense

  # Check if make is installed
  if ! command -v make &> /dev/null; then
    echo -e "${YELLOW}Installing build tools...${NC}"
    apt-get update && apt-get install -y build-essential
  fi

  # Build and install drivers
  make clean
  make
  make install

  if [ $? -eq 0 ]; then
    echo -e "${GREEN}Linuwu-Sense drivers installed successfully!${NC}"
    cd ..
    return 0
  else
    echo -e "${RED}Error: Failed to install Linuwu-Sense drivers${NC}"
    cd ..
    pause
    return 1
  fi
}

install_daemon() {
  echo -e "${YELLOW}Installing Daemon...${NC}"

  if [ ! -d "Daemon" ]; then
    echo -e "${RED}Error: Daemon directory not found!${NC}"
    echo "Please make sure the script is run from the same directory containing Daemon folder."
    pause
    return 1
  fi

  # Create installation directory
  mkdir -p ${INSTALL_DIR}/daemon

  # Copy daemon binary
  cp -f Daemon/AcerSense-Daemon ${INSTALL_DIR}/daemon/
  chmod +x ${INSTALL_DIR}/daemon/AcerSense-Daemon

  # Create systemd service file with improved configuration
  cat > ${SYSTEMD_DIR}/${DAEMON_SERVICE_NAME} << EOL
[Unit]
Description=Daemon for Acer laptops
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

  # Enable and start the service
  systemctl daemon-reload
  systemctl enable ${DAEMON_SERVICE_NAME}
  systemctl start ${DAEMON_SERVICE_NAME}

  # Verify service is running
  if systemctl is-active --quiet ${DAEMON_SERVICE_NAME}; then
    echo -e "${GREEN}Daemon installed and service started successfully!${NC}"
    return 0
  else
    echo -e "${RED}Warning: Daemon service may not have started correctly. Check with 'systemctl status ${DAEMON_SERVICE_NAME}'${NC}"
    return 1
  fi
}

install_gui() {
  echo -e "${YELLOW}Installing AcerSense...${NC}"

  if [ ! -d "AcerSense" ]; then
    echo -e "${RED}Error: AcerSense directory not found!${NC}"
    echo "Please make sure the script is run from the same directory containing AcerSense folder."
    pause
    return 1
  fi

  # Create installation directory
  mkdir -p ${INSTALL_DIR}/gui

  # Copy GUI files
  cp -rf AcerSense/* ${INSTALL_DIR}/gui/
  chmod +x ${INSTALL_DIR}/gui/AcerSense

  # Create icon directory if it doesn't exist
  mkdir -p ${ICON_DIR}

  # Copy icon
  cp -f AcerSense/icon.png ${ICON_DIR}/acersense.png

  # Create desktop entry
  cat > ${DESKTOP_FILE_DIR}/acersense.desktop << EOL
[Desktop Entry]
Name=AcerSense
Comment=Acer Laptop Control Center. An alternative to PredatorSense/NitroSense for Acer laptops on Linux.
Exec=${INSTALL_DIR}/gui/AcerSense
Icon=acersense
Terminal=false
Type=Application
Categories=Utility;System;
Keywords=acer;laptop;system;
EOL

  # Create command shortcut
  cat > ${BIN_DIR}/ACERSENSE << EOL
#!/bin/bash
${INSTALL_DIR}/gui/AcerSense "\$@"
EOL
  chmod +x ${BIN_DIR}/AcerSense

  echo -e "${GREEN}AcerSense installed successfully!${NC}"
  return 0
}

perform_install() {
  local skip_drivers=$1
  local is_update=$2

  # If this is an update/reinstall, perform cleanup first
  if [ "$is_update" = true ]; then
    echo -e "${BLUE}Performing cleanup before installation...${NC}"
    comprehensive_cleanup
    echo ""
  else
    # For fresh installs, still check for legacy installations
    cleanup_legacy_installation
    echo ""
  fi

  # Create main installation directory
  mkdir -p ${INSTALL_DIR}

  # Install components
  if [ "$skip_drivers" = false ]; then
    install_drivers
    DRIVER_RESULT=$?
  else
    echo -e "${YELLOW}Skipping driver installation as requested.${NC}"
    DRIVER_RESULT=0
  fi

  install_daemon
  DAEMON_RESULT=$?

  install_gui
  GUI_RESULT=$?

  # Check if all installations were successful
  if [ $DRIVER_RESULT -eq 0 ] && [ $DAEMON_RESULT -eq 0 ] && [ $GUI_RESULT -eq 0 ]; then
    echo -e "${GREEN}AcerSense installation completed successfully!${NC}"
    echo -e "${YELLOW}Please reboot your system to ensure all components are properly initialized.${NC}"

    # Show service status
    echo ""
    echo -e "${BLUE}Service Status:${NC}"
    systemctl status ${DAEMON_SERVICE_NAME} --no-pager -l
    pause
    return 0
  else
    echo -e "${RED}Some components failed to install. Please check the errors above.${NC}"
    pause
    return 1
  fi
}

uninstall() {
  echo -e "${YELLOW}Uninstalling AcerSense...${NC}"
  comprehensive_cleanup
  echo -e "${GREEN}AcerSense uninstalled successfully!${NC}"
  pause
  return 0
}

# Function to check system compatibility
check_system() {
  echo -e "${BLUE}Checking system compatibility...${NC}"

  # Check if systemd is available
  if ! command -v systemctl &> /dev/null; then
    echo -e "${RED}Error: systemd is required but not found on this system.${NC}"
    return 1
  fi

  # Check if we're on a supported distribution
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "Detected OS: $PRETTY_NAME"
  fi

  echo -e "${GREEN}System compatibility check passed.${NC}"
  return 0
}

main_menu() {
  # Perform initial system check
  if ! check_system; then
    echo -e "${RED}System compatibility check failed. Exiting.${NC}"
    pause
    exit 1
  fi

  while true; do
    print_banner

    echo -e "Please select an option:"
    echo -e "  ${GREEN}1${NC}) Install AcerSense"
    echo -e "  ${GREEN}2${NC}) Install AcerSense (without drivers)"
    echo -e "  ${GREEN}3${NC}) Uninstall AcerSense"
    echo -e "  ${GREEN}4${NC}) Reinstall/Update AcerSense"
    echo -e "  ${GREEN}5${NC}) Check service status"
    echo -e "  ${GREEN}q${NC}) Quit"
    echo ""

    read -p "Enter your choice [1-5 or q]: " choice

    case $choice in
      1)
        print_banner
        echo -e "${BLUE}Starting complete installation...${NC}"
        perform_install false false
        ;;
      2)
        print_banner
        echo -e "${BLUE}Starting installation without drivers...${NC}"
        perform_install true false
        ;;
      3)
        print_banner
        echo -e "${BLUE}Starting uninstallation...${NC}"
        uninstall
        ;;
      4)
        print_banner
        echo -e "${BLUE}Starting reinstallation/update...${NC}"
        echo -e "${YELLOW}This will completely remove the existing installation before installing the new version.${NC}"
        perform_install false true
        ;;
      5)
        print_banner
        echo -e "${BLUE}Checking service status...${NC}"
        echo ""
        if systemctl list-unit-files | grep -q ${DAEMON_SERVICE_NAME}; then
          systemctl status ${DAEMON_SERVICE_NAME} --no-pager -l
        else
          echo -e "${YELLOW}AcerSense service not found. The suite may not be installed.${NC}"
        fi
        echo ""
        pause
        ;;
      q|Q)
        echo -e "${BLUE}Exiting installer. Goodbye!${NC}"
        exit 0
        ;;
      *)
        echo -e "${RED}Invalid option. Please try again.${NC}"
        sleep 2
        ;;
    esac
  done
}

# Check and elevate privileges if needed
check_root "$@"

# Start the installer
main_menu
exit 0

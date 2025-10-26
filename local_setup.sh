#!/bin/bash

# Local setup script for DAMX/AcerSense
# This script checks for a pre-built package, builds one if it doesn't exist,
# and then runs the main installer.

# Stop on any error
set -e

# --- Configuration ---
PUBLISH_DIR="Publish"
BUILD_SCRIPT="./build_release.py"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- Main Logic ---
echo -e "${BLUE}=== Local DAMX/AcerSense Installer ===${NC}"

RELEASE_DIR=""

# 1. Find existing release package
echo "Searching for an existing release package in '${PUBLISH_DIR}/'..."
if [ -d "$PUBLISH_DIR" ]; then
  # Find the first subdirectory in Publish/
  RELEASE_DIR=$(find "$PUBLISH_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)
fi

# 2. Build if package not found
if [ -z "$RELEASE_DIR" ]; then
  echo -e "${YELLOW}No release package found.${NC}"
  if [ ! -f "$BUILD_SCRIPT" ]; then
    echo -e "${RED}Error: Build script '$BUILD_SCRIPT' not found. Cannot build package.${NC}"
    exit 1
  fi
  echo -e "${BLUE}Running build script to create a new package...${NC}"
  
  # Make sure build script is executable
  chmod +x "$BUILD_SCRIPT"
  
  # Run the build script
  ./"$BUILD_SCRIPT"

  # Re-check for the release directory after building
  echo "Searching for newly built package..."
  RELEASE_DIR=$(find "$PUBLISH_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)

  if [ -z "$RELEASE_DIR" ]; then
    echo -e "${RED}Error: Build completed, but no release package was found in '$PUBLISH_DIR'.${NC}"
    exit 1
  fi
else
  echo -e "${GREEN}Found existing package: $RELEASE_DIR${NC}"
fi

# 3. Run the installer from the package
SETUP_SCRIPT_PATH="$RELEASE_DIR/setup.sh"
if [ ! -f "$SETUP_SCRIPT_PATH" ]; then
  echo -e "${RED}Error: setup.sh not found inside '$RELEASE_DIR'. The package is incomplete.${NC}"
  exit 1
fi

echo -e "\n${BLUE}Changing to '$RELEASE_DIR' and executing setup.sh...${NC}"
cd "$RELEASE_DIR"

# The setup.sh script should handle its own sudo elevation.
# Pass all arguments from this script to the setup script.
./setup.sh "$@"

echo -e "\n${GREEN}Local setup process finished.${NC}"
exit 0

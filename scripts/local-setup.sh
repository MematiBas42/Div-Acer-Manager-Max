#!/bin/bash

# Local setup script for AcerSense
# This script builds the package locally and installs it.

# Stop on any error
set -e

# --- Configuration ---
# Navigate to project root
cd "$(dirname "$0")/.."
PUBLISH_DIR="Publish"
BUILD_SCRIPT="./build_release.py"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- Main Logic ---
echo -e "${BLUE}=== Local AcerSense Installer ===${NC}"

# Check for build script
if [ ! -f "$BUILD_SCRIPT" ]; then
  echo -e "${RED}Error: Build script '$BUILD_SCRIPT' not found. Cannot build package.${NC}"
  exit 1
fi

echo -e "${BLUE}Building release package...${NC}"

# Make sure build script is executable
chmod +x "$BUILD_SCRIPT"

# Run the build script
./"$BUILD_SCRIPT"

# Find the newly built package
RELEASE_DIR=$(find "$PUBLISH_DIR" -mindepth 1 -maxdepth 1 -type d | grep "AcerSense-Release" | head -n 1)

if [ -z "$RELEASE_DIR" ]; then
  echo -e "${RED}Error: Build completed, but no release package was found in '$PUBLISH_DIR'.${NC}"
  exit 1
fi

echo -e "${GREEN}Built package found: $RELEASE_DIR${NC}"

# Run the installer from the package
SETUP_SCRIPT_PATH="$RELEASE_DIR/setup.sh"
if [ ! -f "$SETUP_SCRIPT_PATH" ]; then
  echo -e "${RED}Error: setup.sh not found inside '$RELEASE_DIR'. The package is incomplete.${NC}"
  exit 1
fi

echo -e "\n${BLUE}Executing installer...${NC}"
cd "$RELEASE_DIR"

# Run setup script (it will request sudo if needed)
sudo ./setup.sh "$@"

echo -e "\n${GREEN}Local setup process finished.${NC}"
exit 0
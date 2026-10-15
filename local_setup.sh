#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "    AcerSense Suite Local Setup & Build Script    "
echo "=================================================="

# Run test suite and package
python3 build_release.py

if [ "$1" == "--install" ]; then
    echo "==> Kurulum başlatılıyor..."
    sudo bash dist/install.sh
else
    echo ""
    echo "Paketleme tamamlandı. Kurmak için:"
    echo "  sudo bash dist/install.sh"
    echo "veya:"
    echo "  ./local_setup.sh --install"
fi

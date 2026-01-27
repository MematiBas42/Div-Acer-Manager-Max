<p align="center">
  <img src="https://raw.githubusercontent.com/kleqing/AcerSense/refs/heads/main/AcerSense/icon.png" alt="icon" width="100" style="vertical-align: middle;">
</p>

<h1 align="center">
  AcerSense Max
</h1>

**AcerSense Max** is a high-performance, professional-grade Linux management suite for Acer laptops (Nitro & Predator series). It provides deep hardware-level control through a modern, asynchronous, and event-driven architecture. This project is a complete evolution of the original [DAMX](https://github.com/PXDiv/Div-Acer-Manager-Max) by PXDiv, optimized for modern Linux environments and desktop enthusiasts (especially Hyprland users).

![Application Screenshot](https://github.com/user-attachments/assets/d684c630-5b0a-482e-acea-0b3933987312)

<h4 align="center" style="font-style: italic">
  "The smartest and most efficient control center for Nitro and Predator laptops on Linux."
</h4>

---

## 🚀 Advanced Features (Max Edition)

### 🧠 Modern Event-Driven Architecture
- **Netlink Monitor:** Replaced inefficient polling with Kernel Netlink events. The system sleeps and wakes up instantly only when power sources change or hardware buttons (Fn+F) are pressed. **0% Idle CPU Usage.**
- **Asyncio Core:** The daemon is built on Python's `asyncio` for non-blocking IPC communication, allowing simultaneous updates to the GUI, Quickshell, and other clients.
- **Smart I/O Optimization:** Intelligent file-writing logic that skips redundant writes to `/sys` and `/proc` if values haven't changed, preserving SSD lifespan and reducing latency.

### 🔋 Power & Thermal Management
- **Dynamic Profile Sync:** Automatically switches between profiles (e.g., Quiet on Battery, Turbo on AC) based on customizable user preferences.
- **Deep System Optimizations:** Applies low-level tweaks including CPU EPP (Energy Performance Preference), WiFi Power Management, Turbo Boost toggles, and PCIe ASPM policies per profile.
- **NOS Mode:** A specialized "Nitro/Predator Overclocking System" that forces maximum cooling and performance with a single command/button.

### ❄️ Fan & Sensor Control
- **Real-Time Monitoring:** High-precision dashboard showing RPM, temperatures (multi-core average), and utilization metrics via `LiveCharts`.
- **Safety Clamping:** Manual fan control includes safety limits (20% minimum) to prevent fan stalling while allowing full 100% bursts.
- **Smooth Transition:** Intelligent initialization that waits for driver availability (`wait_for_file`) instead of using fixed delays.

### 🎨 Desktop & UI Integration
- **Hyprland Integration:** Automatically manages window opacity, blur, and shadows based on the current power state and thermal profile.
- **Modern Avalonia UI:** A clean, responsive XAML-based interface that dynamically hides unsupported features based on hardware detection.
- **Privacy & Logging Control:** A dedicated "Disable Logs" mode that silences all non-critical output and clears existing log files to save disk space and enhance privacy.

---

## ✨ Core Functionalities

- 🔋 **Profills:** Eco, Quiet, Balanced, Performance, Turbo.
- 🌡 **Fans:** Manual and Auto modes with real-time RPM feedback.
- 💡 **Settings:** LCD Override, Keyboard Backlight Timeout, Boot Sound/Animation toggles.
- 🎨 **RGB:** 4-zone keyboard lighting support with effect management (Static, Breathing, Wave, etc.).
- 🛠 **Internals Manager:** Advanced tools for forcing model detection (Nitro/Predator v4) and driver restarts.

---

## 🛠️ Installation

### Prerequisites
- `linuwu-sense` kernel driver (DKMS version recommended).
- `dotnet-sdk` (for building from source).
- `python` with `asyncio`.

### Local Setup
Clone the repository and run the automated build and install script:
```bash
./local_setup.sh
```
*This script will compile the GUI, prepare the daemon, set up systemd services, and configure necessary socket permissions.*

---

## 🧭 Compatibility & Credits

- **Compatibility:** Please refer to the [Compatibility List](Compatibility.md) for supported models. Note that this version supports newer Nitro V models and most Predator series laptops.
- **Linuwu Sense:** Special thanks to the [Linuwu Sense](https://github.com/0x7375646F/Linuwu-Sense) developers for the kernel-level access.
- **Original Author:** Built upon the foundations laid by [PXDiv (DAMX)](https://github.com/PXDiv/Div-Acer-Manager-Max).

---

## 📂 Troubleshooting & Logs

If you encounter issues like "UNKNOWN" laptop type or connection errors:
1. Check if the driver is loaded: `lsmod | grep linuwu_sense`
2. Review the logs:
   - **Daemon:** `/var/log/AcerSenseDaemon.log`
   - **GUI:** `/tmp/AcerSenseGUI.log`
3. Restart the service: `sudo systemctl restart acersense-daemon`

---
**License:** GNU General Public License v3.0  
*Contributions and testing on different Acer models are highly welcome!*

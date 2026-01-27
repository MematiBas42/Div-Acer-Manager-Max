<p align="center">
  <img src="https://raw.githubusercontent.com/kleqing/AcerSense/refs/heads/main/AcerSense/icon.png" alt="icon" width="100" style="vertical-align: middle;">
</p>

<h1 align="center">
  AcerSense Max
</h1>

**AcerSense Max** is a high-performance Linux management suite for Acer laptops (Nitro & Predator series). It provides deep hardware-level control through a modern, asynchronous, and event-driven architecture. This project is a complete evolution of the original [DAMX](https://github.com/PXDiv/Div-Acer-Manager-Max) by PXDiv, specifically optimized for enthusiasts using **Hyprland** and [end-4's dotfiles](https://github.com/end-4/dots-hyprland).

![Application Screenshot](https://github.com/user-attachments/assets/d684c630-5b0a-482e-acea-0b3933987312)

<h4 align="center" style="font-style: italic">
  "The smartest and most efficient control center for Nitro and Predator laptops on Linux."
</h4>

---

## 🚀 Key Improvements (Max Edition)

### 🧠 Modern Event-Driven Architecture
- **Netlink Monitor:** Replaced polling with Kernel Netlink events. The system wakes up instantly only when power sources change or physical buttons (Fn+F) are pressed. **0% Idle CPU Usage.**
- **Asyncio Core:** Python `asyncio` allows non-blocking IPC, supporting simultaneous updates across GUI, Quickshell, and CLI.
- **Smart I/O Optimization:** Intelligent logic that skips redundant writes to `/sys` and `/proc`, preserving SSD lifespan.

### 🔋 Advanced Power & Thermal Control
- **Dynamic Profile Sync:** Automatically switches profiles (e.g., *Quiet* on Battery, *Turbo* on AC) based on customizable user preferences.
- **Deep System Tweaks:** Manages CPU EPP (Energy Performance Preference), WiFi Power Management, Turbo Boost, and PCIe ASPM policies automatically.
- **NOS Mode:** A specialized "Nitro/Predator Overclocking System" that forces maximum cooling and performance with a single command/button.

### 🎨 Hyprland & Desktop Integration
- **Dynamic Visuals:** Automatically adjusts window opacity, blur, and shadows based on the current power state.
- **end-4 Dots Compatibility:** Fully compatible with [end-4's Hyprland dots](https://github.com/end-4/dots-hyprland). Includes specialized scripts to integrate status indicators into the Quickshell bar.
- **Privacy Mode:** "Disable Logs" clears all log files and silences non-critical output for maximum privacy and disk efficiency.

---

## 🛠️ Feature Usage & Integration

### 1. Hyprland Integration
To enable automatic visual changes (Opacity/Blur):
1. Go to the **Misc** (or System Settings) tab in the GUI.
2. Toggle **Enable Hyprland Integration**.
3. Customize your desired opacity levels for both AC and Battery modes.
4. **Blur Control:** Edit `~/.config/hypr/acersense_bat.conf` and `acersense_charge.conf` to customize specific effects.

### 2. end-4 Dots Support (Quickshell)
If you are using **end-4's Hyprland dotfiles**, you can add a real-time AcerSense indicator to your bar by running the repair script:
```bash
./scripts/post_update_fixqshell.sh
```
This will patch your Quickshell configuration and reload the bar instantly with dynamic icons.

### 3. Nitro Button (Special Key)
The physical Nitro key (N) is fully supported with long-press functionality:
- **Short Press:** Cycles through thermal profiles (Quiet -> Balanced -> Performance).
- **Long Press (>600ms):** Activates/Deactivates **NOS Mode** (Max fans + Peak performance).

---

## 📂 Scripts Directory Details

The `scripts/` directory contains essential tools for installation and desktop integration:

- **`local-setup.sh`**: The primary local installation script that builds the binaries and sets up system services.
- **`NitroButton.sh`**: A background service that listens for the physical Nitro key using `evtest`. It delegates actions to the long-press handler.
- **`long_press_handler.sh`**: Manages the logic for the Nitro key. It differentiates between short presses (cycle profiles) and long presses (NOS mode toggle).
- **`post_update_fixqshell.sh`**: A comprehensive integration script for [end-4's dotfiles](https://github.com/end-4/dots-hyprland). It sets up a Python event listener and patches Quickshell's QML files to show an AcerSense indicator on the status bar.
- **`setup_template.sh`**: The template used by the build system to generate the final installer script.

---

## 🛠️ Installation

### Prerequisites
- `linuwu-sense` kernel driver (DKMS recommended).
- `dotnet-sdk` (for building the GUI).
- `python` with `asyncio`.
- `evtest` and `socat` (for Nitro Button functionality).

### Local Setup
```bash
./local_setup.sh
```

---

## 🧭 Compatibility & Credits

- **Compatibility:** Supports newer Nitro V models and most Predator series. Check the [Compatibility List](Compatibility.md).
- **Linuwu Sense:** Special thanks to the [Linuwu Sense](https://github.com/0x7375646F/Linuwu-Sense) developers.
- **Original Author:** Built upon the foundations laid by [PXDiv (DAMX)](https://github.com/PXDiv/Div-Acer-Manager-Max).

---
**License:** GNU General Public License v3.0  
*Help test on different Acer laptop models and contribute!*

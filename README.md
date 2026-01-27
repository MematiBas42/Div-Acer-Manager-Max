<p align="center">
  <img src="https://raw.githubusercontent.com/kleqing/AcerSense/refs/heads/main/AcerSense/icon.png" alt="icon" width="100" style="vertical-align: middle;">
</p>

<h1 align="center">
  AcerSense Max
</h1>

**AcerSense Max** is a professional-grade Linux management suite for Acer laptops (Nitro & Predator series). It provides deep hardware-level control through a modern, asynchronous, and event-driven architecture. 

This project is a complete evolution of the original [DAMX](https://github.com/PXDiv/Div-Acer-Manager-Max) by PXDiv. It combines the aesthetic of NitroSense/PredatorSense with an optimized backend designed for extreme efficiency and modern Linux desktop environments (especially Hyprland).

![Application Screenshot](https://github.com/user-attachments/assets/d684c630-5b0a-482e-acea-0b3933987312)

<h4 align="center" style="font-style: italic">
  "The smartest and most efficient control center for Nitro and Predator laptops on Linux."
</h4>

---

## ❓ Why this Rework?

Many Acer Linux users find that standard drivers or tools don't fully support their specific Nitro or Predator models. This version was inspired by the need for a tool that just *works* out of the box while looking as good as the official Windows software. By building on the [linuwu_sense](https://github.com/0x7375646F/Linuwu-Sense) driver, we've enabled features that were previously inaccessible on Linux, such as proper thermal profiles and per-zone RGB control.

---

## 🚀 Max Edition Improvements

### 🧠 Modern Event-Driven Architecture
- **Netlink Monitor:** Replaced CPU-heavy polling with Kernel Netlink events. The system sleeps and wakes up instantly only when power sources change or hardware buttons (Fn+F) are pressed. **0% Idle CPU Usage.**
- **Asyncio Core:** The daemon uses Python's `asyncio` for non-blocking communication, allowing instantaneous synchronization between the hardware, GUI, and bar indicators.
- **Smart I/O Optimization:** Intelligent logic that skips redundant writes to `/sys` files if values haven't changed, preserving SSD lifespan.

### 🔋 Advanced Power & Thermal Control
- **Dynamic Profile Sync:** Automatically switches profiles (e.g., *Quiet* on Battery, *Turbo* on AC) based on your preferences.
- **Deep System Tweaks:** Manages CPU EPP (Energy Performance Preference), WiFi Power Management, Turbo Boost, and PCIe ASPM policies automatically per profile.
- **NOS Mode:** A specialized "Nitro/Predator Overclocking System" that forces maximum cooling and performance with long-press support.

### ❄️ Fan & Sensor Control
- **Real-Time Monitoring:** Dashboard featuring an accurate RPM feedback and multi-core temperature averaging.
- **Safety Clamping:** Manual fan control includes safety limits (20% minimum) to prevent fan stalling while allowing peak 100% cooling.
- **Dynamic Initialization:** Uses `wait_for_file` logic during startup to ensure the daemon connects to the driver as soon as it's ready.

### 🛡️ Reliable Driver Management (DKMS)
- **Automatic Kernel Rebuilds:** The project now officially transitions to using [linuwu-sense-dkms](https://github.com/ZauJulio/linuwu-sense-dkms). This ensures that the kernel driver is automatically rebuilt every time you update your Linux kernel, preventing the application from breaking after system updates.
- **Improved Stability:** Management via DKMS (Dynamic Kernel Module Support) provides a more robust way to handle out-of-tree kernel modules compared to manual compilation.

---

## ✨ Features

- 🔋 **Performance Profiles:** Eco, Quiet, Balanced, Performance, Turbo (Turbo is enabled only on AC for supported models).
- 🌡 **Fan Control:** Full control over CPU and GPU fans with real-time RPM display.
- 🎨 **RGB Lighting:** 4-zone keyboard support with modes like Wave, Breathing, and Neon.
- 💡 **Display & Sound:** LCD Override settings and Boot Animation/Sound toggles.
- 🛡 **Internals Manager:** Force Nitro/Predator model identification or reset drivers with a single click.
- 🌑 **Privacy Mode:** "Disable Logs" stops all non-critical disk writes and wipes existing logs instantly.

---

## 🛠️ Feature Usage & Integration

### 1. Hyprland Integration Switch
Located in the **Misc** (or System Settings) tab, this toggle provides a deep integration with the Hyprland compositor:
- **How it works:** When enabled, the daemon injects a `source = ~/.config/hypr/acersense.conf` line into your `hyprland.conf`. 
- **Dynamic Visuals:** It automatically manages window opacity and effect profiles based on your power state.
- **Customization:**
  - *Active/Inactive Opacity:* Use the sliders in the GUI to set your preferred transparency for focused and background windows.
  - *Mode-Specific Configs:* The system creates `acersense_bat.conf` (power saving) and `acersense_charge.conf` (high performance) in your Hyprland directory. You can edit these files to customize specific blur, shadow, or animation settings for each power state.

### 2. Default Profile Selection
Found in the **System Settings** tab, this feature allows you to automate your laptop's behavior:
- **On AC Power:** Choose which profile (e.g., *Balanced* or *Performance*) should activate the moment you plug in your charger.
- **On Battery:** Choose a power-efficient profile (e.g., *Quiet* or *Eco*) to be applied automatically when you unplug.
- **Instant Response:** Thanks to the **Netlink Monitor**, these transitions happen in milliseconds without any user intervention.

### 3. end-4 Dots Support (Quickshell)


## 🛠️ Installation & Usage

### Prerequisites
- **linuwu-sense driver:** Managed via [DKMS](https://github.com/ZauJulio/linuwu-sense-dkms) (The installer can automatically handle this for you).
- **dotnet-sdk:** Required for building the GUI from source.
- **Python3:** With `asyncio` (Standard in most modern distros).
- **Utilities:** `evtest`, `socat`, `bc` (Required for full Nitro Button and script functionality).

### Local Setup
The automated installer will check for the driver and offer to install the DKMS version if missing:
```bash
./local_setup.sh
```

### Script Details (`scripts/`)
- **`local-setup.sh`**: Main installer.
- **`NitroButton.sh`**: Background service listening for the physical Nitro key.
- **`long_press_handler.sh`**: Handles Short Press (Cycle Profile) and Long Press (NOS Mode).
- **`post_update_fixqshell.sh`**: Automated repair/integration script for end-4 dots.

---

## 🧭 Troubleshooting

- **UNKNOWN Laptop Type:** This usually means the driver isn't loaded yet. The daemon will attempt to restart the driver automatically (up to 20 times).
- **GUI not connecting:** Ensure the daemon service is running: `sudo systemctl status acersense-daemon`.
- **Logs:** 
  - Daemon: `/var/log/AcerSenseDaemon.log`
  - GUI: `/tmp/AcerSenseGUI.log`
- **Driver Check:** `lsmod | grep linuwu_sense` should return a result.

---

## ❤️ Credits & Heritage

- **[Linuwu Sense](https://github.com/0x7375646F/Linuwu-Sense):** The foundation that makes this project possible.
- **[linuwu-sense-dkms](https://github.com/ZauJulio/linuwu-sense-dkms):** For the modern DKMS-based driver management.
- **[DAMX (PXDiv)](https://github.com/PXDiv/Div-Acer-Manager-Max):** The original project this suite evolved from.
- **[end-4](https://github.com/end-4/dots-hyprland):** For the incredible Hyprland dotfiles.

---
**License:** GNU General Public License v3.0  
*Contributions and testing on different Acer models are highly welcome!*
<p align="center">
  <img src="https://raw.githubusercontent.com/kleqing/AcerSense/refs/heads/main/AcerSense/icon.png" alt="icon" width="100" style="vertical-align: middle;">
</p>

<h1 align="center">
  AcerSense Max
</h1>

**AcerSense Max** is a high-performance Linux management suite for Acer laptops (Nitro & Predator series). It provides deep hardware-level control through a modern, asynchronous, and event-driven architecture. This project is a complete evolution of the original [DAMX](https://github.com/PXDiv/Div-Acer-Manager-Max) by PXDiv, specifically optimized for enthusiasts using **Hyprland** and **end-4's dotfiles**.

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
- **Safety Clamping:** Manual fan control includes safety limits (20% minimum) to prevent stalling while allowing peak 100% bursts.

### 🎨 Hyprland & Desktop Integration
- **Dynamic Visuals:** Automatically adjusts window opacity, blur, and shadows based on the current power state.
- **end-4 Dots Compatibility:** Includes a specialized post-update script to seamlessly integrate status indicators into the Quickshell bar.
- **Privacy Mode:** "Disable Logs" clears all log files and silences non-critical output for maximum privacy and disk efficiency.

---

## 🛠️ Feature Usage & Integration

### 1. Hyprland Integration
To enable automatic visual changes (Opacity/Blur):
1. Go to the **Misc** (or System Settings) tab in the GUI.
2. Toggle **Enable Hyprland Integration**.
3. Customize your desired opacity levels for both AC and Battery modes.
   - *Active Window:* Opacity of the focused window.
   - *Inactive Window:* Opacity of background windows.
4. **Blur Control:** Edit `~/.config/hypr/acersense_bat.conf` and `acersense_charge.conf` to customize specific effects like blur or shadows for each mode.

### 2. end-4 Dots Support (Quickshell)
If you are using **end-4's Hyprland dotfiles**, you can add a real-time AcerSense indicator to your bar:
1. Run the post-update script after installing or updating AcerSense:
   ```bash
   ./scripts/post_update_fixqshell.sh
   ```
2. This script will:
   - Install a persistent Python event listener.
   - Patch `UtilButtons.qml` and `PowerIndicator.qml` in your Quickshell config.
   - Send a `USR1` signal to reload Quickshell instantly.
3. You will now see a dynamic icon (Rocket, Leaf, or Speedometer) on your bar reflecting your current profile.

### 3. Thermal Profiles
- **Eco/Low-Power:** Maximizes battery life by disabling Turbo and setting CPU EPP to 'power'.
- **Quiet:** Prioritizes silence and low fan speeds.
- **Balanced:** Optimal mix for daily use.
- **Performance/Turbo:** Maximizes clock speeds and cooling for gaming/heavy tasks.

---

## 🛠️ Installation

### Prerequisites
- `linuwu-sense` kernel driver (DKMS recommended).
- `dotnet-sdk` (for building the GUI).
- `python` with `asyncio`.

### Local Setup
Clone the repository and run the automated installer:
```bash
./local_setup.sh
```
*This script compiles the binaries, sets up systemd services, and configures socket permissions.*

---

## 🧭 Compatibility & Credits

- **Compatibility:** Supports newer Nitro V models and most Predator series. Check the [Compatibility List](Compatibility.md).
- **Linuwu Sense:** Special thanks to the [Linuwu Sense](https://github.com/0x7375646F/Linuwu-Sense) developers for kernel-level access.
- **Original Author:** Built upon the foundations laid by [PXDiv (DAMX)](https://github.com/PXDiv/Div-Acer-Manager-Max).

---

## 📂 Troubleshooting & Logs

If the laptop type is "UNKNOWN" or connection fails:
1. Check driver status: `lsmod | grep linuwu_sense`
2. Review logs:
   - **Daemon:** `/var/log/AcerSenseDaemon.log`
   - **GUI:** `/tmp/AcerSenseGUI.log`
3. Restart service: `sudo systemctl restart acersense-daemon`

---
**License:** GNU General Public License v3.0  
*Contributions and testing on different Acer models are highly welcome!*
#!/bin/bash
set -e

# --- AYARLAR ---
USER_HOME="/home/nitro"
LISTENER_PY="$USER_HOME/.config/hypr/custom/scripts/acersense_event_listener.py"
BAR_DIR=$(find "$USER_HOME/.config/quickshell" -type d -name "bar" | grep "/ii/" | head -n 1)
[ -z "$BAR_DIR" ] && BAR_DIR="$USER_HOME/.config/quickshell/ii/modules/ii/bar"
INDICATOR_QML="$BAR_DIR/PowerIndicator.qml"
UTIL_QML="$BAR_DIR/UtilButtons.qml"

echo -e "\033[0;34m>> AcerSense Quickshell Onarımı (USR1 Reload) <<\033[0m"

# 1. Python Listener (Sürekli Çalışan, Kendi Kendini Onaran)
cat <<'PYTHON_EOF' > "$LISTENER_PY"
#!/usr/bin/env python3
import socket, json, sys, os, time

SOCKET_PATH = "/var/run/AcerSense.sock"

def get_ac_state():
    try:
        for p in ["/sys/class/power_supply/AC/online", "/sys/class/power_supply/ACAD/online"]:
            if os.path.exists(p):
                with open(p, "r") as f: return "AC" if f.read().strip() == "1" else "BAT"
    except: pass
    return "BAT"

def send_update(profile, ac_state):
    try:
        data = {"alt": profile, "tooltip": f"Mode: {ac_state}\nProfile: {profile}"}
        sys.stdout.write(json.dumps(data) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        sys.exit(0)

def main():
    while True:
        try:
            if not os.path.exists(SOCKET_PATH):
                time.sleep(2)
                continue

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(SOCKET_PATH)
                s.sendall(b'{"command": "get_all_settings"}\n')
                
                f = s.makefile()
                last_profile = "unknown"
                ac_state = get_ac_state()
                
                for line in f:
                    try:
                        msg = json.loads(line.strip())
                        if "data" in msg and "thermal_profile" in msg["data"]:
                            last_profile = msg["data"]["thermal_profile"]["current"]
                            send_update(last_profile, ac_state)
                        elif msg.get("type") == "event":
                            evt = msg.get("event")
                            d = msg.get("data")
                            if evt == "thermal_profile_changed":
                                last_profile = d.get("profile", last_profile)
                                send_update(last_profile, ac_state)
                            elif evt == "power_state_changed":
                                ac_state = "AC" if d.get("plugged_in") else "BAT"
                                send_update(last_profile, ac_state)
                    except: continue
        except: time.sleep(1)

if __name__ == "__main__":
    main()
PYTHON_EOF
chmod +x "$LISTENER_PY"

# 2. PowerIndicator.qml
cat <<QML_EOF > "$INDICATOR_QML"
import QtQuick
import Quickshell
import Quickshell.Io
import qs.modules.common
import qs.modules.common.widgets

Item {
    id: root
    implicitWidth: icon.implicitWidth
    implicitHeight: icon.implicitHeight
    property string currentProfile: "unknown"

    Process {
        id: proc
        command: ["python3", "$LISTENER_PY"]
        running: true
        stdout: SplitParser {
            onRead: data => {
                let clean = data.trim();
                if (clean) {
                    try {
                        let j = JSON.parse(clean);
                        if (j.alt) root.currentProfile = j.alt;
                    } catch(e) {}
                }
            }
        }
    }

    MaterialSymbol {
        id: icon
        anchors.centerIn: parent
        text: {
            let p = root.currentProfile.toLowerCase();
            if (p.indexOf("performance") !== -1 || p.indexOf("turbo") !== -1) return "rocket_launch";
            if (p.indexOf("quiet") !== -1 || p.indexOf("low") !== -1 || p.indexOf("eco") !== -1) return "energy_savings_leaf";
            if (p.indexOf("balanced") !== -1) return "speed";
            return "help";
        }
        iconSize: Appearance.font.pixelSize.large
        color: Appearance.colors.colOnLayer2
    }
}
QML_EOF

# 3. UtilButtons.qml Yaması
if [ -f "$UTIL_QML" ]; then
    grep -q "import Quickshell.Io" "$UTIL_QML" || sed -i '1i import Quickshell.Io' "$UTIL_QML"
    perl -0777 -i -pe 's/Loader\s*\{\s*active: Config\.options\.bar\.utilButtons\.showPerformanceProfileToggle.*?\}\s*\}\s*\}/Loader {\n            active: Config.options.bar.utilButtons.showPerformanceProfileToggle\n            visible: Config.options.bar.utilButtons.showPerformanceProfileToggle\n            sourceComponent: CircleUtilButton {\n                Layout.alignment: Qt.AlignVCenter\n                onClicked: {} \n                PowerIndicator {}\n            }\n        }/s' "$UTIL_QML"
fi

# 4. Yenileme
echo ">> Daemon ve Listener tazeleniyor..."
pkill -f "acersense_event_listener" || true
sudo systemctl restart acersense-daemon.service

echo ">> Quickshell USR1 sinyali gönderiliyor..."
pkill -USR1 quickshell || true

echo -e "\033[0;32m>> BAŞARILI! Sistem güncellendi.\033[0m"

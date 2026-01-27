#!/usr/bin/env python3
# AcerSense Power Source Detection - Monitors power source using Kernel Netlink Events (Instant)

import os
import logging
import socket
import select
import threading
import time

# Get logger from main daemon
log = logging.getLogger("AcerSenseDaemon")

class PowerSourceDetector:
    """Detects power source and manages automatic mode switching using Netlink UEvents"""

    def __init__(self, manager):
        self.manager = manager
        self.current_source = None
        self.running = False
        self.monitor_thread = None
        
        # Paths to check
        self.possible_power_supply_paths = [
            "/sys/class/power_supply/AC/online",
            "/sys/class/power_supply/ACAD/online",
            "/sys/class/power_supply/ADP1/online",
            "/sys/class/power_supply/AC0/online"
        ]
        
        log.info("PowerSourceDetector initialized")

    def start_monitoring(self):
        """Start monitoring for power events"""
        if self.running:
            return

        self.running = True
        
        # Perform initial check immediately
        self.current_source = self._is_ac_connected()
        # We don't trigger handle_power_change here to avoid double-setting on startup, 
        # relying on the manager to set the initial state.
        
        # Start the monitor thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        log.info("Power source monitoring started (Netlink Mode)")

    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False

    def _monitor_loop(self):
        """Main loop that tries Netlink and falls back to polling if needed"""
        try:
            self._monitor_netlink()
        except Exception as e:
            log.error(f"Netlink monitor failed: {e}. Falling back to polling.")
            self._monitor_polling()

    def _monitor_netlink(self):
        """Monitor Kernel UEvents via Netlink Socket (Instant Response)"""
        NETLINK_KOBJECT_UEVENT = 15
        sock = None

        try:
            sock = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, NETLINK_KOBJECT_UEVENT)
            # Bind to group 1 (kernel broadcast)
            # pid=0 (let kernel assign), groups=1
            sock.bind((0, 1))
        except Exception as e:
            log.warning(f"Could not bind Netlink socket: {e}")
            raise # Re-raise to trigger fallback

        poll_obj = select.poll()
        poll_obj.register(sock, select.POLLIN)

        log.info("Netlink socket bound successfully. Listening for kernel events...")

        while self.running:
            try:
                # Poll indefinitely (-1). Wake up only when kernel sends an event.
                # This eliminates the 2-second CPU 'poke'.
                events = poll_obj.poll(-1)
                
                should_check_power = False
                should_check_profile = False
                
                for fd, event in events:
                    if fd == sock.fileno():
                        # Receive event data
                        data = sock.recv(16384)
                        decoded = data.decode('utf-8', errors='replace')
                        
                        # Check for power supply events
                        if "SUBSYSTEM=power_supply" in decoded:
                            log.debug("Kernel Event: Power source change detected")
                            should_check_power = True
                        
                        # Check for thermal profile events (platform_profile)
                        if "platform_profile" in decoded:
                            log.debug("Kernel Event: Thermal profile change detected")
                            should_check_profile = True
                
                if should_check_power:
                    # Give sysfs a tiny moment to update
                    time.sleep(0.1)
                    self.check_power_source()
                
                if should_check_profile:
                    # Notify manager to sync state with hardware
                    self.manager.handle_hardware_event()

            except Exception as e:
                log.error(f"Error in Netlink loop: {e}")
                time.sleep(5) # Prevent tight loop on error

        if sock:
            sock.close()

    def _monitor_polling(self):
        """Fallback polling loop (Old method, slower but reliable)"""
        log.info("Starting fallback polling loop (1s interval)")
        while self.running:
            self.check_power_source()
            time.sleep(1)

    def check_power_source(self):
        """Check current power source state and notify if changed"""
        is_plugged_in = self._is_ac_connected()

        if is_plugged_in != self.current_source:
            log.info(f"Power state changed: {self.current_source} -> {is_plugged_in}")
            self.current_source = is_plugged_in
            self._handle_power_change(is_plugged_in)

    def _is_ac_connected(self) -> bool:
        """Check if AC power is connected (Read from sysfs)"""
        try:
            # Try known paths first
            for path in self.possible_power_supply_paths:
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        return f.read().strip() == "1"

            # Fallback: Scan sysfs for any AC/ADP device
            base = "/sys/class/power_supply"
            if os.path.exists(base):
                for item in os.listdir(base):
                    if item.startswith("AC") or item.startswith("ADP"):
                        path = os.path.join(base, item, "online")
                        if os.path.exists(path):
                            with open(path, 'r') as f:
                                return f.read().strip() == "1"

            return False
        except Exception as e:
            log.error(f"Error checking power status: {e}")
            return False

    def _handle_power_change(self, is_plugged_in: bool):
        """Notify manager of change"""
        self.manager.handle_power_change(is_plugged_in)

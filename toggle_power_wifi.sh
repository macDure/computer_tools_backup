#!/bin/bash

# Ensure we have the correct DBus session bus address
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"

echo "Starting WiFi and Power Profile Toggle Service..."

# Function to handle lock event
handle_lock() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Screen Locked: Disabling WiFi and setting power-saver mode..."
    nmcli radio wifi off
    powerprofilesctl set power-saver
}

# Function to handle unlock event
handle_unlock() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Screen Unlocked: Enabling WiFi and setting performance mode..."
    nmcli radio wifi on
    powerprofilesctl set performance
}

# Check initial screen saver state at start
IS_LOCKED=$(gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver --method org.gnome.ScreenSaver.GetActive 2>/dev/null)

if [[ "$IS_LOCKED" == "(true,)" ]]; then
    handle_lock
else
    # Default to unlock setup if unlocked or call fails
    handle_unlock
fi

# Monitor GNOME ScreenSaver signals
gdbus monitor --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver | while read -r line; do
    if echo "$line" | grep -q "ActiveChanged (true,)"; then
        handle_lock
    elif echo "$line" | grep -q "ActiveChanged (false,)"; then
        handle_unlock
    fi
done

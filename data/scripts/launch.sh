#!/bin/bash

set -euo pipefail

launch_stewart() {
    local desktop_entry_name="stewart"
    local desktop_file_path="$HOME/.local/share/applications/stewart.desktop"

    # Check if desktop file exists
    if [[ ! -f "$desktop_file_path" ]]; then
        echo "Error: Desktop file not found at $desktop_file_path"
        echo "Please run create_desktop_entry.sh first to create the desktop entry."
        exit 1
    fi

    echo "Attempting to launch Stewart..."

    # Try gtk-launch first
    if command -v gtk-launch &> /dev/null; then
        if gtk-launch "$desktop_entry_name"; then
            echo "Stewart launched successfully via gtk-launch"
            exit 0
        fi
    fi

    # Try xdg-open
    if command -v xdg-open &> /dev/null; then
        if xdg-open "$desktop_file_path"; then
            echo "Stewart launched successfully via xdg-open"
            exit 0
        fi
    fi

    # Try gio
    if command -v gio &> /dev/null; then
        if gio open "$desktop_file_path"; then
            echo "Stewart launched successfully via gio"
            exit 0
        fi
    fi

    # Try dbus-send
    if command -v dbus-send &> /dev/null; then
        if dbus-send --session --dest=org.freedesktop.Application.$desktop_entry_name \
            /org/freedesktop/Application/$desktop_entry_name \
            org.freedesktop.Application.Activate \
            &> /dev/null; then
            echo "Stewart launched successfully via dbus-send"
            exit 0
        fi
    fi

    echo "Warning: Could not automatically launch Stewart using any available method."
    echo "Please run it manually from your applications menu or try running the desktop file directly."
    exit 1
}

launch_stewart
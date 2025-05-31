#!/bin/bash

installer_desktop_entry() {
    local desktop_file_name="stewart-installer.desktop"
    local desktop_file_path="$HOME/.local/share/applications/$desktop_file_name"
    local installer_dir="$(dirname "$(dirname "$(dirname "$(realpath "${BASH_SOURCE[0]}")")")")"
    local icon_path="$installer_dir/data/assets/installer_logo.png"
    local exec_path=""

    if [[ -f "$installer_dir/venv/bin/activate" ]]; then
        exec_path="bash -c \"cd '$installer_dir' && source venv/bin/activate && python3.11 main.py\""
        echo "Using virtual environment for installer"
    elif command -v python3.11 &> /dev/null; then
        exec_path="bash -c \"cd '$installer_dir' && python3.11 main.py\""
        echo "Virtual environment not found, using system python3.11 for installer"
    elif command -v python &> /dev/null; then
        exec_path="bash -c \"cd '$installer_dir' && python main.py\""
        echo "python3.11 not found, using system python for installer"
    else
        echo "Error: No Python interpreter found for installer"
        return 1
    fi

    mkdir -p "$HOME/.local/share/applications"

    cat > "$desktop_file_path" <<EOF
[Desktop Entry]
Name=Stewart Installer
GenericName=Stewart Installation Tool
Comment=Install and manage Stewart Voice Assistant
Exec=$exec_path
Icon=$icon_path
Terminal=false
Type=Application
Categories=Utility;System;
EOF

    chmod +x "$desktop_file_path"
    echo "Installer desktop shortcut created at: $desktop_file_path"
    echo "Installer exec command: $exec_path"
}

installer_desktop_entry
#!/bin/bash

set -euo pipefail

DIR=${1:-}

# Check if install directory was passed
if [[ -z "$DIR" ]]; then
    echo "Usage: $0 <app_install_dir>"
    exit 1
fi

# Check if Python 3.11 is installed
if ! command -v python3.11 &> /dev/null; then
    echo "Error: python3.11 is not installed or not in PATH."
    exit 1
fi

# Check if the directory exists
if [[ ! -d "$DIR" ]]; then
    echo "Error: App install directory '$DIR' does not exist."
    exit 1
fi

# Check if the virtual environment exists
if [[ ! -f "$DIR/venv/bin/activate" ]]; then
    echo "Error: Virtual environment not found in '$DIR/venv'."
    exit 1
fi

# Check if main.py exists
if [[ ! -f "$DIR/main.py" ]]; then
    echo "Error: main.py not found in '$DIR'."
    exit 1
fi

create_desktop_entry() {
    local desktop_file_name="stewart.desktop"
    local desktop_file_path="$HOME/.local/share/applications/$desktop_file_name"
    local icon_path="$DIR/data/images/stewart.png"

    local base_cmd="cd '$DIR' && source venv/bin/activate && python3.11 main.py; exec bash"

    local exec_path=""

    declare -A terminals=(
        [gnome-terminal]="gnome-terminal -- bash -c \"$base_cmd\""
        [gnome-console]="gnome-console -- bash -c \"$base_cmd\""
        [kgx]="kgx -- bash -c \"$base_cmd\""
        [konsole]="konsole --noclose -e bash -c \"$base_cmd\""
        [xfce4-terminal]="xfce4-terminal --command=\"bash -c '$base_cmd'\""
        [tilix]="tilix -e bash -c \"$base_cmd\""
        [kitty]="kitty bash -c \"$base_cmd\""
        [alacritty]="alacritty -e bash -c \"$base_cmd\""
        [wezterm]="wezterm start -- bash -c \"$base_cmd\""
        [lxterminal]="lxterminal -e bash -c \"$base_cmd\""
        [terminator]="terminator -x bash -c \"$base_cmd\""
        [mate-terminal]="mate-terminal -- bash -c \"$base_cmd\""
        [urxvt]="urxvt -e bash -c \"$base_cmd\""
        [st]="st -e bash -c \"$base_cmd\""
        [xterm]="xterm -hold -e bash -c \"$base_cmd\""
        [x-terminal-emulator]="x-terminal-emulator -e bash -c \"$base_cmd\""
    )

    local found_terminal=""
    for term in "${!terminals[@]}"; do
        if command -v "$term" &> /dev/null; then
            found_terminal="$term"
            break
        fi
    done

    # Set exec_path based on available terminal
    if [[ -n "$found_terminal" ]]; then
        exec_path="${terminals[$found_terminal]}"
        echo "Using terminal: $found_terminal"
    else
        exec_path="bash -c \"cd '$DIR' && source venv/bin/activate && python3.11 main.py; exec bash\""
        echo "No supported terminal found, using fallback execution"
    fi

    mkdir -p "$HOME/.local/share/applications"

    cat > "$desktop_file_path" <<EOF
[Desktop Entry]
Name=Stewart
GenericName=Voice Assistant
Comment=Useful voice assistant
Exec=$exec_path
Icon=$icon_path
Terminal=true
Type=Application
EOF

    chmod +x "$desktop_file_path"
    echo "Desktop shortcut created or updated at: $desktop_file_path"
    echo "Exec command: $exec_path"
}

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
create_desktop_entry

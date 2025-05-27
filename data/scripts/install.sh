#!/bin/bash

DIR=$1

ensure_polkit_agent() {
    if pgrep -f polkit-gnome-authentication-agent-1 > /dev/null || \
       pgrep -f lxqt-policykit-agent > /dev/null || \
       pgrep -f polkit-kde-authentication-agent-1 > /dev/null; then
        echo "Polkit agent already running."
        return
    fi

    echo "No polkit agent detected. Attempting to install and start one..."

    if command -v apt &> /dev/null; then
        pkexec bash -c 'apt update -qq && apt install -y policykit-1-gnome'
        /usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1 &
    elif command -v dnf &> /dev/null; then
        pkexec bash -c 'dnf install -y polkit-gnome'
        /usr/libexec/polkit-gnome-authentication-agent-1 &
    elif command -v yum &> /dev/null; then
        pkexec bash -c 'yum install -y polkit-gnome'
        /usr/libexec/polkit-gnome-authentication-agent-1 &
    elif command -v pacman &> /dev/null; then
        pkexec bash -c 'pacman -Sy --noconfirm polkit-gnome'
        /usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1 &
    elif command -v zypper &> /dev/null; then
        pkexec bash -c 'zypper install -y polkit-gnome'
        /usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1 &
    else
        echo "No supported package manager found to install a polkit agent."
        exit 1
    fi

    sleep 2  # Give the agent a moment to start
}

is_installed_python() {
    if command -v python3.11 &> /dev/null; then
        return 0
    else
        return 1
    fi
}

install_python() {
    if command -v apt &> /dev/null; then
        echo "Detected apt (Debian/Ubuntu-based)"
        pkexec bash -c 'apt update -qq && apt install -y python3.11 python3.11-venv python3.11-dev' 2>/dev/null
    elif command -v dnf &> /dev/null; then
        echo "Detected dnf (Fedora-based)"
        pkexec bash -c 'dnf update -y -q && dnf install -y python3.11 python3.11-devel' 2>/dev/null
    elif command -v yum &> /dev/null; then
        echo "Detected yum (RHEL/CentOS-based)"
        pkexec bash -c 'yum update -y -q && yum install -y python3.11 python3.11-devel' 2>/dev/null
    elif command -v pacman &> /dev/null; then
        echo "Detected pacman (Arch-based)"
        pkexec bash -c 'pacman -Sy --noconfirm python python-pip base-devel' 2>/dev/null
    elif command -v zypper &> /dev/null; then
        echo "Detected zypper (OpenSUSE-based)"
        pkexec bash -c 'zypper refresh -q && zypper install -y python3 python3-devel' 2>/dev/null
    else
        echo "No compatible package manager found. Please install Python 3.11 manually."
        exit 1
    fi
}

install_additional_packages() {
    if command -v apt &> /dev/null; then
        echo "Installing additional packages for apt-based system"
        pkexec bash -c 'apt update -qq && apt install -y mpv libmpv-dev portaudio19-dev python3-evdev gcc g++ python3-dev dbus libdbus-1-dev python3-dbus' 2>/dev/null
    elif command -v dnf &> /dev/null; then
        echo "Installing additional packages for dnf-based system"
        pkexec bash -c 'dnf update -y -q && dnf install -y mpv-devel mpv portaudio-devel portaudio python3-pyaudio python-pyaudio python3-evdev gcc g++ python3-devel python3.11-devel dbus python3-dbus' 2>/dev/null
    elif command -v yum &> /dev/null; then
        echo "Installing additional packages for yum-based system"
        pkexec bash -c 'yum update -y -q && yum install -y mpv-devel mpv portaudio-devel portaudio python3-pyaudio python-pyaudio python3-evdev gcc gcc-c++ python3-devel python3.11-devel dbus python3-dbus' 2>/dev/null
    elif command -v pacman &> /dev/null; then
        echo "Installing additional packages for pacman-based system"
        pkexec bash -c 'pacman -Sy --noconfirm portaudio python-pyaudio python-evdev gcc gcc-libs dbus python-dbus' 2>/dev/null
    elif command -v zypper &> /dev/null; then
        echo "Installing additional packages for zypper-based system"
        pkexec bash -c 'zypper refresh -q && zypper install -y mpv-devel mpv portaudio-devel portaudio python3-pyaudio python3-evdev gcc gcc-c++ python3-devel python3.11-devel dbus python3-dbus' 2>/dev/null
    else
        echo "No compatible package manager found. Please install additional packages manually."
        exit 1
    fi
}

install_requirements() {
    echo "Creating virtual environment"
    cd "$DIR" || exit
    python3.11 -m venv venv
    source venv/bin/activate
    python3.11 -m ensurepip --quiet

    echo "Upgrading pip and setuptools"
    pip install -U pip setuptools wheel --quiet

    if [[ -f requirements.txt ]]; then
        echo "Installing requirements"
        pip install -r requirements.txt --progress-bar off 2>&1 | while IFS= read -r line; do
            if [[ $line == *"Collecting"* ]]; then
                package=$(echo "$line" | sed 's/Collecting //' | cut -d' ' -f1)
                echo "Collecting $package"
            elif [[ $line == *"Successfully installed"* ]]; then
                echo "$line"
            elif [[ $line == *"ERROR"* ]] || [[ $line == *"error"* ]]; then
                echo "$line"
            fi
        done
    else
        echo "requirements.txt not found in $DIR"
        return 1
    fi

    echo "Installing PyTorch CPU version"
    pip install torch==2.2.1+cpu -f https://download.pytorch.org/whl/torch_stable.html --progress-bar off --quiet 2>&1 | while IFS= read -r line; do
        if [[ $line == *"Successfully installed"* ]]; then
            echo "$line"
        elif [[ $line == *"ERROR"* ]] || [[ $line == *"error"* ]]; then
            echo "$line"
        fi
    done
}

ensure_polkit_agent

is_installed_python
is_python_installed=$?

if [ $is_python_installed -eq 0 ]; then
    echo "Python 3.11 is already installed."
else
    echo "Python 3.11 not found. Attempting to install..."
    install_python

    is_installed_python
    is_python_installed=$?

    if [ $is_python_installed -ne 0 ]; then
        echo "Python 3.11 installation failed or not supported."
        exit 1
    fi
fi

install_additional_packages
install_requirements

echo "Installation process completed"

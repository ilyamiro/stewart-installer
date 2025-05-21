#!/bin/bash

DIR=$1

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
        pkexec bash -c 'apt update && apt install -y python3.11 python3.11-venv python3.11-dev'
    elif command -v dnf &> /dev/null; then
        echo "Detected dnf (Fedora-based)"
        pkexec bash -c 'dnf update -y && dnf install -y python3.11 python3.11-devel'
    elif command -v yum &> /dev/null; then
        echo "Detected yum (RHEL/CentOS-based)"
        pkexec bash -c 'yum update -y && yum install -y python3.11 python3.11-devel'
    elif command -v pacman &> /dev/null; then
        echo "Detected pacman (Arch-based)"
        pkexec bash -c 'pacman -Sy --noconfirm python python-pip base-devel'
        # Arch usually has python 3.11 as default or close
    elif command -v zypper &> /dev/null; then
        echo "Detected zypper (OpenSUSE-based)"
        pkexec bash -c 'zypper refresh && zypper install -y python3 python3-devel'
    else
        echo "No compatible package manager found. Please install Python 3.11 manually."
        exit 1
    fi
}

install_additional_packages() {
    if command -v apt &> /dev/null; then
        echo "Installing additional packages for apt-based system"
        pkexec bash -c 'apt update && apt install -y mpv libmpv-dev portaudio19-dev python3-pyaudio python3-evdev gcc g++ python3-dev python3.11-dev dbus libdbus-1-dev python3-dbus'
    elif command -v dnf &> /dev/null; then
        echo "Installing additional packages for dnf-based system"
        pkexec bash -c 'dnf update -y && dnf install -y mpv-devel mpv portaudio-devel portaudio python3-pyaudio python-pyaudio python3-evdev gcc g++ python3-devel python3.11-devel dbus python3-dbus'
    elif command -v yum &> /dev/null; then
        echo "Installing additional packages for yum-based system"
        pkexec bash -c 'yum update -y && yum install -y mpv-devel mpv portaudio-devel portaudio python3-pyaudio python-pyaudio python3-evdev gcc gcc-c++ python3-devel python3.11-devel dbus python3-dbus'
    elif command -v pacman &> /dev/null; then
        echo "Installing additional packages for pacman-based system"
        pkexec bash -c 'pacman -Sy --noconfirm mpv portaudio python-pyaudio python-evdev gcc gcc-libs python python-devel dbus python-dbus'
        # Note: Arch package names might differ, adjust if needed.
    elif command -v zypper &> /dev/null; then
        echo "Installing additional packages for zypper-based system"
        pkexec bash -c 'zypper refresh && zypper install -y mpv-devel mpv portaudio-devel portaudio python3-pyaudio python3-evdev gcc gcc-c++ python3-devel python3.11-devel dbus python3-dbus'
    else
        echo "No compatible package manager found. Please install additional packages manually."
        exit 1
    fi
}

install_requirements() {
    cd "$DIR" || exit
    python3.11 -m venv venv
    source venv/bin/activate
    python3.11 -m ensurepip
    pip install -U pip setuptools wheel

    if [[ -f requirements.txt ]]; then
        pip install -r requirements.txt
    else
        echo "requirements.txt not found in $DIR"
        return 1
    fi

    pip install torch==2.2.1+cpu -f https://download.pytorch.org/whl/torch_stable.html
}


is_installed_python
is_python_installed=$?

if [ $is_python_installed -eq 0 ]; then
    echo "Python 3.11 is already installed."
else
    echo "Python 3.11 not found. Attempting to install..."
    install_python

    # Re-check after installation
    is_installed_python
    is_python_installed=$?

    if [ $is_python_installed -ne 0 ]; then
        echo "Python 3.11 installation failed or not supported."
        exit 1
    fi
fi

# Install additional system packages required for your dependencies
install_additional_packages

# Step 2: If Python 3.11 is installed, proceed with installing Python requirements
install_requirements

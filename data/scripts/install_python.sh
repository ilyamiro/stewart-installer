#!/bin/bash

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
        sudo apt update
        sudo apt install -y python3.11
    elif command -v dnf &> /dev/null; then
        echo "Detected dnf (Fedora-based)"
        sudo dnf install -y python3.11
    elif command -v yum &> /dev/null; then
        echo "Detected yum (RHEL/CentOS-based)"
        sudo yum install -y python3.11
    elif command -v pacman &> /dev/null; then
        echo "Detected pacman (Arch-based)"
        sudo pacman -Sy python311
    elif command -v zypper &> /dev/null; then
        echo "Detected zypper (OpenSUSE-based)"
        sudo zypper install -y python3.11
    else
        echo "No compatible package manager found. Please install Python 3.11 manually."
        exit 1
    fi
}

install_requirements() {
    python3.11 -m venv venv
    source venv/bin/activate
    pip install --update pip setuptools wheel
    pip install -r requirements.txt
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

# Step 2: If Python 3.11 is installed, proceed with installing requirements
install_requirements

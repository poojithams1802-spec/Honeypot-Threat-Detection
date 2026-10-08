#!/usr/bin/env bash
# ==============================================================================
# Cowrie Honeypot - Docker & Docker Compose Installation Script for Ubuntu
# ==============================================================================
# This script installs the official Docker Engine and Docker Compose plugin on
# an isolated Ubuntu lab VM.
#
# Usage:
#   chmod +x scripts/install_docker.sh
#   ./scripts/install_docker.sh
# ==============================================================================

set -euo pipefail

echo "=========================================================="
echo " Starting Docker & Docker Compose installation for Ubuntu"
echo "=========================================================="

# 1. Verify OS is Ubuntu/Debian
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$ID" != "ubuntu" && "$ID_LIKE" != *"ubuntu"* && "$ID" != "debian" ]]; then
        echo "[-] WARNING: This script is tailored for Ubuntu/Debian systems."
        echo "[-] Detected OS: $PRETTY_NAME"
        read -p "Do you want to proceed anyway? (y/N): " -r CONFIRM
        if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
            echo "[-] Aborting installation."
            exit 1
        fi
    fi
else
    echo "[-] Cannot detect OS via /etc/os-release. Aborting."
    exit 1
fi

echo "[+] Step 1: Removing conflicting legacy packages (if any)..."
sudo apt-get remove -y docker.io docker-doc docker-compose podman-docker containerd runc 2>/dev/null || true

echo "[+] Step 2: Updating apt package index and installing prerequisites..."
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release

echo "[+] Step 3: Setting up Docker official GPG key..."
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "[+] Step 4: Adding Docker official repository to apt sources..."
CODENAME="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
if [ -z "$CODENAME" ]; then
    CODENAME=$(lsb_release -cs)
fi

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $CODENAME stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "[+] Step 5: Installing Docker Engine, CLI, Containerd, and Compose plugin..."
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "[+] Step 6: Enabling and starting Docker systemd service..."
if command -v systemctl >/dev/null 2>&1; then
    sudo systemctl enable docker
    sudo systemctl start docker
elif command -v service >/dev/null 2>&1; then
    sudo service docker start || true
fi

echo "[+] Step 7: Adding current user ($USER) to docker group..."
sudo usermod -aG docker "$USER" || true

echo "[+] Step 8: Ensuring log directory permissions for Cowrie..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
mkdir -p "$PROJECT_ROOT/data/cowrie_logs"
# Cowrie runs as UID 1000 inside the official container
chmod -R 777 "$PROJECT_ROOT/data/cowrie_logs" || true

echo ""
echo "=========================================================="
echo " Docker installation completed successfully!"
echo "=========================================================="
docker --version || true
docker compose version || true
echo ""
echo "[i] NOTE: To run Docker commands without 'sudo', run:"
echo "    newgrp docker"
echo "    or log out and log back in to your Ubuntu session."

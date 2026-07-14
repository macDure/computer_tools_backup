#!/bin/bash
# ThinkPad T14p Gen3 NVIDIA Driver Setup Script
# Configures system to use the open-source kernel module driver (required for this GPU) and sets it as the primary display GPU.

set -e

echo "=========================================================="
echo "Starting NVIDIA GPU Driver Installation & Configuration"
echo "=========================================================="

echo "[1/3] Updating apt package listings..."
sudo apt-get update

echo "[2/3] Installing recommended open-source NVIDIA driver (nvidia-driver-595-open)..."
# Installing nvidia-driver-595-open, which is required for this GPU architecture on this kernel.
# Also installing nvidia-prime (graphics switching) and nvidia-settings (control panel).
sudo apt-get install -y nvidia-driver-595-open nvidia-prime nvidia-settings

echo "[3/3] Setting NVIDIA GPU as the default display device..."
sudo prime-select nvidia

echo "=========================================================="
echo "Installation and configuration completed successfully!"
echo "Please REBOOT your system now for the new driver to load."
echo "After rebooting, you can verify with: nvidia-smi"
echo "=========================================================="

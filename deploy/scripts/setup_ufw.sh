#!/usr/bin/env bash
set -e

echo "============================================================"
echo " ODtech ERP: UFW Firewall Configuration"
echo "============================================================"

# Ensure UFW is installed
if ! command -v ufw >/dev/null 2>&1; then
    echo "[*] Installing UFW..."
    sudo apt-get update && sudo apt-get install -y ufw
fi

echo "[*] Configuring firewall rules (safe order: allowing SSH first)..."

# Safe default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# CRITICAL: Always allow SSH port 22 first
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow OpenSSH comment 'OpenSSH profile'

# Web traffic
sudo ufw allow 80/tcp comment 'Nginx HTTP'
sudo ufw allow 443/tcp comment 'Nginx HTTPS'

# Tailscale VPN interface
if ip link show tailscale0 >/dev/null 2>&1; then
    sudo ufw allow in on tailscale0 comment 'Tailscale VPN'
    echo "[+] Tailscale interface (tailscale0) allowed."
fi

# Netdata Monitoring port (optional local monitoring)
sudo ufw allow 19999/tcp comment 'Netdata Monitoring'

# Loopback
sudo ufw allow in on lo comment 'Local loopback'

echo "[*] Enabling UFW firewall..."
sudo ufw --force enable

echo ""
echo "[+] Active UFW Status:"
sudo ufw status verbose

echo ""
echo "============================================================"
echo " [SUCCESS] UFW Firewall is enabled and active!"
echo "============================================================"

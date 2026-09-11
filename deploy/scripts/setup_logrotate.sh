#!/usr/bin/env bash
set -e

echo "============================================================"
echo " ODtech ERP: Setting up Logrotate"
echo "============================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
LOGROTATE_SRC="$DEPLOY_DIR/logrotate/odtech"
LOGROTATE_DEST="/etc/logrotate.d/odtech"

# Ensure directories and files exist with correct permissions
mkdir -p /home/server_admin/ODtech/logs
chmod 755 /home/server_admin/ODtech/logs
touch /home/server_admin/backups/cron_backup.log
chmod 640 /home/server_admin/backups/cron_backup.log

echo "[*] Installing logrotate configuration to $LOGROTATE_DEST..."
sudo cp "$LOGROTATE_SRC" "$LOGROTATE_DEST"
sudo chmod 644 "$LOGROTATE_DEST"
sudo chown root:root "$LOGROTATE_DEST"

echo "[*] Testing logrotate configuration syntax..."
sudo logrotate -d "$LOGROTATE_DEST"

echo ""
echo "============================================================"
echo " [SUCCESS] Logrotate is successfully configured!"
echo "============================================================"

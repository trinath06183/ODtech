#!/usr/bin/env bash
# ==============================================================================
# ODtech ERP: Installer for Automated USB Backup Trigger
# Configures udev rules and systemd to detect a specific external drive,
# backup system data, prune backups >30 days old, and safely eject.
# ==============================================================================
set -e

if [ "$EUID" -ne 0 ]; then
    echo "[-] Please run this setup script as root or with sudo:"
    echo "    sudo bash deploy/scripts/setup_usb_backup.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKER_SRC="$SCRIPT_DIR/usb_backup_worker.sh"
WORKER_DEST="/usr/local/bin/odtech_usb_backup.sh"
SYSTEMD_SERVICE="/etc/systemd/system/odtech-usb-backup@.service"
UDEV_RULE_FILE="/etc/udev/rules.d/99-odtech-usb-backup.rules"

echo "============================================================"
echo " ODtech ERP: Automated External Drive Backup Setup"
echo "============================================================"

# Ensure required utilities are present
for cmd in udisksctl blkid sync wall; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "[*] Installing missing system tools ($cmd)..."
        apt-get update && apt-get install -y udisks2 util-linux libnotify-bin
        break
    fi
done

# Step 1: Install worker script
echo "[1/4] Installing backup worker script to $WORKER_DEST..."
cp "$WORKER_SRC" "$WORKER_DEST"
chmod +x "$WORKER_DEST"

# Step 2: Install systemd service unit
echo "[2/4] Installing systemd service unit..."
cat << 'EOF' > "$SYSTEMD_SERVICE"
[Unit]
Description=ODtech Automated USB Backup Worker
After=local-fs.target

[Service]
Type=oneshot
TimeoutStartSec=1800
ExecStart=/usr/local/bin/odtech_usb_backup.sh %I

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# Step 3: Identify Drive UUID
echo ""
echo "[3/4] External Drive Identification:"
echo "------------------------------------------------------------"
echo "Currently detected block devices and UUIDs:"
lsblk -o NAME,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINT
echo "------------------------------------------------------------"
echo ""

TARGET_UUID="$1"

if [ -z "$TARGET_UUID" ]; then
    echo "Please plug in your USB drive or external hard disk now."
    read -rp "Enter the UUID of your external drive partition (e.g. 4A21-7B89 or b52431fa-...): " TARGET_UUID
fi

if [ -z "$TARGET_UUID" ]; then
    echo "[-] No UUID entered. Setup aborted."
    exit 1
fi

# Step 4: Write udev rule
echo ""
echo "[4/4] Writing udev rule for UUID: $TARGET_UUID..."
cat << EOF > "$UDEV_RULE_FILE"
# ODtech ERP: Automatic USB Backup for UUID=$TARGET_UUID
ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_UUID}=="$TARGET_UUID", TAG+="systemd", ENV{SYSTEMD_WANTS}="odtech-usb-backup@%k.service"
EOF

# Reload udev
udevadm control --reload-rules
udevadm trigger

echo ""
echo "============================================================"
echo " [SUCCESS] Automated USB Backup Configured Successfully!"
echo "============================================================"
echo " Drive UUID locked: $TARGET_UUID"
echo " Logs will be stored at: /var/log/odtech_usb_backup.log"
echo ""
echo "How it works:"
echo " 1. Insert this specific external drive into any USB port."
echo " 2. The server detects the UUID and runs ODtech full backup."
echo " 3. Copies complete backup archive (.tar.gz) and DB (.sql.gz) to /odtech_backups on the drive."
echo " 4. Removes backups on the drive older than 30 days."
echo " 5. Sends a message: 'ODtech Backup copied successfully!'."
echo " 6. Automatically unmounts and ejects the drive safely."
echo "============================================================"


#!/usr/bin/env bash
# ==============================================================================
# ODtech ERP: USB Auto-Backup Worker
# Triggered by systemd when the designated external USB drive is plugged in.
# ==============================================================================
set -e

DEV_NAME="$1"
if [ -z "$DEV_NAME" ]; then
    echo "[-] Error: Device name not specified."
    exit 1
fi

DEV="/dev/$DEV_NAME"
MOUNT_POINT="/mnt/odtech_usb_backup"
LOG_FILE="/var/log/odtech_usb_backup.log"
PROJECT_DIR="/home/server_admin/ODtech"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
BACKUP_DIR="/home/server_admin/backups"

mkdir -p "$(dirname "$LOG_FILE")"
exec >> "$LOG_FILE" 2>&1

echo ""
echo "========================================================================"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting automated USB backup for $DEV"
echo "========================================================================"

mkdir -p "$MOUNT_POINT"

# 1. Mount the drive
echo "[*] Mounting $DEV at $MOUNT_POINT..."
mount "$DEV" "$MOUNT_POINT" || {
    echo "[-] Failed to mount $DEV to $MOUNT_POINT."
    exit 1
}

# Trap exit to guarantee safe unmount and ejection even if error occurs
cleanup() {
    echo "[*] Synchronizing file buffers to disk..."
    sync
    echo "[*] Unmounting $MOUNT_POINT..."
    umount -l "$MOUNT_POINT" 2>/dev/null || true
    echo "[*] Ejecting / powering down external drive $DEV..."
    udisksctl power-off -b "$DEV" 2>/dev/null || eject "$DEV" 2>/dev/null || true
    echo "[+] Safe to unplug drive."
}
trap cleanup EXIT

# 2. Trigger the system backup
echo "[*] Generating system backup via ODtech management command..."
if [ -f "$VENV_PYTHON" ] && [ -d "$PROJECT_DIR" ]; then
    sudo -u server_admin "$VENV_PYTHON" "$PROJECT_DIR/manage.py" backup_db --triggered-by manual
else
    echo "[!] Warning: ODtech project not located at $PROJECT_DIR; looking for existing archives in $BACKUP_DIR"
fi

# 3. Create target directory on external drive
TARGET_DIR="$MOUNT_POINT/odtech_backups"
mkdir -p "$TARGET_DIR"

# 4. Copy latest full backup files
echo "[*] Copying backups to external drive ($TARGET_DIR)..."
LATEST_COMPLETE=$(ls -t "$BACKUP_DIR"/odtech_complete_backup_*.tar.gz 2>/dev/null | head -n 1 || true)
LATEST_SQL=$(ls -t "$BACKUP_DIR"/odtech_db_*.sql.gz 2>/dev/null | head -n 1 || true)

if [ -n "$LATEST_COMPLETE" ]; then
    echo "[+] Copying complete archive: $(basename "$LATEST_COMPLETE")"
    cp -v "$LATEST_COMPLETE" "$TARGET_DIR/"
fi

if [ -n "$LATEST_SQL" ]; then
    echo "[+] Copying DB dump: $(basename "$LATEST_SQL")"
    cp -v "$LATEST_SQL" "$TARGET_DIR/"
fi

# 5. Delete backups older than 30 days on the external drive
echo "[*] Deleting backups older than 30 days from external drive..."
OLD_FILES=$(find "$TARGET_DIR" -type f \( -name '*.tar.gz' -o -name '*.sql.gz' -o -name '*.zip' \) -mtime +30)
if [ -n "$OLD_FILES" ]; then
    echo "$OLD_FILES" | while read -r f; do
        echo "[+] Pruning old backup: $f"
        rm -f "$f"
    done
else
    echo "[+] No backups older than 30 days found."
fi

# Flush changes to disk
sync

# 6. Notification / Message
SUCCESS_MESSAGE="ODtech Backup copied successfully! The drive is safely ejected and can now be unplugged."
echo "========================================================================"
echo "[SUCCESS] $SUCCESS_MESSAGE"
echo "========================================================================"

# Broadcast alert to all active terminal sessions (SSH, local console)
echo "$SUCCESS_MESSAGE" | wall 2>/dev/null || true

# If a desktop user is logged in, send GUI desktop notification
for user_home in /home/*; do
    username=$(basename "$user_home")
    if id -u "$username" >/dev/null 2>&1; then
        uid=$(id -u "$username")
        bus_path="/run/user/$uid/bus"
        if [ -S "$bus_path" ]; then
            sudo -u "$username" DBUS_SESSION_BUS_ADDRESS="unix:path=$bus_path" \
                notify-send -u critical -i drive-removable-media "ODtech Backup" "$SUCCESS_MESSAGE" 2>/dev/null || true
        fi
    fi
done

# Audible terminal bell
echo -en "\007" > /dev/console 2>/dev/null || true


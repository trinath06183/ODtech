#!/usr/bin/env bash
set -e

echo "============================================================"
echo " ODtech ERP: Automated Database Backup Setup"
echo "============================================================"

PROJECT_DIR="/home/server_admin/ODtech"
BACKUP_DIR="/home/server_admin/backups"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"

# 1. Verify / Install PostgreSQL Client
if ! command -v pg_dump >/dev/null 2>&1; then
    echo "[-] pg_dump not found. Installing postgresql-client..."
    sudo apt-get update && sudo apt-get install -y postgresql-client
else
    echo "[+] pg_dump is already installed: $(which pg_dump)"
fi

# 2. Ensure Backup Directory Exists
mkdir -p "$BACKUP_DIR"
chmod 750 "$BACKUP_DIR"
echo "[+] Backup directory ready at: $BACKUP_DIR"

# 3. Configure Crontab for server_admin
echo "[*] Setting up nightly cron jobs..."

TMP_CRON=$(mktemp)
crontab -l 2>/dev/null | grep -v "backup_db" | grep -v "odtech_db_" | grep -v "odtech_complete_" > "$TMP_CRON" || true

cat << 'EOF' >> "$TMP_CRON"
# ODtech Nightly Database Backup at 23:30 IST
30 23 * * * cd /home/server_admin/ODtech && /home/server_admin/ODtech/venv/bin/python manage.py backup_db --triggered-by schedule >> /home/server_admin/backups/cron_backup.log 2>&1
# ODtech Cleanup Backups older than 14 days at 01:00 AM daily
0 1 * * * find /home/server_admin/backups/ -type f \( -name 'odtech_db_*.sql.gz' -o -name 'odtech_complete_*.tar.gz' \) -mtime +14 -delete
EOF

crontab "$TMP_CRON"
rm -f "$TMP_CRON"
echo "[+] Crontab updated successfully:"
crontab -l | grep -E "backup_db|delete"

# 4. Run Manual Backup Test Verification
echo ""
echo "[*] Running verification backup test..."
cd "$PROJECT_DIR"
"$VENV_PYTHON" manage.py backup_db --triggered-by manual

echo ""
echo "[+] Latest files in $BACKUP_DIR:"
ls -lh "$BACKUP_DIR" | tail -n 5

echo ""
echo "============================================================"
echo " [SUCCESS] Automated Database Backups are fully configured!"
echo "============================================================"

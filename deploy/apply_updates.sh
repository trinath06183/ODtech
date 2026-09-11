#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "############################################################"
echo "# Starting ODtech ERP Comprehensive Production Setup"
echo "############################################################"

chmod +x "$SCRIPT_DIR/scripts/"*.sh

echo ""
echo ">>> STEP 1: Setting up Nginx Gzip Compression & Caching..."
"$SCRIPT_DIR/scripts/setup_nginx.sh"

echo ""
echo ">>> STEP 2: Setting up Automated DB Backups & Nightly Cron..."
"$SCRIPT_DIR/scripts/setup_backups.sh"

echo ""
echo ">>> STEP 3: Setting up Logrotate (Log Maintenance)..."
"$SCRIPT_DIR/scripts/setup_logrotate.sh"

echo ""
echo ">>> STEP 4: Configuring UFW Firewall (SSH + Web + Tailscale)..."
"$SCRIPT_DIR/scripts/setup_ufw.sh"

echo ""
echo ">>> STEP 5: Restarting Application Service..."
FOUND_SERVICE=""
for s in odtech odtech-erp gunicorn django erp; do
    if systemctl is-active --quiet "$s" 2>/dev/null; then
        FOUND_SERVICE="$s"
        break
    fi
done

if [ -n "$FOUND_SERVICE" ]; then
    echo "[+] Found active service: $FOUND_SERVICE. Restarting..."
    sudo systemctl restart "$FOUND_SERVICE"
    echo "[+] Service $FOUND_SERVICE restarted successfully."
else
    echo "[!] No standard service name found (tried odtech, odtech-erp, gunicorn, django, erp)."
    echo "[*] If Gunicorn runs under a custom service name, check with: systemctl list-units --type=service | grep -iE 'odtech|gunicorn|django'"
fi

echo ""
echo ">>> STEP 6: Verifying Health Check Endpoint (/healthz)..."
curl -s http://127.0.0.1/healthz/ || curl -s http://127.0.0.1/health/ || true
echo ""

echo ""
echo ">>> STEP 7: Google Drive Backup Status..."
"$SCRIPT_DIR/scripts/setup_google_drive.sh"

echo ""
echo "############################################################"
echo "# [DONE] All Production Enhancements have been applied!"
echo "############################################################"

#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "############################################################"
echo "# Starting ODtech ERP Deployment Maintenance (Items 3 & 4)"
echo "############################################################"

chmod +x "$SCRIPT_DIR/scripts/setup_nginx.sh"
chmod +x "$SCRIPT_DIR/scripts/setup_backups.sh"

echo ""
echo ">>> STEP 1: Setting up Nginx Gzip Compression & Caching..."
"$SCRIPT_DIR/scripts/setup_nginx.sh"

echo ""
echo ">>> STEP 2: Setting up Automated DB Backups & Nightly Cron..."
"$SCRIPT_DIR/scripts/setup_backups.sh"

echo ""
echo ">>> STEP 3: Restarting Gunicorn to apply updated scheduler..."
sudo systemctl restart gunicorn

echo ""
echo "############################################################"
echo "# [DONE] Both Items 3 and 4 have been successfully deployed!"
echo "############################################################"

#!/usr/bin/env bash
set -e

echo "============================================================"
echo " ODtech ERP: Google Drive Cloud Backup Setup"
echo "============================================================"

PROJECT_DIR="/home/server_admin/ODtech"
ENV_FILE="$PROJECT_DIR/.env"
CREDS_FILE="$PROJECT_DIR/google_drive_credentials.json"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"

echo "To enable automated Google Drive backups:"
echo " 1. Create a Google Cloud Service Account with Google Drive API enabled."
echo " 2. Download the JSON key file and save it as: $CREDS_FILE"
echo " 3. Share your target Google Drive folder with the service account email (as Editor)."
echo " 4. Add GOOGLE_DRIVE_FOLDER_ID to your .env file."
echo ""

if [ ! -f "$CREDS_FILE" ]; then
    echo "[-] $CREDS_FILE was not found."
    echo "[!] To complete this step later:"
    echo "    1) Copy your service account JSON file to $CREDS_FILE"
    echo "    2) Add to $ENV_FILE:"
    echo "         GOOGLE_DRIVE_ENABLED=true"
    echo "         GOOGLE_DRIVE_FOLDER_ID=your_google_drive_folder_id"
    echo "         GOOGLE_DRIVE_CREDENTIALS_PATH=$CREDS_FILE"
    echo "    3) Re-run this script: bash deploy/scripts/setup_google_drive.sh"
    exit 0
fi

echo "[+] Found credentials at $CREDS_FILE."

# Ensure GOOGLE_DRIVE_ENABLED=true in .env
if grep -q "GOOGLE_DRIVE_ENABLED" "$ENV_FILE"; then
    sed -i 's/GOOGLE_DRIVE_ENABLED=.*/GOOGLE_DRIVE_ENABLED=true/' "$ENV_FILE"
else
    echo "GOOGLE_DRIVE_ENABLED=true" >> "$ENV_FILE"
fi

if ! grep -q "GOOGLE_DRIVE_CREDENTIALS_PATH" "$ENV_FILE"; then
    echo "GOOGLE_DRIVE_CREDENTIALS_PATH=$CREDS_FILE" >> "$ENV_FILE"
fi

echo "[*] Testing complete backup with Google Drive upload..."
cd "$PROJECT_DIR"
"$VENV_PYTHON" manage.py backup_db --triggered-by manual

echo ""
echo "============================================================"
echo " [SUCCESS] Google Drive Cloud Backup configured!"
echo "============================================================"

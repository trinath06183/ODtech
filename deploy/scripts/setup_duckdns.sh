#!/usr/bin/env bash
set -e

echo "============================================================"
echo " ODtech ERP: DuckDNS Dynamic Domain Setup"
echo "============================================================"

DUCK_DIR="/home/server_admin/duckdns"
DUCK_SCRIPT="$DUCK_DIR/duck.sh"

echo "Step 1: Sign in at https://www.duckdns.org (via Google or GitHub)."
echo "Step 2: Create your free subdomain (e.g., 'odtech' -> odtech.duckdns.org)."
echo "Step 3: Copy your account TOKEN from the top of the DuckDNS page."
echo ""

# Accept arguments if passed, otherwise prompt
DOMAIN="$1"
TOKEN="$2"

if [ -z "$DOMAIN" ]; then
    read -p "Enter your DuckDNS subdomain name (without .duckdns.org): " DOMAIN
fi

if [ -z "$TOKEN" ]; then
    read -p "Enter your DuckDNS Token: " TOKEN
fi

# Clean inputs
DOMAIN=$(echo "$DOMAIN" | tr -d '[:space:]' | sed 's/\.duckdns\.org$//')
TOKEN=$(echo "$TOKEN" | tr -d '[:space:]')

if [ -z "$DOMAIN" ] || [ -z "$TOKEN" ]; then
    echo "[-] Error: Subdomain name and Token are required."
    exit 1
fi

mkdir -p "$DUCK_DIR"

cat << EOF > "$DUCK_SCRIPT"
#!/bin/bash
echo url="https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=" | curl -s -k -o ${DUCK_DIR}/duck.log -K -
EOF

chmod 700 "$DUCK_SCRIPT"

# Add cron job to update IP every 5 minutes
echo "[*] Adding 5-minute IP sync cron job..."
TMP_CRON=$(mktemp)
crontab -l 2>/dev/null | grep -v "duckdns" > "$TMP_CRON" || true
echo "*/5 * * * * ${DUCK_SCRIPT} >/dev/null 2>&1" >> "$TMP_CRON"
crontab "$TMP_CRON"
rm -f "$TMP_CRON"

# Test run
echo "[*] Testing initial IP update to DuckDNS..."
"$DUCK_SCRIPT"
RESULT=$(cat "${DUCK_DIR}/duck.log" 2>/dev/null || echo "")

echo ""
if [ "$RESULT" = "OK" ]; then
    echo "[+] SUCCESS: DuckDNS responded with OK!"
    echo "[+] Your domain https://${DOMAIN}.duckdns.org is now active and pointed to your IP!"
else
    echo "[-] Warning: DuckDNS response was: '$RESULT' (Expected: OK)."
    echo "[-] Please double-check your Token and Subdomain name."
fi

echo ""
echo "============================================================"
echo " Next: Automatic SSL Certificate with Let's Encrypt (Certbot)"
echo "============================================================"
echo "To secure https://${DOMAIN}.duckdns.org with a free SSL certificate:"
echo " 1. Ensure ports 80 and 443 are forwarded to this server on your router."
echo " 2. Run: sudo apt-get install -y certbot python3-certbot-nginx"
echo " 3. Run: sudo certbot --nginx -d ${DOMAIN}.duckdns.org"
echo "============================================================"

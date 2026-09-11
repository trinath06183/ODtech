#!/usr/bin/env bash
set -e

echo "============================================================"
echo " ODtech ERP: Nginx Compression & Static Caching Setup"
echo "============================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"
NGINX_CONF_SRC="$DEPLOY_DIR/nginx/odtech_compression.conf"
NGINX_CONF_DEST="/etc/nginx/conf.d/odtech_compression.conf"

# 1. Install Gzip compression config
echo "[*] Installing Gzip compression configuration to $NGINX_CONF_DEST..."
sudo cp "$NGINX_CONF_SRC" "$NGINX_CONF_DEST"
sudo chmod 644 "$NGINX_CONF_DEST"

# 2. Ensure /etc/nginx/nginx.conf has gzip on enabled
sudo sed -i 's/# gzip_vary on;/gzip_vary on;/' /etc/nginx/nginx.conf 2>/dev/null || true
sudo sed -i 's/# gzip_proxied any;/gzip_proxied any;/' /etc/nginx/nginx.conf 2>/dev/null || true
sudo sed -i 's/# gzip_comp_level 6;/gzip_comp_level 6;/' /etc/nginx/nginx.conf 2>/dev/null || true
sudo sed -i 's/# gzip_buffers 16 8k;/gzip_buffers 16 8k;/' /etc/nginx/nginx.conf 2>/dev/null || true
sudo sed -i 's/# gzip_http_version 1.1;/gzip_http_version 1.1;/' /etc/nginx/nginx.conf 2>/dev/null || true

# 3. Test Nginx configuration
echo "[*] Testing Nginx configuration..."
sudo nginx -t

# 4. Reload Nginx
echo "[*] Reloading Nginx service..."
sudo systemctl reload nginx

# 5. Verify Gzip output
echo ""
echo "[*] Verifying compression headers on local endpoint..."
curl -s -I -H "Accept-Encoding: gzip" http://127.0.0.1/static/admin/css/base.css | grep -iE "content-encoding|cache-control|content-type" || true

echo ""
echo "============================================================"
echo " [SUCCESS] Nginx Compression & Caching is fully configured!"
echo "============================================================"

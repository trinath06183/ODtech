#!/usr/bin/env bash
set -e

echo "============================================================"
echo " ODtech ERP: DuckDNS DNS-01 SSL Certificate Setup"
echo "============================================================"

DOMAIN="odtech"
TOKEN="2d18056c-8044-4696-b567-4689ebbb7090"
EMAIL="bn06183@gmail.com"
FQDN="${DOMAIN}.duckdns.org"

# 1. Ensure A Record is updated on DuckDNS
echo "[*] Ensuring A Record is refreshed on DuckDNS..."
UPDATE_RESP=$(curl -s "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}")
echo "[+] DuckDNS A Record response: $UPDATE_RESP"

# Check resolution
echo "[*] Testing DNS resolution for $FQDN..."
host "$FQDN" || ping -c 1 "$FQDN" || true

# 2. Issue Certificate via DNS-01 challenge (Bypasses port 80/443 router restrictions!)
echo ""
echo "[*] Requesting SSL Certificate from Let's Encrypt via DNS-01 challenge..."
sudo certbot certonly \
  --manual \
  --preferred-challenges dns \
  --manual-auth-hook "curl -s 'https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&txt='\$CERTBOT_VALIDATION && sleep 30" \
  --manual-cleanup-hook "curl -s 'https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&clear=true'" \
  -d "$FQDN" \
  --non-interactive \
  --agree-tos \
  -m "$EMAIL"

# 3. Configure Nginx with the newly issued certificate
echo ""
echo "[*] Configuring Nginx with SSL certificate..."
SSL_CERT="/etc/letsencrypt/live/${FQDN}/fullchain.pem"
SSL_KEY="/etc/letsencrypt/live/${FQDN}/privkey.pem"

if sudo test -f "$SSL_CERT" && sudo test -f "$SSL_KEY"; then
    echo "[+] Found issued certificate at $SSL_CERT"

    # Install SSL configuration in Nginx
    sudo bash -c "cat > /etc/nginx/conf.d/odtech_ssl.conf << 'EOF'
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name ${FQDN};

    ssl_certificate ${SSL_CERT};
    ssl_certificate_key ${SSL_KEY};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    client_max_body_size 50M;

    location /static/ {
        alias /home/server_admin/ODtech/static/;
        expires 30d;
        add_header Cache-Control 'public, max-age=2592000, immutable';
        access_log off;
    }

    location /media/ {
        alias /home/server_admin/ODtech/media/;
        expires 7d;
        add_header Cache-Control 'public, max-age=604800';
        access_log off;
    }

    location / {
        limit_req zone=req_limit_per_ip burst=20 nodelay;
        limit_req_status 429;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 120s;
        proxy_read_timeout 120s;
    }
}
EOF"

    sudo nginx -t
    sudo systemctl reload nginx
    echo ""
    echo "============================================================"
    echo " [SUCCESS] SSL Certificate is installed and active!"
    echo " Access your ERP securely at: https://${FQDN}"
    echo "============================================================"
else
    echo "[-] Error: Certificate files were not found."
fi

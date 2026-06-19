#!/bin/sh
# ============================================================
# Obtain SSL certificate via DNS-01 challenge (Cloudflare)
# This works behind Cloudflare proxy (orange cloud) without issues.
#
# Prerequisites:
#   - /etc/letsencrypt/cloudflare.ini with your API token (see cloudflare.ini.example)
#   - File MUST have permissions 600: chmod 600 /etc/letsencrypt/cloudflare.ini
#
# Usage on the VPS:
#   bash certbot/obtain-cert.sh
# ============================================================

set -e

DOMAIN="${DOMAIN:-ayceventos.com.co}"
EMAIL="${CERTBOT_EMAIL:-info@ayceventos.com.co}"
CRED_FILE="/etc/letsencrypt/cloudflare.ini"

echo "=== Obtain SSL certificate (DNS-01 / Cloudflare) ==="
echo "Domain: $DOMAIN"

# Check credentials file
if [ ! -f "$CRED_FILE" ]; then
    echo "ERROR: $CRED_FILE not found."
    echo ""
    echo "Create it with:"
    echo "  sudo cp certbot/cloudflare.ini.example $CRED_FILE"
    echo "  sudo nano $CRED_FILE"
    echo "  sudo chmod 600 $CRED_FILE"
    exit 1
fi

# Run certbot with Cloudflare DNS plugin (standalone, no docker needed)
docker run --rm \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v /var/www/certbot:/var/www/certbot \
    $(docker build -q ./certbot 2>/dev/null | xargs -I{} echo {}) \
    certbot certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
    --dns-cloudflare-propagation-seconds 30 \
    -d "$DOMAIN" \
    -d "www.$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --non-interactive

echo ""
echo "✅ Certificate obtained for $DOMAIN"
echo "   Path: /etc/letsencrypt/live/$DOMAIN/"
echo ""
echo "Now you can set Cloudflare SSL/TLS mode to 'Full (strict)'"
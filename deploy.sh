#!/bin/bash
# ============================================================
# Deploy script — ayceventos.com.co
# Run on the VPS: bash deploy.sh
# ============================================================

set -e

DOMAIN="ayceventos.com.co"
EMAIL="${CERTBOT_EMAIL:-admin@ayceventos.com.co}"

echo "=== Logistica Deploy — $DOMAIN ==="

# 1. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "Log out and back in for Docker group, then re-run this script."
    exit 0
fi

# 2. Clone repo if not already
if [ ! -d "/opt/logistica" ]; then
    echo "Cloning repository..."
    git clone https://github.com/ElSantiago31/logistica.git /opt/logistica
fi

cd /opt/logistica

# 3. Pull latest code
echo "Pulling latest code..."
git pull origin master

# 4. Create .env if not exists
if [ ! -f ".env" ]; then
    echo "Creating .env from example..."
    cp .env.example .env
    DB_PASS=$(openssl rand -hex 16)
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s/CHANGE_ME_STRONG_PASSWORD/$DB_PASS/g" .env
    sed -i "s/CHANGE_ME_GENERATE_WITH_openssl_rand_hex_32/$JWT_SECRET/g" .env
    sed -i "s/yourdomain.com/$DOMAIN/g" .env
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://logistica:$DB_PASS@postgres:5432/logistica|" .env
    echo ".env created with generated secrets. Edit to add WhatsApp credentials."
fi

# 5. Get SSL certificate if not exists
if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    echo "Getting SSL certificate for $DOMAIN..."
    mkdir -p /var/www/certbot
    docker run --rm \
        -v /etc/letsencrypt:/etc/letsencrypt \
        -v /var/www/certbot:/var/www/certbot \
        certbot/certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        -d $DOMAIN \
        -d www.$DOMAIN \
        --email $EMAIL \
        --agree-tos \
        --non-interactive
    echo "SSL certificate obtained"
fi

# 6. Build and start services
echo "Building and starting services..."
docker compose -f docker-compose.prod.yml up -d --build

# 7. Run migrations
echo "Running migrations..."
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head

# 8. Seed initial data
echo "Seeding initial data..."
docker compose -f docker-compose.prod.yml exec backend python -m scripts.seed

echo ""
echo "=========================================="
echo "Deploy complete!"
echo "Site: https://$DOMAIN"
echo "Admin: https://$DOMAIN/admin/login"
echo "=========================================="
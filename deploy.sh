#!/bin/bash
# ============================================================
# Deploy script — ayceventos.com.co
# Run on the VPS: bash deploy.sh
# ============================================================

set -e

DOMAIN="${DOMAIN:-ayceventos.com.co}"
EMAIL="${CERTBOT_EMAIL:-admin@ayceventos.com.co}"
REPO_DIR="/opt/logistica"

echo "=== Logistica Deploy — $DOMAIN ==="

# 1. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "==> Log out and back in for Docker group, then re-run this script."
    exit 0
fi

# 2. Clone repo if not already
if [ ! -d "$REPO_DIR" ]; then
    echo "Cloning repository..."
    git clone https://github.com/ElSantiago31/logistica.git "$REPO_DIR"
fi

cd "$REPO_DIR"

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
    sed -i "s|DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://logistica:$DB_PASS@postgres:5432/logistica|" .env
    echo ".env created with generated secrets."
    echo "==> Edit .env to add WhatsApp/Zenvia credentials before final deploy."
fi

# 5. Create SSL dirs
sudo mkdir -p /etc/letsencrypt /var/www/certbot

# 6. Obtain SSL certificate (two-phase: HTTP-only nginx, then full nginx)
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "=== Phase 1: Obtain SSL certificate ==="

    # Start postgres + backend only (no nginx yet)
    docker compose -f docker-compose.prod.yml up -d postgres backend

    # Wait for backend health
    echo "Waiting for backend to be healthy..."
    sleep 20

    # Run certbot standalone (uses port 80 directly)
    docker run --rm \
        -p 80:80 \
        -v /etc/letsencrypt:/etc/letsencrypt \
        -v /var/www/certbot:/var/www/certbot \
        certbot/certbot certonly \
        --standalone \
        -d $DOMAIN \
        -d www.$DOMAIN \
        --email $EMAIL \
        --agree-tos \
        --non-interactive
    echo "SSL certificate obtained for $DOMAIN"
else
    echo "SSL certificate already exists, skipping certbot."
fi

# 7. Build and start ALL services (nginx can now find certs)
echo "=== Phase 2: Build and start all services ==="
docker compose -f docker-compose.prod.yml up -d --build

# Wait for services to start
echo "Waiting for services to start..."
sleep 15

# 8. Migrations + seed already handled by entrypoint.sh, but verify
echo "=== Verifying migrations & seed ==="
docker compose -f docker-compose.prod.yml exec -T backend alembic current || \
    docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec -T backend python -m scripts.seed || true

echo ""
echo "=========================================="
echo "Deploy complete!"
echo "Site:  https://$DOMAIN"
echo "Admin: https://$DOMAIN/admin/login"
echo "Login: admin@logistica.com / Admin123!"
echo "=========================================="
echo ""
echo "IMPORTANT: Change the admin password after first login!"
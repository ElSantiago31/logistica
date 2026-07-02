#!/bin/sh
# Docker entrypoint: espera DB, corre migraciones y arranca uvicorn
set -e

echo "=== Waiting for PostgreSQL ==="
# Esperar hasta 30s a que Postgres acepte conexiones
for i in $(seq 1 30); do
    python -c "
import asyncio, asyncpg, os
async def check():
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            database=os.getenv('POSTGRES_DB', 'logistica'),
            user=os.getenv('POSTGRES_USER', 'logistica'),
            password=os.getenv('POSTGRES_PASSWORD', 'logistica_dev_2024'),
        )
        await conn.close()
        return True
    except Exception:
        return False
ok = asyncio.run(check())
exit(0 if ok else 1)
" && break
    echo "  PostgreSQL not ready, retry ${i}/30..."
    sleep 1
done

echo "=== Running Alembic migrations ==="
alembic upgrade head

echo "=== Running initial seed ==="
python -m scripts.seed || echo "Seed skipped (may already exist)"

echo "=== Starting uvicorn ==="
# ⚠️ workers=1 es OBLIGATORIO para WebSockets (ConnectionManager en memoria).
#    Con >1 worker, los mensajes WS se pierden entre procesos.
#    Para escalar, migrar el manager a Redis pub/sub en el futuro.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

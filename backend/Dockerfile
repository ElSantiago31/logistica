# ============================================================
# Multi-stage Dockerfile — Logistica A&C Eventos
#
# Stage 1 (js-builder): Minifica assets JS con Terser (Node.js)
# Stage 2 (runtime):    App Python (FastAPI + uvicorn + LibreOffice)
#
# El build context debe ser la RAÍZ del repo (context: .) para que
# Stage 1 pueda acceder a frontend/js/ y frontend/build.js.
# ============================================================

# ---- Stage 1: JS minification + Tailwind CSS build ----
FROM node:20-alpine AS js-builder
WORKDIR /build

# Instalar deps (Terser + Tailwind). IMPORTANTE: son devDependencies, así que
# NO usar --production (excluiría devDeps). En un stage de BUILD se necesitan
# las herramientas de build. --include=dev asegura instalarlas sin importar NODE_ENV.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --include=dev --no-audit --no-fund

# Copiar build script y código fuente JS
COPY frontend/build.js ./
COPY frontend/js ./js

# Copiar config de Tailwind y CSS de entrada
COPY frontend/tailwind.config.js frontend/tailwind.input.css ./

# Copiar templates HTML (fuente para el purge de Tailwind).
# tailwind.config.js apunta a './templates/**/*.html' (relativo a /build).
COPY backend/app/templates ./templates

# Crear directorio public/ (Tailwind no lo crea solo)
RUN mkdir -p public

# Ejecutar build: genera js/*.min.js (Terser) + public/tailwind.css (Tailwind)
RUN node build.js && ls -la js/ && ls -la public/

# ---- Stage 2: Python runtime ----
FROM python:3.11-slim

WORKDIR /app

# System deps + LibreOffice (para conversión XLSX → PDF de planillas)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    libreoffice-calc \
    libreoffice-core && \
    rm -rf /var/lib/apt/lists/*

# Python deps (cache layer: solo se reinstala si cambia requirements.txt)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code (todo el contenido de backend/ → /app/)
COPY backend/ .

# Frontend JS completo (fuente única): *.js originales + *.min.js (Stage 1).
# En desarrollo local, main.py sirve desde frontend/js/ en la raíz del repo.
# En Docker, copiamos frontend/js/ completa para mantener consistencia.
COPY frontend/js/ /app/frontend/js/

# Sobreescribir/asegurar *.min.js desde Stage 1 (siempre frescos del build).
COPY --from=js-builder /build/js/*.min.js /app/frontend/js/

# Tailwind CSS compilado en Stage 1 (purge automático, minificado).
# Se sirve en /static/frontend/tailwind.css (montado en main.py).
COPY --from=js-builder /build/public/tailwind.css /app/frontend/public/tailwind.css

# Entrypoint permissions
RUN chmod +x /app/entrypoint.sh

# Create data dirs (StaticFiles requiere que existan en build time)
RUN mkdir -p /app/data/photos/thumbnails /app/data/rut

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
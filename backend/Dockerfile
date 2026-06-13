FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Entrypoint permissions
RUN chmod +x /app/entrypoint.sh

# Create data dirs
RUN mkdir -p /app/data/photos/thumbnails

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
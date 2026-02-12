FROM python:3.12-slim

# Install PostgreSQL client for pg_dump
RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application modules
COPY scraper.py database.py dump_manager.py main.py ./

# .env is NOT baked into the image — supply credentials via
# env_file: .env  in docker-compose.yml (file stays on the host, out of the image)

# Dumps volume mount point (actual data lands on the named volume)
RUN mkdir -p /dumps

CMD ["python", "main.py"]
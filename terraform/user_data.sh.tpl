#!/bin/bash
set -euxo pipefail

# --- Docker + compose plugin (Amazon Linux 2023) -----------------------------
dnf install -y docker
systemctl enable --now docker

mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-x86_64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# --- App stack ----------------------------------------------------------------
mkdir -p /opt/taskflow
cat > /opt/taskflow/docker-compose.yml <<COMPOSE
services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: taskflow
      POSTGRES_PASSWORD: ${db_password}
      POSTGRES_DB: taskflow
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U taskflow -d taskflow"]
      interval: 5s
      timeout: 3s
      retries: 10

  api:
    image: ${app_image}
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    environment:
      TASKFLOW_ENVIRONMENT: production
      TASKFLOW_DATABASE_URL: postgresql+psycopg://taskflow:${db_password}@db:5432/taskflow
      TASKFLOW_JWT_SECRET: ${jwt_secret}
    ports:
      - "8000:8000"
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"
    logging:
      driver: awslogs
      options:
        awslogs-region: ${aws_region}
        awslogs-group: ${log_group}
        awslogs-stream: api

volumes:
  pgdata:
COMPOSE

docker compose -f /opt/taskflow/docker-compose.yml up -d

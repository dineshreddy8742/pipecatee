#!/bin/bash
set -e

# Set environment variables for the application
export DATABASE_URL="postgresql+asyncpg://dograh:dineshadmissionspassword123@localhost:5432/dograh"
export REDIS_URL="redis://localhost:6379"
export PYTHONPATH=/app

echo "Starting PostgreSQL..."
mkdir -p /var/run/postgresql
chown -R postgres:postgres /var/run/postgresql
chown -R postgres:postgres /var/lib/postgresql

# Start Postgres service
service postgresql start

# Wait for Postgres to start
until pg_isready -h localhost -p 5432; do
  echo "Waiting for Postgres to start..."
  sleep 1
done

echo "Setting up Postgres Database and Permissions..."
su - postgres -c "psql -c \"CREATE DATABASE dograh;\"" || true
su - postgres -c "psql -c \"CREATE USER dograh WITH PASSWORD 'dineshadmissionspassword123';\"" || true
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE dograh TO dograh;\"" || true

echo "Starting Redis Server..."
service redis-server start

echo "Configuring Asterisk..."
mkdir -p /etc/asterisk
cp -R /app/config/asterisk/* /etc/asterisk/
chown -R asterisk:asterisk /etc/asterisk

# Start Asterisk in background
echo "Starting Asterisk..."
asterisk

echo "Running Alembic Database Migrations..."
cd /app
python -m alembic -c /app/api/alembic.ini upgrade head || true

echo "Starting FastAPI Uvicorn Application on port 7860..."
exec uvicorn api.app:app --host 0.0.0.0 --port 7860

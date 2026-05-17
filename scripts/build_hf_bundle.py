import os
import shutil

SOURCE_DIR = "C:\\dd\\temp_dograh"
TARGET_DIR = "C:\\dd\\temp_dograh_hf"

def main():
    print(f"Creating Hugging Face deployment folder at: {TARGET_DIR}")
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
    else:
        # Clear old files but preserve the .git, .github and README.md repository configurations!
        for item in os.listdir(TARGET_DIR):
            if item in (".git", ".github", "README.md"):
                continue
            item_path = os.path.join(TARGET_DIR, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
            else:
                try:
                    os.remove(item_path)
                except Exception:
                    pass

    # Copy source folders (skipping binary assets)
    folders_to_copy = ["api", "config", "scripts", "pipecat"]
    for folder in folders_to_copy:
        src = os.path.join(SOURCE_DIR, folder)
        dst = os.path.join(TARGET_DIR, folder)
        if os.path.exists(src):
            print(f"Copying {folder}...")
            shutil.copytree(src, dst)

    # Delete unused pipecat examples folder to prevent large/binary files from triggering LFS
    examples_path = os.path.join(TARGET_DIR, "pipecat", "examples")
    if os.path.exists(examples_path):
        print("Removing pipecat/examples directory...")
        shutil.rmtree(examples_path, ignore_errors=True)

    # Clean binary files from target folder to prevent Hugging Face Git rejections
    for root, dirs, files in os.walk(TARGET_DIR):
        for file in files:
            if file.endswith((".wav", ".so", ".so.0", ".so.0.4.1", ".png", ".jpg", ".jpeg", ".gif", ".mp3", ".onnx")):
                file_path = os.path.join(root, file)
                print(f"Removing binary file to prevent Hugging Face rejection: {file_path}")
                os.remove(file_path)

    # Copy root level files if they exist
    files_to_copy = ["alembic.ini", "requirements.txt"]
    for file in files_to_copy:
        src = os.path.join(SOURCE_DIR, file)
        dst = os.path.join(TARGET_DIR, file)
        if os.path.exists(src):
            shutil.copy(src, dst)

    # 1. Write the custom Hugging Face Dockerfile (downloads rnnoise from GitHub!)
    dockerfile_content = """FROM ubuntu:22.04

# Avoid interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies (including compilation tools and deadsnakes PPA for Python 3.12!)
RUN apt-get update && apt-get install -y \\
    software-properties-common \\
    curl \\
    git \\
    procps \\
    && add-apt-repository ppa:deadsnakes/ppa \\
    && apt-get update && apt-get install -y \\
    python3.12 \\
    python3.12-dev \\
    postgresql \\
    postgresql-contrib \\
    postgresql-server-dev-14 \\
    make \\
    gcc \\
    redis-server \\
    asterisk \\
    libgl1 \\
    libglib2.0-0 \\
    && rm -rf /var/lib/apt/lists/*

# Compile and install pgvector extension from source (extremely fast and 100% reliable!)
RUN git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git /tmp/pgvector \\
    && cd /tmp/pgvector \\
    && make \\
    && make install \\
    && rm -rf /tmp/pgvector

# Set up working directory
WORKDIR /app

# Link python and python3 to python3.12
RUN ln -sf /usr/bin/python3.12 /usr/bin/python3 \\
    && ln -sf /usr/bin/python3.12 /usr/bin/python

# Copy requirement files first for caching
COPY ./api/requirements.txt /app/api/requirements.txt

# Ensure pip is installed for Python 3.12 and install requirements
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 \\
    && python3.12 -m pip install --no-cache-dir -r /app/api/requirements.txt

# Copy application code (including local pipecat folder!)
COPY . /app

# Install the custom local pipecat framework with all required integration extras
RUN python3.12 -m pip install --no-cache-dir "/app/pipecat[deepgram,google,groq,sarvam,speechmatics,assemblyai,gladia,aws,azure,cartesia,elevenlabs,rime,openai,webrtc]"

# Expose Hugging Face Space default port
EXPOSE 7860

# Securely download the precompiled rnnoise binary and ONNX models during the build!
RUN mkdir -p /app/api/native/rnnoise \\
    && curl -L https://raw.githubusercontent.com/dineshreddy8742/pipecatee/main/api/native/rnnoise/librnnoise.so.0.4.1 -o /app/api/native/rnnoise/librnnoise.so.0.4.1 \\
    && ln -s /app/api/native/rnnoise/librnnoise.so.0.4.1 /app/api/native/rnnoise/librnnoise.so \\
    && ln -s /app/api/native/rnnoise/librnnoise.so.0.4.1 /app/api/native/rnnoise/librnnoise.so.0 \\
    && mkdir -p /app/pipecat/src/pipecat/audio/vad/data \\
    && curl -L https://raw.githubusercontent.com/pipecat-ai/pipecat/main/src/pipecat/audio/vad/data/silero_vad.onnx -o /app/pipecat/src/pipecat/audio/vad/data/silero_vad.onnx \\
    && mkdir -p /app/pipecat/src/pipecat/audio/turn/smart_turn/data \\
    && curl -L https://raw.githubusercontent.com/pipecat-ai/pipecat/main/src/pipecat/audio/turn/smart_turn/data/smart-turn-v3.2-cpu.onnx -o /app/pipecat/src/pipecat/audio/turn/smart_turn/data/smart-turn-v3.2-cpu.onnx

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
"""
    with open(os.path.join(TARGET_DIR, "Dockerfile"), "w") as f:
        f.write(dockerfile_content)

    # 2. Write the custom Hugging Face entrypoint.sh
    entrypoint_content = """#!/bin/bash
set -e

# Set environment variables for the application
export DATABASE_URL="postgresql+asyncpg://dograh:dineshadmissionspassword123@localhost:5432/dograh"
export REDIS_URL="redis://localhost:6379"
export PYTHONPATH=/app

# Default storage configuration for FastAPI startup validation
export MINIO_ENDPOINT="localhost:9000"
export MINIO_PUBLIC_ENDPOINT="http://localhost:9000"
export MINIO_ACCESS_KEY="minioadmin"
export MINIO_SECRET_KEY="minioadmin"
export MINIO_BUCKET="voice-audio"

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
su - postgres -c "psql -c \\"CREATE DATABASE dograh;\\"" || true
su - postgres -c "psql -c \\"CREATE USER dograh WITH PASSWORD 'dineshadmissionspassword123';\\"" || true
su - postgres -c "psql -c \\"GRANT ALL PRIVILEGES ON DATABASE dograh TO dograh;\\"" || true
su - postgres -c "psql -d dograh -c \\"CREATE EXTENSION IF NOT EXISTS vector;\\"" || true

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

echo "Auto-updating Asterisk ARI telephony configurations to correct local credentials..."
su - postgres -c "psql -d dograh" << 'EOF' || true
UPDATE telephony_configurations SET credentials = '{"ari_endpoint": "http://localhost:8088", "app_name": "dograh", "app_password": "dineshadmissionspassword123", "ws_client_name": "dograh"}'::json, updated_at = NOW() WHERE provider = 'ari';
EOF

echo "Starting FastAPI Uvicorn Application on port 7860..."
exec uvicorn api.app:app --host 0.0.0.0 --port 7860
"""
    # Write entrypoint.sh with Unix line endings
    with open(os.path.join(TARGET_DIR, "entrypoint.sh"), "wb") as f:
        f.write(entrypoint_content.encode('utf-8').replace(b'\r\n', b'\n'))

    print("Hugging Face deployment bundle built successfully at C:\\dd\\temp_dograh_hf!")

if __name__ == "__main__":
    main()

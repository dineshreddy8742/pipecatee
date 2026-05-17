FROM python:3.12-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql \
    postgresql-contrib \
    redis-server \
    asterisk \
    curl \
    git \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Copy requirement files first for caching
COPY ./api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt

# Copy application code
COPY . /app

# Expose Hugging Face Space default port
EXPOSE 7860

# Securely download the precompiled rnnoise binary from your GitHub repository during the build!
RUN mkdir -p /app/api/native/rnnoise \
    && curl -L https://raw.githubusercontent.com/dineshreddy8742/pipecatee/main/api/native/rnnoise/librnnoise.so.0.4.1 -o /app/api/native/rnnoise/librnnoise.so.0.4.1 \
    && ln -s /app/api/native/rnnoise/librnnoise.so.0.4.1 /app/api/native/rnnoise/librnnoise.so \
    && ln -s /app/api/native/rnnoise/librnnoise.so.0.4.1 /app/api/native/rnnoise/librnnoise.so.0

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

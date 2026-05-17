FROM ubuntu:22.04

# Avoid interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies (including deadsnakes PPA for Python 3.12!)
RUN apt-get update && apt-get install -y \
    software-properties-common \
    curl \
    git \
    procps \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.12 \
    python3.12-dev \
    postgresql \
    postgresql-contrib \
    redis-server \
    asterisk \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Link python and python3 to python3.12
RUN ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

# Copy requirement files first for caching
COPY ./api/requirements.txt /app/api/requirements.txt

# Ensure pip is installed for Python 3.12 and install requirements
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 \
    && python3.12 -m pip install --no-cache-dir -r /app/api/requirements.txt

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

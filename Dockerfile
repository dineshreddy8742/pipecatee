FROM ubuntu:22.04

# Avoid interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies (including compilation tools and deadsnakes PPA for Python 3.12!)
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
    postgresql-server-dev-14 \
    make \
    gcc \
    redis-server \
    asterisk \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Compile and install pgvector extension from source (extremely fast and 100% reliable!)
RUN git clone --branch v0.5.1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make \
    && make install \
    && rm -rf /tmp/pgvector

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

# Copy application code (including local pipecat folder!)
COPY . /app

# Install the custom local pipecat framework with all required integration extras
RUN python3.12 -m pip install --no-cache-dir "/app/pipecat[deepgram,google,groq,sarvam,speechmatics,assemblyai,gladia,aws,azure,cartesia,elevenlabs,rime,openai,webrtc]"

# Expose Hugging Face Space default port
EXPOSE 7860

# Securely download the precompiled rnnoise binary and ONNX models during the build!
RUN mkdir -p /app/api/native/rnnoise \
    && curl -L https://raw.githubusercontent.com/dineshreddy8742/pipecatee/main/api/native/rnnoise/librnnoise.so.0.4.1 -o /app/api/native/rnnoise/librnnoise.so.0.4.1 \
    && ln -s /app/api/native/rnnoise/librnnoise.so.0.4.1 /app/api/native/rnnoise/librnnoise.so \
    && ln -s /app/api/native/rnnoise/librnnoise.so.0.4.1 /app/api/native/rnnoise/librnnoise.so.0 \
    && mkdir -p /app/pipecat/src/pipecat/audio/vad/data \
    && curl -L https://raw.githubusercontent.com/pipecat-ai/pipecat/main/src/pipecat/audio/vad/data/silero_vad.onnx -o /app/pipecat/src/pipecat/audio/vad/data/silero_vad.onnx \
    && mkdir -p /app/pipecat/src/pipecat/audio/turn/smart_turn/data \
    && curl -L https://raw.githubusercontent.com/pipecat-ai/pipecat/main/src/pipecat/audio/turn/smart_turn/data/smart-turn-v3.2-cpu.onnx -o /app/pipecat/src/pipecat/audio/turn/smart_turn/data/smart-turn-v3.2-cpu.onnx

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]

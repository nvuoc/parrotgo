# ==============================================================================
# ParrotGo LiveKit Voice Agent Worker Dockerfile
# ==============================================================================
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install Linux system dependencies required for WebRTC, Audio, and C++ builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ffmpeg \
    libasound2 \
    libasound2-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download LiveKit models (Silero VAD, etc.) so container boots instantly
RUN python -m livekit.agents download-files

# Copy the rest of application code
COPY . /app

# Ensure data directory exists
RUN mkdir -p /app/data

# Default command: start LiveKit Agent Worker
CMD ["python", "-m", "src.livekit_agent", "start"]

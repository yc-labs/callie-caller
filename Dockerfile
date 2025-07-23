FROM python:3.11-slim

# --- Build Arguments ---
ARG VERSION=1.0.0
ARG BUILD_DATE
ARG VCS_REF
ARG BUILD_NUMBER

# --- Environment Variables ---
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    # App settings
    CONTAINER_MODE=true \
    USE_UPNP=false \
    LOG_LEVEL=INFO \
    # Set paths
    PATH="/app:${PATH}"

# --- System Dependencies ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Audio libraries for PyAudio
    libasound2-dev \
    portaudio19-dev \
    # For SIP networking
    curl \
    netcat-traditional \
    # Build tools (will be removed later)
    gcc \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Application Setup ---
RUN groupadd -r callie && useradd -r -g callie -d /app callie
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y gcc \
    && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY callie_caller/ ./callie_caller/
COPY main.py .
COPY config.env.template .

# Set version info
RUN sed -i "s/__version__ = \".*\"/__version__ = \"${VERSION}\"/" callie_caller/_version.py

# Create directories and set permissions
RUN mkdir -p /app/logs /app/captured_audio \
    && chown -R callie:callie /app
USER callie

# --- Runtime Configuration ---
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD curl -f http://localhost:8080/health || exit 1

# --- Entry Point ---
CMD ["python", "main.py"] 
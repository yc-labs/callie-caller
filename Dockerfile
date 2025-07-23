# Callie Caller - AI Voice Agent
# Production-ready Docker image

FROM python:3.13-slim

# Build arguments for version and metadata
ARG VERSION=1.0.0
ARG BUILD_DATE
ARG VCS_REF
ARG BUILD_NUMBER

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Labels for image metadata
LABEL maintainer="Troy Fortin" \
      version="${VERSION}" \
      description="AI Voice Agent with SIP calling capabilities" \
      org.opencontainers.image.title="Callie Caller" \
      org.opencontainers.image.description="Production-ready AI voice assistant with SIP integration" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/troyfortin/callie-caller" \
      org.opencontainers.image.licenses="MIT"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Audio processing dependencies
    libasound2-dev \
    portaudio19-dev \
    # Network utilities
    miniupnpc \
    # Build tools (removed after pip install)
    gcc \
    g++ \
    make \
    pkg-config \
    # Cleanup in same layer
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r callie && useradd -r -g callie -d /app callie

# Set work directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    # Remove build dependencies to reduce image size
    && apt-get purge -y gcc g++ make pkg-config \
    && apt-get autoremove -y

# Copy application code
COPY callie_caller/ ./callie_caller/
COPY main*.py ./
COPY config.env.template .

# Set version in the container
RUN sed -i "s/__version__ = \".*\"/__version__ = \"${VERSION}\"/" callie_caller/_version.py \
    && sed -i "s/__build__ = \".*\"/__build__ = \"docker\"/" callie_caller/_version.py \
    && sed -i "s/__commit__ = \".*\"/__commit__ = \"${VCS_REF}\"/" callie_caller/_version.py

# Create directories for logs and audio
RUN mkdir -p /app/logs /app/captured_audio \
    && chown -R callie:callie /app

# Switch to non-root user
USER callie

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# Expose port
EXPOSE 8080

# Default command
CMD ["python", "main.py"]

# Alternative entry points as examples:
# CMD ["python", "main.py", "--debug"]                    # Debug mode
# CMD ["python", "main.py", "--call", "+1234567890"]     # Test call
# CMD ["python", "main.py", "--config-check"]            # Config validation 
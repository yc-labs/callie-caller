#!/bin/bash

# Callie Caller - Docker with Google Cloud Secrets
# Fetches secrets from Secret Manager and runs the container

set -euo pipefail

echo "🔐 Fetching secrets from Google Cloud Secret Manager..."

# Fetch secrets
export GEMINI_API_KEY=$(gcloud secrets versions access latest --secret="gemini-api-key")
export ZOHO_SIP_USERNAME=$(gcloud secrets versions access latest --secret="zoho-sip-username")
export ZOHO_SIP_PASSWORD=$(gcloud secrets versions access latest --secret="zoho-sip-password")

# Other configuration
export ZOHO_SIP_SERVER="us3-proxy2.zohovoice.com"
export SIP_PORT="5060"
export TEST_CALL_NUMBER="+16782960086"
export SERVER_PORT="8080"
export USE_UPNP="true"
export LOG_LEVEL="INFO"
export PYTHONUNBUFFERED="1"

echo "✅ Secrets fetched successfully"
echo "🐳 Starting Docker container with secrets..."

# Stop any existing container
docker-compose down 2>/dev/null || true

# Start with secrets
docker-compose up --build -d

echo "🚀 Container started!"
echo "📊 Container status:"
docker-compose ps

echo ""
echo "📋 To check logs:"
echo "  docker-compose logs -f"
echo ""
echo "📋 To test the API:"
echo "  curl -X POST http://localhost:8080/call -H 'Content-Type: application/json' -d '{\"number\": \"+16782960086\", \"message\": \"Hello from Docker!\"}'"
echo ""
echo "📋 To make a test call:"
echo "  docker-compose exec callie-caller python main-cloudrun-full.py --call +16782960086" 
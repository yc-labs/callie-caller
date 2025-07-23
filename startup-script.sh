#!/bin/bash
set -e

# --- Install Docker ---
echo "Updating packages and installing Docker..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# --- Create Application User and Add to Docker Group ---
echo "Creating application user 'callie' and adding to docker group..."
useradd --system --shell /bin/bash --create-home callie 2>/dev/null || true
usermod -aG docker callie
APP_DIR="/home/callie/callie-caller"
mkdir -p $APP_DIR
chown -R callie:callie /home/callie

# --- Fetch Secrets and Create .env file ---
echo "Fetching secrets from Secret Manager..."
# Allow unauthenticated access for simplicity in this script.
# For higher security, the VM's service account should be granted specific roles.
ZOHO_SIP_USERNAME=$(gcloud secrets versions access latest --secret="zoho-sip-username" --project="yc-partners")
ZOHO_SIP_PASSWORD=$(gcloud secrets versions access latest --secret="zoho-sip-password" --project="yc-partners")
GEMINI_API_KEY=$(gcloud secrets versions access latest --secret="gemini-api-key" --project="yc-partners")

echo "Creating .env file in $APP_DIR/.env..."
cat > $APP_DIR/.env << EOF
# --- SIP Provider Configuration ---
ZOHO_SIP_SERVER=us3-proxy2.zohovoice.com
ZOHO_SIP_USERNAME=${ZOHO_SIP_USERNAME}
ZOHO_SIP_PASSWORD=${ZOHO_SIP_PASSWORD}

# --- Google AI Configuration ---
GEMINI_API_KEY=${GEMINI_API_KEY}

# --- Application Settings ---
LOG_LEVEL=INFO
# Using host networking, so the server port can be directly accessed.
SERVER_PORT=8080
# Disable UPnP in production
USE_UPNP=false
CONTAINER_MODE=true
EOF

chown callie:callie $APP_DIR/.env
chmod 600 $APP_DIR/.env

echo "Setup complete. The VM is ready to run the Docker container."

# Authenticate Docker to GAR
gcloud auth configure-docker us-central1-docker.pkg.dev -q 
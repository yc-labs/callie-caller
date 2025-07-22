#!/bin/bash

# Callie Caller - Static Port Setup Guide
# Configure these EXACT ports on your router for Docker deployment

set -euo pipefail

echo "🌐 CALLIE CALLER - STATIC PORT CONFIGURATION GUIDE"
echo "=================================================="
echo ""

# Get local IP
LOCAL_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -n1)
echo "📍 Your Local Machine IP: $LOCAL_IP"
echo ""

echo "🔧 ROUTER CONFIGURATION REQUIRED:"
echo "=================================="
echo "Configure these EXACT port forwards on your router:"
echo ""
echo "Protocol | External Port | Internal IP   | Internal Port | Description"
echo "---------|---------------|---------------|---------------|------------------"
echo "UDP      | 5060          | $LOCAL_IP | 5060          | SIP Signaling"
echo "UDP      | 10000         | $LOCAL_IP | 10000         | Primary RTP Audio"
echo "UDP      | 10001         | $LOCAL_IP | 10001         | Backup RTP Audio" 
echo "UDP      | 10002         | $LOCAL_IP | 10002         | Additional RTP Audio"
echo "UDP      | 10003         | $LOCAL_IP | 10003         | Additional RTP Audio"
echo "UDP      | 10004         | $LOCAL_IP | 10004         | Additional RTP Audio"
echo "TCP      | 8080          | $LOCAL_IP | 8080          | Web Interface (optional)"
echo ""

echo "🐳 DOCKER CONFIGURATION:"
echo "========================"
echo "Docker will map these ports automatically when you run:"
echo "  docker-compose -f docker-compose-static-ports.yml up -d"
echo ""

echo "🔍 PORT TESTING:"
echo "================"
echo "After configuring your router, test port accessibility:"
echo ""
echo "# Test from external network (use your phone's hotspot):"
echo "# Replace YOUR_PUBLIC_IP with your actual public IP"
echo "nc -u YOUR_PUBLIC_IP 10000  # Test RTP port"
echo "nc -u YOUR_PUBLIC_IP 5060   # Test SIP port"
echo ""

echo "🚀 DEPLOYMENT STEPS:"
echo "===================="
echo "1. Configure the above ports on your router"
echo "2. Run: ./setup-static-ports.sh deploy"
echo "3. Test with: curl http://localhost:8080/health"
echo "4. Make test call to verify audio works"
echo ""

if [[ "${1:-}" == "deploy" ]]; then
    echo "🚀 Starting deployment with static ports..."
    echo ""
    
    # Check if secrets file exists
    if [[ ! -f "docker-secrets.env" ]]; then
        echo "📝 Creating secrets file..."
        cat > docker-secrets.env << EOF
# Fetched from Google Cloud Secret Manager
GEMINI_API_KEY=$(gcloud secrets versions access latest --secret="gemini-api-key")
ZOHO_SIP_USERNAME=$(gcloud secrets versions access latest --secret="zoho-sip-username") 
ZOHO_SIP_PASSWORD=$(gcloud secrets versions access latest --secret="zoho-sip-password")

# SIP Configuration
ZOHO_SIP_SERVER=us3-proxy2.zohovoice.com
SIP_PORT=5060

# Static port configuration
RTP_PORT=10000
USE_UPNP=false
CONTAINER_MODE=true

# Other settings
TEST_CALL_NUMBER=+16782960086
SERVER_PORT=8080
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1
EOF
        echo "✅ Secrets file created"
    fi
    
    # Stop any existing containers
    docker-compose down 2>/dev/null || true
    docker-compose -f docker-compose-static-ports.yml down 2>/dev/null || true
    
    # Start with static port configuration
    echo "🐳 Starting Docker with static ports..."
    docker-compose -f docker-compose-static-ports.yml up --build -d
    
    echo "✅ Deployment complete!"
    echo ""
    echo "📊 Container status:"
    docker-compose -f docker-compose-static-ports.yml ps
    echo ""
    echo "📋 Next steps:"
    echo "1. Check logs: docker-compose -f docker-compose-static-ports.yml logs -f"
    echo "2. Test health: curl http://localhost:8080/health"
    echo "3. Test call: curl -X POST http://localhost:8080/call -H 'Content-Type: application/json' -d '{\"number\": \"+14044626406\", \"message\": \"Test call with static ports\"}'"
    
elif [[ "${1:-}" == "test" ]]; then
    echo "🧪 Testing port connectivity..."
    echo ""
    
    # Test local ports
    echo "Testing local ports:"
    for port in 5060 8080 10000 10001 10002; do
        if nc -z -u localhost $port 2>/dev/null; then
            echo "✅ Port $port: OPEN"
        else
            echo "❌ Port $port: CLOSED"
        fi
    done
    
elif [[ "${1:-}" == "status" ]]; then
    echo "📊 Current deployment status:"
    docker-compose -f docker-compose-static-ports.yml ps
    echo ""
    echo "📋 Recent logs:"
    docker-compose -f docker-compose-static-ports.yml logs --tail=10
    
else
    echo "💡 USAGE:"
    echo "  $0 deploy    # Deploy with static ports"
    echo "  $0 test      # Test port connectivity" 
    echo "  $0 status    # Show deployment status"
    echo ""
    echo "⚠️  IMPORTANT: Configure the router ports shown above BEFORE deploying!"
fi 
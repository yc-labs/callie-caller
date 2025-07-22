#!/bin/bash
# Start Callie Caller in debug mode for audio troubleshooting

echo "🤖 Starting Callie Caller in Audio Debug Mode"
echo "=============================================="

# Check if docker.env exists
if [ ! -f "docker.env" ]; then
    echo "❌ docker.env file not found!"
    echo "Please create docker.env with your credentials"
    exit 1
fi

# Check if credentials are set
if grep -q "your_gemini_api_key_here" docker.env; then
    echo "⚠️  WARNING: docker.env still contains placeholder values"
    echo "Please update docker.env with your real credentials:"
    echo "  - GEMINI_API_KEY=your_real_api_key"
    echo "  - ZOHO_SIP_USERNAME=your_real_username"
    echo "  - ZOHO_SIP_PASSWORD=your_real_password"
    echo ""
    read -p "Continue anyway? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "🚀 Starting debug container..."
echo "📋 Features enabled:"
echo "   • Debug logging"
echo "   • Audio pipeline tracing"
echo "   • Test audio injection"
echo "   • Automatic call to +16782960086"
echo ""

# Start the container
docker-compose -f docker-compose.debug.yml up

echo "🏁 Debug session ended" 
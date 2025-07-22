# Callie Caller - AI Voice Agent

A production-ready AI voice assistant that makes and receives phone calls using SIP protocol and Google's Gemini Live API for natural voice conversations.

## Features

- **Real-time Voice Conversations**: Natural AI-powered phone conversations
- **SIP Integration**: Compatible with standard SIP providers (tested with Zoho Voice)
- **Production-ready**: Proper error handling, logging, and input validation
- **Audio Processing**: High-quality audio codec conversion and streaming
- **NAT Traversal**: Automatic UPnP configuration for firewall compatibility
- **Web API**: RESTful endpoints for making calls and monitoring
- **Call Recording**: Automatic WAV recording of conversations
- **Scalable Architecture**: Modular design for easy customization
- **Docker Support**: Containerized deployment with Google Artifact Registry
- **Version Control**: Semantic versioning with automated CI/CD

## Architecture

### Core Components

1. **SIP Client**: Handles SIP registration and call management
2. **RTP Bridge**: Real-time audio forwarding and processing
3. **AI Audio Bridge**: Interface with Google Gemini Live API
4. **Audio Codec Processing**: Converts between telephony codecs and PCM
5. **Agent Orchestrator**: Main control system with web interface

### Audio Processing Pipeline

**Incoming Audio**: Phone → SIP → RTP Bridge → Codec Conversion → AI Bridge → Gemini Live API  
**Outgoing Audio**: Gemini Live API → AI Bridge → RTP Bridge → Codec Conversion → SIP → Phone

## Installation

### Prerequisites

- Python 3.8 or higher
- Docker and Docker Compose (for containerized deployment)
- SIP provider account (Zoho Voice recommended)
- Google AI API key with Gemini Live access
- Google Cloud Project (for container registry)

### Local Development Setup

```bash
# Clone the repository
git clone <repository-url>
cd callie-caller

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp config.env.template .env
# Edit .env with your credentials
```

### Docker Deployment

#### Quick Start with Docker

```bash
# Build and run locally
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f callie-caller
```

#### Production Deployment with Google Artifact Registry

```bash
# Set up Google Artifact Registry (one-time setup)
./deploy.sh --project your-gcp-project setup

# Build and push to registry
./deploy.sh --project your-gcp-project --version 1.0.0 build

# Deploy to production
./deploy.sh --project your-gcp-project --version 1.0.0 deploy

# Check deployment status
./deploy.sh status
```

## Configuration

Create a `.env` file with your credentials:

```bash
# SIP Provider Configuration
ZOHO_SIP_DOMAIN=us3-proxy2.zohovoice.com
ZOHO_SIP_USERNAME=your_sip_username
ZOHO_SIP_PASSWORD=your_sip_password

# Google AI Configuration
GOOGLE_API_KEY=your_gemini_api_key

# Optional Configuration
USE_UPNP=true
LOG_LEVEL=INFO
SERVER_PORT=8080

# Docker/Production Configuration
GCP_PROJECT_ID=your-gcp-project
GAR_REGION=us-central1
GAR_REPOSITORY=callie-caller
```

## Usage

### Command Line

```bash
# Start the agent in server mode
python main.py

# Make a test call
python main.py --call +1234567890 --message "Hello, this is a test call"

# Enable debug logging
python main.py --debug

# Validate configuration
python main.py --config-check

# Show version information
python main.py --version
```

### Docker Usage

```bash
# Development with local build
docker-compose up -d

# Production with GAR images
export GAR_IMAGE=us-central1-docker.pkg.dev/your-project/callie-caller/callie-caller:1.0.0
docker-compose -f docker-compose.prod.yml up -d

# Using deployment script (recommended)
./deploy.sh --project your-project deploy
```

### Web API

Start the server and use the REST API:

```bash
# Make an outbound call
curl -X POST http://localhost:8080/call \
  -H "Content-Type: application/json" \
  -d '{"number": "+1234567890", "message": "Hello from AI!"}'

# Health check
curl http://localhost:8080/health

# Get conversation history
curl http://localhost:8080/conversations

# Agent statistics
curl http://localhost:8080/stats
```

### Python Integration

```python
from callie_caller import CallieAgent

# Initialize the agent
agent = CallieAgent()
agent.start()

# Make a call with validation
success = agent.make_call("+1234567890", "Hello, this is your AI assistant!")

# Cleanup
agent.stop()
```

## Version Management

### Semantic Versioning

```bash
# Show current version
python scripts/version.py --show

# Bump patch version (1.0.0 → 1.0.1)
python scripts/version.py --bump patch

# Bump minor version (1.0.0 → 1.1.0)
python scripts/version.py --bump minor

# Create a full release (bump, commit, tag, push)
python scripts/version.py --release patch
```

### Building and Deploying

```bash
# Build specific version
./build.sh --version 1.0.1 --project your-project --push

# Build from git tag
./build.sh --project your-project --push --latest

# Complete deployment workflow
python scripts/version.py --release patch
./deploy.sh --project your-project build deploy
```

## Deployment Guide

### Google Cloud Setup

1. **Create a Google Cloud Project**
2. **Enable APIs and set up Artifact Registry**:
   ```bash
   ./deploy.sh --project your-project setup
   ```

3. **Configure authentication**:
   ```bash
   gcloud auth login
   gcloud auth configure-docker us-central1-docker.pkg.dev
   ```

### Production Deployment

1. **Prepare environment file**:
   ```bash
   cp config.env.template .env
   # Edit .env with production credentials
   ```

2. **Deploy application**:
   ```bash
   # Build and deploy specific version
   ./deploy.sh --project your-project --version 1.0.0 build deploy
   
   # Or deploy latest
   ./deploy.sh --project your-project deploy
   ```

3. **Monitor deployment**:
   ```bash
   # Check status
   ./deploy.sh status
   
   # View logs
   ./deploy.sh logs
   
   # Health check
   curl http://localhost:8080/health
   ```

### CI/CD Integration

The project includes scripts for automated CI/CD:

- **Version Management**: `scripts/version.py` for semantic versioning
- **Build Script**: `build.sh` for Docker image creation
- **Deployment Script**: `deploy.sh` for complete deployment automation

Example workflow:
```bash
# 1. Create release
python scripts/version.py --release patch

# 2. Build and push
./build.sh --project your-project --push --latest

# 3. Deploy
./deploy.sh --project your-project deploy
```

## API Reference

### CallieAgent

```python
agent = CallieAgent()

# Start the agent
agent.start()

# Make a call with validation
agent.make_call(phone_number: str, message: Optional[str] = None) -> bool

# Stop the agent
agent.stop()
```

### REST Endpoints

- `GET /health` - Health check
- `POST /call` - Make outbound call
- `POST /sms` - SMS webhook handler
- `GET /conversations` - Conversation history
- `GET /stats` - Agent statistics

### Version Information

```python
from callie_caller import __version__, get_version_info

print(f"Version: {__version__}")
print(f"Detailed info: {get_version_info()}")
```

## Configuration Options

### SIP Settings

- **Server**: SIP proxy server address
- **Username/Password**: SIP credentials
- **Transport**: UDP (default)
- **Codecs**: PCMU, PCMA, G.729

### Audio Settings

- **Sample Rate**: 8kHz (telephony), 16kHz (AI processing), 24kHz (AI output)
- **Codec**: A-law/μ-law for SIP, PCM for AI processing
- **Packet Size**: 20ms RTP packets

### AI Settings

- **Model**: Gemini 2.0 Flash (with Live API)
- **Voice**: Natural conversation mode
- **Language**: English (configurable)

### Docker Settings

- **Base Image**: Python 3.11 slim
- **User**: Non-root for security
- **Health Checks**: Automated container health monitoring
- **Resource Limits**: Configurable CPU and memory limits

## File Structure

```
callie_caller/
├── ai/               # AI integration components
├── sip/              # SIP/RTP protocol implementation
├── core/             # Main orchestration and web server
├── config/           # Configuration management
├── utils/            # Network utilities and helpers
├── _version.py       # Version management
├── Dockerfile        # Container definition
├── docker-compose.yml # Development deployment
├── docker-compose.prod.yml # Production deployment
├── build.sh          # Docker build script
├── deploy.sh         # Deployment automation
└── scripts/
    └── version.py    # Version management script
```

## Production Deployment

### Environment Setup

1. **Configure Firewall**: Allow UDP traffic on RTP port range (10000-10100)
2. **Set up UPnP**: Enable for automatic NAT traversal
3. **Logging**: Configure appropriate log levels for production
4. **Monitoring**: Use health check endpoint for monitoring
5. **Container Registry**: Set up Google Artifact Registry

### Security Considerations

- Store credentials securely (environment variables)
- Validate all input phone numbers
- Rate limit API endpoints
- Monitor for unusual call patterns
- Implement proper authentication for web API
- Use non-root container user
- Regular security updates for base images

### Performance

- Single-threaded async design for efficiency
- Automatic audio buffer management
- Graceful error handling and recovery
- Memory-efficient audio processing
- Container resource limits and monitoring
- Health checks for automatic restart

### Monitoring and Logging

```bash
# Container logs
docker-compose logs -f callie-caller

# Resource usage
docker stats callie-caller

# Health monitoring
curl http://localhost:8080/health

# Application metrics
curl http://localhost:8080/stats
```

## Troubleshooting

### Common Issues

**Port Already in Use**
```bash
# Check what's using the port
lsof -i :8080
```

**Network Connectivity**
- Verify UPnP is enabled on router
- Check firewall allows UDP traffic
- Ensure SIP provider credentials are correct

**Audio Quality**
- Check network latency and jitter
- Verify codec compatibility with SIP provider
- Monitor system audio resources

**Container Issues**
```bash
# Check container status
docker-compose ps

# View detailed logs
docker-compose logs callie-caller

# Restart containers
docker-compose restart
```

### Deployment Issues

**GAR Authentication**
```bash
# Re-authenticate with Google Cloud
gcloud auth login
gcloud auth configure-docker us-central1-docker.pkg.dev
```

**Version Conflicts**
```bash
# Check current version
python scripts/version.py --show

# Clean up old images
./deploy.sh cleanup
```

### Support

For issues and questions:
1. Check the logs for error messages
2. Verify configuration with `--config-check`
3. Test with debug logging enabled
4. Review audio recordings in `captured_audio/` directory
5. Check container health status

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please read the contributing guidelines and submit pull requests for any improvements.

### Development Workflow

1. **Create feature branch**
2. **Make changes**
3. **Test locally**: `docker-compose up -d`
4. **Bump version**: `python scripts/version.py --bump patch`
5. **Create release**: `python scripts/version.py --release patch`
6. **Submit pull request**

---

**Note**: This software is designed for legitimate business and personal use. Ensure compliance with local telecommunications regulations and obtain proper consent for call recording where required. 
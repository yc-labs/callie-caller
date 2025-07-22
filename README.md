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
- SIP provider account (Zoho Voice recommended)
- Google AI API key with Gemini Live access

### Setup

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

# Make a call
success = agent.make_call("+1234567890", "Hello, this is your AI assistant!")

# Cleanup
agent.stop()
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

## File Structure

```
callie_caller/
├── ai/               # AI integration components
├── sip/              # SIP/RTP protocol implementation
├── core/             # Main orchestration and web server
├── config/           # Configuration management
└── utils/            # Network utilities and helpers
```

## Production Deployment

### Environment Setup

1. **Configure Firewall**: Allow UDP traffic on RTP port range
2. **Set up UPnP**: Enable for automatic NAT traversal
3. **Logging**: Configure appropriate log levels for production
4. **Monitoring**: Use health check endpoint for monitoring

### Security Considerations

- Store credentials securely (environment variables)
- Validate all input phone numbers
- Rate limit API endpoints
- Monitor for unusual call patterns
- Implement proper authentication for web API

### Performance

- Single-threaded async design for efficiency
- Automatic audio buffer management
- Graceful error handling and recovery
- Memory-efficient audio processing

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

### Support

For issues and questions:
1. Check the logs for error messages
2. Verify configuration with `--config-check`
3. Test with debug logging enabled
4. Review audio recordings in `captured_audio/` directory

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please read the contributing guidelines and submit pull requests for any improvements.

---

**Note**: This software is designed for legitimate business and personal use. Ensure compliance with local telecommunications regulations and obtain proper consent for call recording where required. 
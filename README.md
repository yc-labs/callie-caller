# Callie Caller - AI Voice Agent

## Overview
Callie Caller is an AI-powered voice agent that can make and receive phone calls using SIP (Session Initiation Protocol) and real-time audio processing with Google's Gemini Live API. It acts as an intelligent phone system that can hold natural voice conversations.

## Architecture

### Core Components

1. **SIP Client** (`callie_caller/sip/client.py`)
   - Handles SIP registration and call management
   - Connects to Zoho Voice SIP provider
   - Manages call states (IDLE, CALLING, RINGING, CONNECTED, ENDED)

2. **RTP Bridge** (`callie_caller/sip/rtp_bridge.py`)
   - Media proxy for real-time audio forwarding
   - Captures caller audio and sends to AI
   - Receives AI audio and streams to caller
   - Records conversations as WAV files

3. **AI Audio Bridge** (`callie_caller/ai/live_client.py`)
   - Interfaces with Google Gemini Live API
   - Handles bidirectional real-time audio streaming
   - Manages AI conversation state

4. **Audio Codec Processing** (`callie_caller/sip/audio_codec.py`)
   - Converts between telephony codecs (μ-law, A-law) and PCM
   - Handles sample rate conversion (8kHz ↔ 16kHz ↔ 24kHz)
   - Provides anti-aliasing for quality resampling

5. **Agent Orchestrator** (`callie_caller/core/agent.py`)
   - Main control system coordinating all components
   - Provides Flask web interface for API calls
   - Handles call monitoring and automatic hangup

## Audio Processing Pipeline

### Incoming Call Flow (Your Voice → AI)
```
Phone → Zoho → RTP Bridge → Codec Conversion → AI Bridge → Gemini Live API
         (A-law/8kHz)    (PCM/16kHz)     (PCM/16kHz)
```

### Outgoing Audio Flow (AI → Your Phone)  
```
Gemini Live API → AI Bridge → RTP Bridge → Codec Conversion → Zoho → Phone
   (PCM/24kHz)    (PCM/24kHz)  (A-law/8kHz RTP packets)
```

## Installation

### Prerequisites
- Python 3.8+
- Zoho Voice SIP account
- Google AI API key with Gemini Live access

### Setup
```bash
# Clone repository
git clone <repository-url>
cd callie-caller

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp config.env.template .env
# Edit .env with your credentials
```

## Configuration

### Required Environment Variables
```bash
# Zoho Voice SIP Configuration
ZOHO_SIP_DOMAIN=us3-proxy2.zohovoice.com
ZOHO_SIP_USERNAME=your_username
ZOHO_SIP_PASSWORD=your_password

# Google AI Configuration  
GOOGLE_API_KEY=your_gemini_api_key

# Optional: UPnP for NAT traversal
USE_UPNP=true
```

## Usage

### Command Line Interface
```bash
# Make a test call
python main.py --call +1234567890 --message "Hello, this is a test call"

# Start web server mode
python main.py

# Test audio with known tone instead of AI
python main.py --call +1234567890 --test-audio

# Use custom audio file for testing
python main.py --call +1234567890 --test-audio-file path/to/audio.wav
```

### Web API Endpoints
```bash
# Make outbound call
curl -X POST http://localhost:8080/call \
  -H "Content-Type: application/json" \
  -d '{"number": "+1234567890", "message": "Hello!"}'

# Health check
curl http://localhost:8080/health

# Get conversation history
curl http://localhost:8080/conversations

# Get agent statistics
curl http://localhost:8080/stats
```

## Key Features

### ✅ Working Features
- **SIP Registration**: Connects to Zoho Voice successfully
- **Call Management**: Can make outbound calls with proper SIP flow
- **Audio Recording**: Records both sides of conversation as WAV files
- **NAT Traversal**: Supports UPnP for automatic port forwarding
- **Echo Prevention**: Prevents audio feedback loops
- **Voicemail Detection**: Automatically hangs up on voicemail
- **Call Termination**: Properly handles call cleanup and BYE messages
- **WAV Recording**: Saves audio as standard WAV files instead of RTP

### 🔧 Current Issues Being Debugged
1. **Audio Static**: AI voice has static/distortion (partially improved with better resampling)
2. **AI Responsiveness**: AI sometimes doesn't respond to user speech
3. **Audio Quality**: Need further refinement of codec conversions

## Technical Details

### SIP Configuration
- **Device Emulation**: Yealink SIP-T46S for compatibility
- **Codecs Supported**: PCMU (μ-law), PCMA (A-law), G.729
- **Transport**: UDP with automatic NAT traversal
- **Authentication**: Digest authentication with Zoho Voice

### Audio Specifications
- **Telephony Standard**: 8kHz, 16-bit, mono
- **AI Input**: 16kHz PCM for Gemini Live
- **AI Output**: 24kHz PCM from Gemini Live  
- **RTP Packetization**: 20ms packets (160 samples at 8kHz)

### Network Architecture
```
[Phone] ←→ [Zoho SIP Proxy] ←→ [RTP Bridge] ←→ [AI Bridge] ←→ [Gemini Live API]
          (SIP signaling)      (RTP media)    (PCM audio)
```

## File Structure
```
callie_caller/
├── ai/               # AI integration
│   ├── client.py     # Gemini client
│   ├── live_client.py # Gemini Live API
│   └── conversation.py # Chat management
├── sip/              # SIP/RTP implementation  
│   ├── client.py     # SIP protocol
│   ├── call.py       # Call objects
│   ├── rtp_bridge.py # Media proxy
│   ├── rtp.py        # RTP packet handling
│   ├── sdp.py        # SDP parsing
│   ├── parser.py     # SIP message parsing
│   ├── auth.py       # SIP authentication
│   └── audio_codec.py # Audio conversion
├── core/             # Main orchestration
│   ├── agent.py      # Primary controller
│   └── logging.py    # Logging setup
├── config/           # Configuration
│   └── settings.py   # Settings management
├── utils/            # Network utilities
│   └── network.py    # IP discovery, UPnP
└── handlers/         # Call handlers (empty)
```

## Dependencies
```txt
google-genai>=0.6.0    # Gemini Live API
flask>=2.3.0           # Web server
pyaudio>=0.2.11        # Audio I/O
miniupnpc>=2.2.2       # UPnP support
```

## Troubleshooting

### Recent Fixes Applied
1. **Corrected Sample Rates**: Fixed 16kHz→24kHz assumption to proper 24kHz from AI
2. **Improved Resampling**: Added linear interpolation and anti-aliasing
3. **Voice Detection**: Added amplitude monitoring to debug responsiveness
4. **RTP Timing**: Fixed timestamp gaps causing choppy audio
5. **Codec Matching**: Ensured A-law (PCMA) consistency throughout pipeline

### Current Investigation Areas
1. **Static Source**: May be from A-law↔PCM conversion or resampling artifacts
2. **AI Hearing Issues**: Voice detection logging should show if AI receives audio
3. **Timing Synchronization**: RTP stream timing between AI responses and call

### Debug Logging
The system provides extensive logging:
- `🎤` Audio capture and conversion 
- `🗣️` Voice activity detection
- `📦` RTP packet analysis
- `🎵` Audio format conversions
- `🌉` Bridge statistics and flow

### Common Issues

#### "Address already in use" Error
```bash
# Check what's using port 8080
lsof -i :8080
# Or use direct calling instead
python main.py --call +1234567890
```

#### No Audio Flow
1. Check UPnP is enabled on router
2. Verify firewall allows UDP traffic
3. Check logs for "🗣️ VOICE ACTIVITY DETECTED"

#### Rate Limiting
```
400 Too many calls to the same destination in a short period
```
Wait 5-10 minutes between test calls to the same number.

### Audio Quality Debugging
1. **Check Recorded Files**: Review `captured_audio/*.wav` files
2. **Monitor Voice Detection**: Look for voice activity logs
3. **RTP Analysis**: Check packet analysis logs for codec mismatches
4. **Sample Rate Verification**: Ensure proper conversions in logs

## Development

### Adding New Features
- Call handlers go in `callie_caller/handlers/`
- Audio processing improvements in `callie_caller/sip/audio_codec.py`
- AI conversation logic in `callie_caller/ai/`

### Testing
```bash
# Test with known audio file
python main.py --call +1234567890 --test-audio-file test.wav

# Monitor logs for debugging
tail -f logs/callie_caller.log
```

## Next Steps for Troubleshooting
1. **Test Voice Detection**: Check logs for "🗣️ VOICE ACTIVITY DETECTED" when speaking
2. **Audio Quality Analysis**: Compare recorded WAV files before/after conversion
3. **AI Response Timing**: Monitor if AI generates audio but it's lost in conversion
4. **Codec Chain Verification**: Trace audio through each conversion step
5. **Alternative AI Models**: Test with different Gemini voice models if available

## Contributing
The system is fundamentally working but needs audio quality refinement to achieve production-ready voice conversations. Key areas for improvement:
- Audio codec optimization
- Real-time audio processing
- Call quality metrics
- Error handling and recovery

## License
[License information here] 
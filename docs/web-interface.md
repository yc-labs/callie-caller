# Callie Caller Web Interface

A modern, real-time web interface for controlling and monitoring your AI-powered voice agent.

## Features

### 🎯 Call Control
- **Place Calls**: Enter any phone number and initiate calls with a single click
- **AI/Direct Mode Toggle**: Switch between AI assistant mode and direct microphone mode
- **Context Messages**: Provide the AI with context about the call before it starts
- **AI Model Selection**: Choose between different Gemini models (Flash, Pro, etc.)
- **Call Management**: End active calls with real-time status updates

### 📊 Real-Time Monitoring
- **Call Status**: Live updates showing call state (connecting, ringing, connected, ended)
- **Call Duration**: Real-time call timer
- **Audio Visualization**: 
  - Dual audio level meters for caller and AI
  - Real-time waveform display
  - Visual feedback for active speech

### 📝 Live Transcription
- **Real-Time Transcripts**: See what both the caller and AI are saying
- **Speaker Identification**: Clear visual distinction between caller and AI
- **In-Progress Indicators**: Shows when someone is actively speaking
- **Auto-Scrolling**: Automatically follows the conversation

### 📋 System Logs
- **Tabbed Interface**: Organized logs by category
  - All Logs
  - SIP (Session Initiation Protocol)
  - RTP/Audio
  - AI
  - System
- **Log Levels**: Color-coded by severity (INFO, WARNING, ERROR)
- **Live Updates**: Logs stream in real-time during calls
- **Auto-Scroll**: Always shows the latest log entries

### 🔌 WebSocket Integration
- **Real-Time Updates**: All data updates live via WebSocket connection
- **Connection Status**: Visual indicator showing backend connection status
- **Automatic Reconnection**: Handles connection drops gracefully

## Getting Started

### Prerequisites
- Node.js 16+ and npm
- Python 3.8+ with pip
- All Callie Caller dependencies installed

### Quick Start

1. **Run the Web Interface**:
   ```bash
   ./web/run-web-ui.sh
   ```

   This script will:
   - Start the backend API server with WebSocket support
   - Install frontend dependencies (first run only)
   - Start the React development server
   - Open your browser to http://localhost:3000

2. **Manual Setup** (if preferred):
   
   Backend:
   ```bash
   USE_WEB_UI=true python main.py
   ```
   
   Frontend (in another terminal):
   ```bash
   cd web/frontend
   npm install  # First time only
   npm run dev
   ```

### Making a Call

1. Enter the phone number in the format: (555) 123-4567
2. Toggle "Use AI Assistant" on/off based on your preference
3. If using AI:
   - Select the AI model
   - Optionally provide context in the message box
4. Click "Start Call"
5. Monitor the call progress in real-time
6. Click "End Call" when finished

## Technical Architecture

### Backend (Flask + SocketIO)
- **Enhanced API Endpoints**:
  - `POST /api/call` - Initiate calls with options
  - `GET /api/call/<id>` - Get call status
  - `POST /api/call/<id>/end` - End a call
  - `GET /api/settings` - Get/update settings

- **WebSocket Events**:
  - `call_state` - Call status updates
  - `audio_levels` - Real-time audio levels
  - `log_entry` - System log entries
  - `transcription` - Live transcription updates

### Frontend (React + TypeScript)
- **Tech Stack**:
  - React 18 with TypeScript
  - Material-UI for components
  - Socket.IO client for WebSocket
  - Vite for fast development
  - Context API for state management

- **Key Components**:
  - `CallControl` - Phone dialer and settings
  - `AudioVisualizer` - Real-time audio display
  - `LogViewer` - Tabbed log interface
  - `TranscriptionPanel` - Live conversation view
  - `CallStatus` - Current call information

### WebSocket Protocol
- **Rooms**: Each call has its own room for targeted updates
- **Events Flow**:
  1. Client joins call room on call start
  2. Server emits updates only to relevant clients
  3. Client leaves room on call end

## Development

### Frontend Development
```bash
cd web/frontend
npm run dev      # Development server
npm run build    # Production build
```

### Adding New Features

1. **New Log Type**:
   - Add to `logTypes` array in `LogViewer.tsx`
   - Emit with appropriate type from backend

2. **New WebSocket Event**:
   - Add handler in `WebSocketManager`
   - Listen in appropriate context/component

3. **New API Endpoint**:
   - Add route in `WebAPI`
   - Update types in frontend

## Troubleshooting

### Connection Issues
- Check that backend is running on port 8080
- Verify no firewall blocking WebSocket connections
- Check browser console for errors

### Audio Visualization Not Working
- Ensure audio levels are being emitted from backend
- Check WebSocket connection status
- Verify call is in connected state

### Logs Not Appearing
- Check log type matches expected values
- Ensure WebSocket room is joined for the call
- Verify backend is emitting log entries

## Future Enhancements
- Call history and recordings
- Multiple simultaneous calls
- Advanced AI parameter tuning
- Call analytics and metrics
- WebRTC integration for browser-based calling 
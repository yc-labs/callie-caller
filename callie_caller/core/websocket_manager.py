"""
WebSocket manager for real-time communication with web interface.
"""
import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any
from datetime import datetime
import threading
from flask import request
from flask_socketio import SocketIO, emit, join_room, leave_room

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages WebSocket connections and real-time updates."""
    
    def __init__(self, socketio: SocketIO):
        self.socketio = socketio
        self.active_connections: Dict[str, Set[str]] = {}  # call_id -> set of session_ids
        self.call_states: Dict[str, Dict[str, Any]] = {}  # call_id -> call state
        self.audio_levels: Dict[str, Dict[str, float]] = {}  # call_id -> {caller: level, ai: level}
        self._setup_handlers()
        
    def _setup_handlers(self):
        """Setup WebSocket event handlers."""
        
        @self.socketio.on('connect')
        def handle_connect():
            logger.info(f"Client connected: {request.sid}")
            emit('connected', {'status': 'connected'})
            
        @self.socketio.on('disconnect')
        def handle_disconnect():
            logger.info(f"Client disconnected: {request.sid}")
            # Remove from all rooms
            for call_id in list(self.active_connections.keys()):
                if request.sid in self.active_connections[call_id]:
                    self.active_connections[call_id].remove(request.sid)
                    
        @self.socketio.on('join_call')
        def handle_join_call(data):
            call_id = data.get('call_id')
            if call_id:
                join_room(call_id)
                if call_id not in self.active_connections:
                    self.active_connections[call_id] = set()
                self.active_connections[call_id].add(request.sid)
                
                # Send current state if available
                if call_id in self.call_states:
                    emit('call_state', self.call_states[call_id])
                    
        @self.socketio.on('leave_call')
        def handle_leave_call(data):
            call_id = data.get('call_id')
            if call_id:
                leave_room(call_id)
                if call_id in self.active_connections:
                    self.active_connections[call_id].discard(request.sid)
    
    def emit_call_state(self, call_id: str, state: str, details: Optional[Dict[str, Any]] = None):
        """Emit call state update."""
        call_state = {
            'call_id': call_id,
            'state': state,
            'timestamp': datetime.now().isoformat(),
            'details': details or {}
        }
        self.call_states[call_id] = call_state
        self.socketio.emit('call_state', call_state, room=call_id)
        
    def emit_audio_levels(self, call_id: str, caller_level: float, ai_level: float):
        """Emit audio level updates."""
        levels = {
            'call_id': call_id,
            'caller': caller_level,
            'ai': ai_level,
            'timestamp': datetime.now().isoformat()
        }
        self.audio_levels[call_id] = {'caller': caller_level, 'ai': ai_level}
        self.socketio.emit('audio_levels', levels, room=call_id)
        
    def emit_log_entry(self, call_id: str, log_type: str, message: str, level: str = 'info'):
        """Emit log entry for a specific call."""
        log_entry = {
            'call_id': call_id,
            'type': log_type,
            'level': level,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        self.socketio.emit('log_entry', log_entry, room=call_id)
        
    def emit_transcription(self, call_id: str, speaker: str, text: str, is_final: bool = False):
        """Emit transcription update."""
        transcription = {
            'call_id': call_id,
            'speaker': speaker,  # 'caller' or 'ai'
            'text': text,
            'is_final': is_final,
            'timestamp': datetime.now().isoformat()
        }
        self.socketio.emit('transcription', transcription, room=call_id)
        
    def cleanup_call(self, call_id: str):
        """Clean up call data when call ends."""
        if call_id in self.call_states:
            del self.call_states[call_id]
        if call_id in self.audio_levels:
            del self.audio_levels[call_id]
        if call_id in self.active_connections:
            del self.active_connections[call_id] 
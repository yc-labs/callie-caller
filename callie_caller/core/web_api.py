"""
Enhanced Web API for Callie Caller with WebSocket support.
"""
import os
import logging
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from typing import Dict, Any, Optional
import threading
import numpy as np

from callie_caller.core.websocket_manager import WebSocketManager
from callie_caller.config.settings import get_settings

logger = logging.getLogger(__name__)


class WebAPI:
    """Enhanced Web API with real-time features."""
    
    def __init__(self, agent):
        self.agent = agent
        self.app = Flask(__name__, static_folder='../../web/frontend/build')
        CORS(self.app)
        
        # Initialize SocketIO
        self.socketio = SocketIO(self.app, cors_allowed_origins="*", async_mode='threading')
        self.ws_manager = WebSocketManager(self.socketio)
        
        # Track active calls
        self.active_calls: Dict[str, Dict[str, Any]] = {}
        
        self._setup_routes()
        self._setup_hooks()
        
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.route('/api/health')
        def health():
            return jsonify({
                'status': 'healthy',
                'version': '1.0.0',
                'sip_registered': self.agent.sip_client.registered if hasattr(self.agent, 'sip_client') else False
            })
            
        @self.app.route('/api/settings')
        def get_settings_route():
            """Get current settings."""
            settings = get_settings()
            return jsonify({
                'ai_models': ['gemini-2.0-flash-001', 'gemini-1.5-pro', 'gemini-1.5-flash'],
                'current_model': settings.ai.model,
                'sip_registered': self.agent.sip_client.registered if hasattr(self.agent, 'sip_client') else False,
                'server_port': settings.server.port
            })
            
        @self.app.route('/api/settings', methods=['POST'])
        def update_settings():
            """Update settings."""
            data = request.json
            # TODO: Implement settings update
            return jsonify({'status': 'success'})
            
        @self.app.route('/api/call', methods=['POST'])
        def make_call():
            """Enhanced call endpoint with more options."""
            data = request.json
            phone_number = data.get('number')
            initial_message = data.get('message', '')
            use_ai = data.get('use_ai', True)
            ai_model = data.get('ai_model')
            ai_params = data.get('ai_params', {})
            
            if not phone_number:
                return jsonify({'error': 'Phone number required'}), 400
                
            try:
                # Create call with enhanced options
                call = self.agent.make_call(
                    phone_number, 
                    initial_message=initial_message if use_ai else None
                )
                
                if call:
                    call_info = {
                        'call_id': call.call_id,
                        'number': phone_number,
                        'use_ai': use_ai,
                        'status': 'initiated',
                        'ai_model': ai_model or 'default',
                        'start_time': call.start_time.isoformat() if hasattr(call, 'start_time') else None
                    }
                    self.active_calls[call.call_id] = call_info
                    
                    # Emit initial state
                    self.ws_manager.emit_call_state(call.call_id, 'initiated', call_info)
                    
                    return jsonify(call_info)
                else:
                    return jsonify({'error': 'Failed to initiate call'}), 500
                    
            except Exception as e:
                logger.error(f"Error making call: {e}")
                return jsonify({'error': str(e)}), 500
                
        @self.app.route('/api/call/<call_id>')
        def get_call_status(call_id):
            """Get call status."""
            if call_id in self.active_calls:
                return jsonify(self.active_calls[call_id])
            return jsonify({'error': 'Call not found'}), 404
            
        @self.app.route('/api/call/<call_id>/end', methods=['POST'])
        def end_call(call_id):
            """End a call."""
            try:
                # Find and end the call
                if hasattr(self.agent, 'active_calls') and call_id in self.agent.active_calls:
                    call = self.agent.active_calls[call_id]
                    call.hangup()
                    
                    # Update state
                    if call_id in self.active_calls:
                        self.active_calls[call_id]['status'] = 'ended'
                        
                    self.ws_manager.emit_call_state(call_id, 'ended')
                    self.ws_manager.cleanup_call(call_id)
                    
                    return jsonify({'status': 'success'})
                else:
                    return jsonify({'error': 'Call not found'}), 404
                    
            except Exception as e:
                logger.error(f"Error ending call: {e}")
                return jsonify({'error': str(e)}), 500
                
        @self.app.route('/api/calls/active')
        def get_active_calls():
            """Get all active calls."""
            return jsonify(list(self.active_calls.values()))
            
        # Serve React app
        @self.app.route('/', defaults={'path': ''})
        @self.app.route('/<path:path>')
        def serve_react(path):
            if path != "" and os.path.exists(os.path.join(self.app.static_folder, path)):
                return send_from_directory(self.app.static_folder, path)
            else:
                return send_from_directory(self.app.static_folder, 'index.html')
                
    def _setup_hooks(self):
        """Setup hooks to agent events for real-time updates."""
        # We'll need to modify the agent to emit these events
        pass
        
    def emit_audio_levels(self, call_id: str, audio_data: bytes, is_caller: bool = True):
        """Calculate and emit audio levels from raw audio data."""
        try:
            # Convert bytes to numpy array (assuming 16-bit PCM)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Calculate RMS (root mean square) for volume level
            rms = np.sqrt(np.mean(audio_array.astype(float)**2))
            
            # Normalize to 0-1 range (16-bit audio max is 32767)
            level = min(1.0, rms / 32767.0)
            
            # Emit based on source
            if is_caller:
                self.ws_manager.emit_audio_levels(call_id, level, 0)
            else:
                self.ws_manager.emit_audio_levels(call_id, 0, level)
                
        except Exception as e:
            logger.error(f"Error calculating audio levels: {e}")
            
    def run(self, host='0.0.0.0', port=None, debug=False):
        """Run the web server with WebSocket support."""
        if port is None:
            settings = get_settings()
            port = settings.server.port
            
        logger.info(f"Starting enhanced web server on http://{host}:{port}")
        self.socketio.run(self.app, host=host, port=port, debug=debug) 
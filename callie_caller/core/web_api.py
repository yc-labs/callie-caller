"""
Enhanced Web API for Callie Caller with WebSocket support.
"""
import os
import logging
import re
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from typing import Dict, Any, Optional
import threading
import numpy as np
from datetime import datetime
import uuid
import time
import asyncio

from callie_caller.core.websocket_manager import WebSocketManager
from callie_caller.core.logging_handler import WebSocketLoggingHandler
from callie_caller.config.settings import get_settings

logger = logging.getLogger(__name__)


class WebAPI:
    """Enhanced Web API with real-time features."""
    
    def __init__(self, agent):
        self.agent = agent
        self.app = Flask(__name__, static_folder='../../web/frontend/build')
        
        # Configure CORS properly to avoid WebSocket errors
        CORS(self.app, resources={
            r"/*": {
                "origins": ["http://localhost:3000", "http://localhost:8080"],
                "allow_headers": ["Content-Type"],
                "supports_credentials": True
            }
        })
        
        # Initialize SocketIO with proper configuration
        self.socketio = SocketIO(
            self.app, 
            cors_allowed_origins=["http://localhost:3000", "http://localhost:8080"],
            async_mode='threading',
            logger=False,
            engineio_logger=False,
            ping_timeout=60,
            ping_interval=25
        )
        self.ws_manager = WebSocketManager(self.socketio)
        
        # Track active calls
        self.active_calls: Dict[str, Dict[str, Any]] = {}
        
        # Setup WebSocket logging handler
        self.ws_logging_handler = WebSocketLoggingHandler(self.ws_manager)
        self.ws_logging_handler.setLevel(logging.INFO)
        self.ws_logging_handler.setFormatter(
            logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        )
        
        # Add handler to root logger to capture all logs
        root_logger = logging.getLogger()
        root_logger.addHandler(self.ws_logging_handler)
        
        self._setup_routes()
        self._setup_hooks()
        
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.route('/api/debug/event-loop', methods=['GET'])
        def check_event_loop():
            """Check event loop status."""
            result = {
                'loop_exists': hasattr(self.agent, '_loop') and self.agent._loop is not None,
                'loop_running': False,
                'loop_thread_alive': False,
                'loop_thread_exists': hasattr(self.agent, '_loop_thread') and self.agent._loop_thread is not None
            }
            
            if hasattr(self.agent, '_loop') and self.agent._loop:
                result['loop_running'] = self.agent._loop.is_running()
            
            if hasattr(self.agent, '_loop_thread') and self.agent._loop_thread:
                result['loop_thread_alive'] = self.agent._loop_thread.is_alive()
                
            return jsonify(result)
            
        @self.app.route('/api/debug/start-ai/<call_id>', methods=['POST'])
        def force_start_ai(call_id):
            """Manually start AI conversation for a call to test if it works."""
            result = {'success': False, 'message': 'Call not found'}
            
            # Find the SIP call
            if hasattr(self.agent, 'sip_client') and self.agent.sip_client:
                if hasattr(self.agent.sip_client, 'active_calls'):
                    for sip_call in self.agent.sip_client.active_calls.values():
                        if sip_call.call_id == call_id:
                            try:
                                # Manually trigger the AI conversation
                                if self.agent._loop and self.agent._loop.is_running():
                                    future = asyncio.run_coroutine_threadsafe(
                                        self.agent._handle_call_conversation(sip_call),
                                        self.agent._loop
                                    )
                                    result = {'success': True, 'message': f'AI conversation manually started for call {call_id}'}
                                else:
                                    result = {'success': False, 'message': 'No event loop available'}
                            except Exception as e:
                                result = {'success': False, 'message': f'Error starting AI: {e}'}
                            break
            
            return jsonify(result)
            
        @self.app.route('/api/debug/cleanup', methods=['POST'])
        def force_cleanup():
            """Force cleanup of stuck calls and RTP bridge."""
            cleanup_results = {
                'cleared_web_calls': 0,
                'cleared_sip_calls': 0,
                'stopped_rtp_bridge': False,
                'stopped_silence_injection': False
            }
            
            # Clear web API active calls
            cleanup_results['cleared_web_calls'] = len(self.active_calls)
            self.active_calls.clear()
            
            # Clear SIP client active calls and stop RTP bridge
            if hasattr(self.agent, 'sip_client') and self.agent.sip_client:
                if hasattr(self.agent.sip_client, 'active_calls'):
                    cleanup_results['cleared_sip_calls'] = len(self.agent.sip_client.active_calls)
                    self.agent.sip_client.active_calls.clear()
                
                # Force stop RTP bridge
                if hasattr(self.agent.sip_client, 'rtp_bridge') and self.agent.sip_client.rtp_bridge:
                    if self.agent.sip_client.rtp_bridge.running:
                        self.agent.sip_client.rtp_bridge.stop_bridge()
                        cleanup_results['stopped_rtp_bridge'] = True
                    self.agent.sip_client.rtp_bridge = None
            
            return jsonify(cleanup_results)
            
        @self.app.route('/api/debug/status')
        def debug_status():
            """Debug endpoint to check active calls and RTP bridge status."""
            status = {
                'active_calls': len(self.active_calls),
                'call_ids': list(self.active_calls.keys()),
                'sip_client_active_calls': 0,
                'rtp_bridge_running': False,
                'silence_injection_running': False
            }
            
            # Check SIP client status
            if hasattr(self.agent, 'sip_client') and self.agent.sip_client:
                if hasattr(self.agent.sip_client, 'active_calls'):
                    status['sip_client_active_calls'] = len(self.agent.sip_client.active_calls)
                    status['sip_call_ids'] = list(self.agent.sip_client.active_calls.keys())
                
                # Check RTP bridge status
                if hasattr(self.agent.sip_client, 'rtp_bridge') and self.agent.sip_client.rtp_bridge:
                    status['rtp_bridge_running'] = self.agent.sip_client.rtp_bridge.running
                    status['silence_injection_running'] = getattr(self.agent.sip_client.rtp_bridge, 'silence_injection_running', False)
            
            return jsonify(status)
            
        @self.app.route('/api/test')
        def test_endpoint():
            """Simple test endpoint."""
            return jsonify({'status': 'test works', 'timestamp': time.time()})
            
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
                
            # Clean phone number - remove all non-digits
            cleaned_number = re.sub(r'\D', '', phone_number)
            
            # Add country code if not present (assuming US numbers)
            if len(cleaned_number) == 10:
                cleaned_number = '1' + cleaned_number
            elif len(cleaned_number) == 11 and cleaned_number[0] == '1':
                # Already has country code
                pass
            else:
                return jsonify({'error': 'Invalid phone number format'}), 400
                
            try:
                # Create call with enhanced options - run in background thread
                call_id = str(uuid.uuid4())
                
                # Create call info immediately
                call_info = {
                    'call_id': call_id,
                    'number': phone_number,
                    'use_ai': use_ai,
                    'ai_model': ai_model,
                    'status': 'initiating',
                    'start_time': datetime.now().isoformat(),
                    'sip_call_id': None
                }
                
                # Store active call
                self.active_calls[call_id] = call_info
                
                # Start call in background thread to avoid blocking
                def start_call():
                    try:
                        logger.info(f"📞 Starting call to {cleaned_number} in background thread")
                        success = self.agent.make_call(
                            cleaned_number, 
                            message=initial_message if use_ai else None
                        )
                        
                        if success:
                            call_info['status'] = 'connected'
                            logger.info(f"✅ Call {call_id} connected successfully")
                            
                            # Get the actual SIP call ID if available
                            if hasattr(self.agent.sip_client, 'active_calls') and self.agent.sip_client.active_calls:
                                sip_calls = list(self.agent.sip_client.active_calls.values())
                                if sip_calls:
                                    latest_call = sip_calls[-1]
                                    call_info['sip_call_id'] = latest_call.call_id
                                    logger.info(f"Linked WebSocket call {call_id} to SIP call {latest_call.call_id}")
                        else:
                            call_info['status'] = 'failed'
                            logger.error(f"❌ Call {call_id} failed to connect")
                    except Exception as e:
                        call_info['status'] = 'failed'
                        logger.error(f"❌ Call {call_id} failed with error: {e}")
                
                # Start the call in a background thread
                call_thread = threading.Thread(target=start_call, daemon=True)
                call_thread.start()
                
                # Return immediately with call info
                return jsonify(call_info)
                    
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
        # For now, let's add a method to handle incoming transcriptions
        logger.info("Setting up WebSocket hooks for real-time updates")
        
    def emit_transcription(self, call_id: str, speaker: str, text: str, is_final: bool = True):
        """Emit transcription via WebSocket."""
        self.ws_manager.emit_transcription(call_id, speaker, text, is_final)
            
    def emit_audio_levels(self, call_id: str, audio_data: bytes, is_caller: bool = True):
        """Calculate and emit audio levels from raw audio data."""
        try:
            # Log the first few audio level calculations
            if not hasattr(self, '_audio_levels_logged'):
                self._audio_levels_logged = {'caller': 0, 'ai': 0}
            
            source = 'caller' if is_caller else 'AI'
            if self._audio_levels_logged[source.lower()] < 5:
                logger.info(f"📊 Calculating audio levels for {source}: {len(audio_data)} bytes")
                self._audio_levels_logged[source.lower()] += 1
            
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
                if self._audio_levels_logged['ai'] <= 5:
                    logger.info(f"📊 AI audio level: {level:.3f}")
                
        except Exception as e:
            logger.error(f"Error calculating audio levels: {e}")
            
    def run(self, host='0.0.0.0', port=None, debug=False):
        """Run the web server with WebSocket support."""
        if port is None:
            settings = get_settings()
            port = settings.server.port
            
        logger.info(f"Starting enhanced web server on http://{host}:{port}")
        self.socketio.run(self.app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True) 
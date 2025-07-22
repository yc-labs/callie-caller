"""
Web-only Callie Agent for Cloud Run deployment.
Provides REST API functionality without SIP calling capabilities.
"""

import logging
import threading
import time
from typing import Optional, Dict, Any
from flask import Flask, request, Response, jsonify

from callie_caller.config import get_settings
from callie_caller.ai.conversation import ConversationManager

logger = logging.getLogger(__name__)

class WebCallieAgent:
    """
    Web-only AI voice agent for Cloud Run.
    Provides REST API without SIP calling functionality.
    """
    
    def __init__(self):
        """Initialize Web-only Callie Agent."""
        self.settings = get_settings()
        
        # Initialize only non-SIP components
        self.conversation_manager = ConversationManager()
        
        # Flask app for API
        self.app = Flask(__name__)
        self._setup_flask_routes()
        
        # State management
        self.running = False
        
        logger.info("Web Callie Agent initialized (Cloud Run mode)")
        
    def start(self) -> None:
        """Start the web agent."""
        if self.running:
            logger.warning("Web agent is already running")
            return
            
        logger.info("Starting Web Callie Agent...")
        self.running = True
        
        logger.info("Web Callie Agent started successfully")
        logger.info("📋 Cloud Run Mode - SIP calling not available in this environment")
        logger.info("🌐 Use external SIP infrastructure for actual calling")
            
    def stop(self) -> None:
        """Stop the Web Callie Agent."""
        logger.info("Stopping Web Callie Agent...")
        self.running = False
        
    def _setup_flask_routes(self) -> None:
        """Setup Flask routes for webhooks and API."""
        
        @self.app.route('/', methods=['GET'])
        def root():
            """Root endpoint with API information."""
            return jsonify({
                'service': 'Callie Caller AI Voice Agent',
                'mode': 'Cloud Run (Web API Only)',
                'version': '1.0.0',
                'status': 'healthy' if self.running else 'stopped',
                'endpoints': {
                    'health': '/health',
                    'call': '/call (POST)',
                    'conversations': '/conversations',
                    'stats': '/stats',
                    'sms': '/sms (POST)'
                },
                'limitations': [
                    'Direct SIP calling not available in Cloud Run',
                    'Use external SIP services for voice calls',
                    'AI conversation and API functionality available'
                ]
            })
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint."""
            return jsonify({
                'status': 'healthy',
                'mode': 'cloud_run_web_only',
                'agent_running': self.running,
                'sip_available': False,
                'active_conversations': len(self.conversation_manager.active_conversations),
                'timestamp': time.time()
            })
            
        @self.app.route('/sms', methods=['POST'])
        def handle_sms():
            """Handle incoming SMS from Zoho Voice."""
            try:
                from_number = request.form.get('from', 'unknown')
                message_body = request.form.get('text', '')
                
                logger.info(f"SMS from {from_number}: {message_body}")
                
                # Start conversation for SMS
                conversation_id = f"sms-{int(time.time())}-{from_number}"
                conversation = self.conversation_manager.start_conversation(
                    conversation_id=conversation_id,
                    phone_number=from_number
                )
                
                # Add user message
                self.conversation_manager.add_user_message(
                    conversation_id, 
                    message_body,
                    metadata={'type': 'sms'}
                )
                
                # Generate AI response
                response = self.conversation_manager.generate_response(conversation_id)
                
                if response:
                    logger.info(f"SMS AI response: {response}")
                    # In a real implementation, send SMS response via Zoho API
                    
                # End SMS conversation
                self.conversation_manager.end_conversation(conversation_id)
                
                return jsonify({
                    'success': True,
                    'response': response,
                    'conversation_id': conversation_id
                })
                
            except Exception as e:
                logger.error(f"Error handling SMS: {e}")
                return jsonify({'error': str(e)}), 500
                
        @self.app.route('/call', methods=['POST'])
        def make_call_api():
            """API endpoint for call requests (Cloud Run limitation noted)."""
            try:
                data = request.get_json()
                number = data.get('number')
                message = data.get('message')
                
                if not number:
                    return jsonify({'error': 'Phone number required'}), 400
                
                logger.info(f"Call request received for {number} with message: {message}")
                
                # In Cloud Run, we can't make direct SIP calls
                # Return information about external calling options
                return jsonify({
                    'success': False,
                    'error': 'Direct SIP calling not available in Cloud Run',
                    'alternatives': {
                        'voice_api': 'Use Zoho Voice API for outbound calls',
                        'sip_service': 'Deploy SIP functionality to external service',
                        'twilio': 'Use Twilio Voice API for calling',
                        'message': 'AI conversation features available via SMS endpoint'
                    },
                    'requested_number': number,
                    'requested_message': message
                })
                    
            except Exception as e:
                logger.error(f"Error in call API: {e}")
                return jsonify({'error': str(e)}), 500
                
        @self.app.route('/conversations', methods=['GET'])
        def get_conversations():
            """Get conversation history."""
            try:
                phone_number = request.args.get('phone_number')
                limit = int(request.args.get('limit', 10))
                
                conversations = self.conversation_manager.get_conversation_history(
                    phone_number=phone_number,
                    limit=limit
                )
                
                return jsonify({
                    'conversations': [
                        {
                            'id': c.conversation_id,
                            'phone_number': c.phone_number,
                            'start_time': c.start_time,
                            'duration': c.duration,
                            'message_count': c.message_count,
                            'summary': c.summary
                        }
                        for c in conversations
                    ]
                })
                
            except Exception as e:
                logger.error(f"Error getting conversations: {e}")
                return jsonify({'error': str(e)}), 500
                
        @self.app.route('/stats', methods=['GET'])
        def get_stats():
            """Get agent statistics."""
            try:
                stats = self.conversation_manager.get_conversation_stats()
                stats.update({
                    'mode': 'cloud_run_web_only',
                    'agent_running': self.running,
                    'sip_available': False,
                    'deployment': 'Cloud Run'
                })
                
                return jsonify(stats)
                
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/ai/chat', methods=['POST'])
        def ai_chat():
            """Direct AI chat endpoint for testing."""
            try:
                data = request.get_json()
                message = data.get('message')
                phone_number = data.get('phone_number', 'web_chat')
                
                if not message:
                    return jsonify({'error': 'Message required'}), 400
                
                # Create temporary conversation
                conversation_id = f"chat-{int(time.time())}-{phone_number}"
                conversation = self.conversation_manager.start_conversation(
                    conversation_id=conversation_id,
                    phone_number=phone_number
                )
                
                # Add user message
                self.conversation_manager.add_user_message(
                    conversation_id, 
                    message,
                    metadata={'type': 'web_chat'}
                )
                
                # Generate AI response
                response = self.conversation_manager.generate_response(conversation_id)
                
                # End conversation
                self.conversation_manager.end_conversation(conversation_id)
                
                return jsonify({
                    'success': True,
                    'response': response,
                    'conversation_id': conversation_id
                })
                
            except Exception as e:
                logger.error(f"Error in AI chat: {e}")
                return jsonify({'error': str(e)}), 500
            
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            'mode': 'cloud_run_web_only',
            'running': self.running,
            'sip_available': False,
            'deployment': 'Cloud Run',
            'active_conversations': len(self.conversation_manager.active_conversations),
            'total_conversations': len(self.conversation_manager.conversation_history)
        }

def create_app() -> Flask:
    """Create Flask app for Cloud Run deployment."""
    agent = WebCallieAgent()
    agent.start()
    return agent.app 
#!/usr/bin/env python3
"""
Callie Caller - Cloud Run Full SIP Entry Point (FIXED)
This version gracefully handles Cloud Run deployment with SIP capabilities.
"""

import os
import sys
import logging
import threading
import time
from flask import Flask, request, Response, jsonify

from callie_caller.core.logging import setup_logging

# Configure logging first
setup_logging(level=os.getenv("LOG_LEVEL", "DEBUG"))
logger = logging.getLogger(__name__)

def create_cloud_run_app():
    """Create a Flask app optimized for Cloud Run with full SIP capabilities."""
    
    # Set required environment variables
    os.environ["USE_UPNP"] = "false"
    os.environ["CONTAINER_MODE"] = "true" 
    os.environ["CLOUD_RUN_MODE"] = "true"
    
    app = Flask(__name__)
    
    # Initialize components
    sip_client = None
    agent_running = False
    
    def init_sip_client():
        """Initialize SIP client in a separate thread to avoid blocking startup."""
        nonlocal sip_client, agent_running
        try:
            logger.info("🔧 Initializing SIP client in background...")
            from callie_caller.core.agent import CallieAgent
            
            agent = CallieAgent()
            agent.start()
            
            sip_client = agent.sip_client
            agent_running = True
            
            logger.info("✅ SIP client initialized successfully!")
            
            # Test audio capabilities
            if hasattr(agent, 'enable_test_audio_mode'):
                test_enabled = agent.enable_test_audio_mode()
                logger.info(f"🧪 Test audio mode: {'enabled' if test_enabled else 'failed'}")
            
            return agent
            
        except Exception as e:
            logger.error(f"❌ SIP client initialization failed: {e}")
            import traceback
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return None
    
    # Initialize SIP in background
    init_thread = threading.Thread(target=init_sip_client, daemon=True)
    init_thread.start()
    
    @app.route('/', methods=['GET'])
    def root():
        """Root endpoint with service information."""
        return jsonify({
            'service': 'Callie Caller AI Voice Agent',
            'mode': 'Cloud Run Full SIP',
            'version': '1.0.0-cloudrun-full',
            'status': 'healthy',
            'sip_status': 'initializing' if not agent_running else 'ready',
            'features': [
                'Full SIP calling with Zoho Voice',
                'AI audio conversation with Gemini Live',
                'Real-time voice interaction',
                'Audio debugging and logging'
            ],
            'endpoints': {
                'health': '/health',
                'call': '/call (POST)',
                'test_call': '/test_call',
                'logs': '/logs'
            }
        })
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint."""
        return jsonify({
            'status': 'healthy',
            'mode': 'cloud_run_full_sip',
            'agent_running': agent_running,
            'sip_available': sip_client is not None,
            'sip_ready': agent_running and sip_client is not None,
            'timestamp': time.time()
        })
    
    @app.route('/call', methods=['POST'])
    def make_call():
        """Make a call with full SIP capabilities."""
        try:
            if not agent_running or not sip_client:
                return jsonify({
                    'success': False,
                    'error': 'SIP client not ready yet',
                    'retry_after': 10,
                    'status': 'initializing'
                }), 503
            
            data = request.get_json()
            number = data.get('number')
            message = data.get('message', 'Hello! This is Callie, your AI voice assistant calling from Cloud Run with full SIP capabilities.')
            
            if not number:
                return jsonify({'error': 'Phone number required'}), 400
            
            logger.info(f"📞 Making SIP call to {number}")
            
            # Get the agent from the thread
            for thread in threading.enumerate():
                if hasattr(thread, 'agent'):
                    agent = thread.agent
                    break
            else:
                # Create temporary agent reference
                from callie_caller.core.agent import CallieAgent
                agent = CallieAgent()
                agent.sip_client = sip_client
            
            # Make the call
            success = agent.make_call(number, message)
            
            if success:
                return jsonify({
                    'success': True,
                    'message': f'Call initiated to {number}',
                    'features_active': [
                        'SIP calling via Zoho Voice',
                        'AI audio conversation',
                        'Real-time voice interaction'
                    ]
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Call failed to connect',
                    'number': number
                }), 500
                
        except Exception as e:
            logger.error(f"Call error: {e}")
            import traceback
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return jsonify({'error': str(e)}), 500
    
    @app.route('/test_call', methods=['GET', 'POST'])
    def test_call():
        """Make a test call to the configured number."""
        try:
            test_number = os.getenv('TEST_CALL_NUMBER', '+16782960086')
            
            return make_call_internal(test_number, 
                "Hello! This is Callie testing the full SIP audio capabilities from Cloud Run. Can you hear me clearly?")
            
        except Exception as e:
            logger.error(f"Test call error: {e}")
            return jsonify({'error': str(e)}), 500
    
    def make_call_internal(number, message):
        """Internal call function."""
        if not agent_running or not sip_client:
            return jsonify({
                'success': False,
                'error': 'SIP client not ready',
                'status': 'initializing'
            }), 503
        
        logger.info(f"🎯 Making test call to {number}")
        
        # Use requests to call our own endpoint to avoid threading issues
        import requests
        import json
        
        try:
            response = requests.post(
                f"http://localhost:{os.getenv('PORT', '8080')}/call",
                json={'number': number, 'message': message},
                timeout=30
            )
            return response.json(), response.status_code
        except Exception as e:
            return jsonify({'error': f'Internal call failed: {e}'}), 500
    
    @app.route('/status', methods=['GET'])
    def status():
        """Detailed status information."""
        status_info = {
            'cloud_run': True,
            'sip_ready': agent_running and sip_client is not None,
            'agent_running': agent_running,
            'timestamp': time.time(),
            'environment': {
                'port': os.getenv('PORT', '8080'),
                'cloud_run_mode': os.getenv('CLOUD_RUN_MODE'),
                'container_mode': os.getenv('CONTAINER_MODE'),
                'log_level': os.getenv('LOG_LEVEL')
            }
        }
        
        if sip_client:
            status_info['sip_info'] = {
                'local_ip': getattr(sip_client, 'local_ip', 'unknown'),
                'local_port': getattr(sip_client, 'local_port', 'unknown'),
                'registered': getattr(sip_client, 'registered', False)
            }
        
        return jsonify(status_info)
    
    @app.route('/logs', methods=['GET'])
    def get_logs():
        """Get recent application logs."""
        try:
            # Return some basic log info
            return jsonify({
                'message': 'Check Cloud Run logs for detailed information',
                'log_command': 'gcloud run services logs read callie-caller-full --region=us-central1',
                'status': 'healthy'
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return app

def main():
    """Main entry point for Cloud Run with full SIP capabilities."""
    logger.info("🤖 Callie Caller v1.0.0 - AI Voice Agent (Cloud Run Full SIP Mode - FIXED)")
    
    try:
        # Create Flask app
        app = create_cloud_run_app()
        
        # Get port from environment (Cloud Run sets PORT)
        port = int(os.getenv("PORT", "8080"))
        host = "0.0.0.0"
        
        logger.info(f"🚀 Starting Cloud Run Full SIP service on {host}:{port}")
        logger.info("📋 Features enabled:")
        logger.info("   • Full SIP calling via Zoho Voice")
        logger.info("   • AI audio conversation with Gemini")
        logger.info("   • Real-time voice interaction")
        logger.info("   • Audio debugging and test modes")
        
        # Start the Flask server
        app.run(
            host=host,
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False
        )
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main() 
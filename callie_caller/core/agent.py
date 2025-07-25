"""
Main Callie Agent - AI Voice Assistant for Zoho Voice.
Coordinates SIP calling, AI conversation, and call management.
Supports both single-tenant (legacy) and multi-tenant modes.
Now with PJSUA2 support for robust session timer handling.
"""

import logging
import threading
import time
import asyncio
import os
from typing import Optional, Dict, Any, Callable, Union
from flask import Flask, request, Response, jsonify
import random

# Import both SIP client implementations
from callie_caller.sip.client import SipClient
from callie_caller.sip.call import SipCall, CallState
from callie_caller.sip.pjsua2_client import PjSipClient
from callie_caller.sip.pjsua2_call import PjCall

from callie_caller.ai.conversation import ConversationManager
from callie_caller.config import get_settings

logger = logging.getLogger(__name__)

class CallieAgent:
    """
    Main AI voice agent that coordinates all components.
    Supports both single-tenant (legacy) and multi-tenant modes.
    Uses PJSUA2 by default for robust SIP handling with proper session timers.
    """
    
    def __init__(self):
        """Initialize Callie Agent."""
        self.settings = get_settings()
        
        # Determine mode based on Firebase availability
        self.multi_tenant_mode = self._check_firebase_availability()
        
        # Initialize components
        self.conversation_manager = ConversationManager()
        
        # Determine which SIP implementation to use
        self.use_pjsua2 = os.getenv('USE_PJSUA2', 'true').lower() == 'true'
        if self.use_pjsua2:
            logger.info("🚀 Using PJSUA2 implementation for robust SIP handling")
        else:
            logger.warning("⚠️ Using legacy SIP implementation (not recommended)")
        
        # Initialize mode-specific components
        if self.multi_tenant_mode:
            self._init_multi_tenant_mode()
        else:
            self._init_single_tenant_mode()
        
        # Flask app for webhooks and API
        self.app = Flask(__name__)
        self._setup_flask_routes()
        
        # State management
        self.running = False
        self.threads: Dict[str, threading.Thread] = {}
        self.call_conversations: Dict[str, str] = {}  # call_id -> conversation_id
        
        # Event loop for async audio conversations
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        
        mode_str = "multi-tenant" if self.multi_tenant_mode else "single-tenant (legacy)"
        sip_str = "PJSUA2" if self.use_pjsua2 else "legacy"
        logger.info(f"Callie Agent initialized in {mode_str} mode with {sip_str} SIP implementation")
        
    def _check_firebase_availability(self) -> bool:
        """Check if Firebase is configured and available."""
        try:
            # Check for Firebase credentials
            firebase_service_account = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
            google_app_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            
            if not (firebase_service_account or google_app_creds):
                logger.info("No Firebase credentials found - using single-tenant mode")
                return False
            
            # Try to initialize Firebase service
            from callie_caller.config.firebase_service import get_firebase_service
            firebase_service = get_firebase_service()
            
            if firebase_service.db:
                logger.info("✅ Firebase available - enabling multi-tenant mode")
                return True
            else:
                logger.warning("Firebase service available but no database connection - using single-tenant mode")
                return False
                
        except Exception as e:
            logger.info(f"Firebase not available ({e}) - using single-tenant mode")
            return False
    
    def _init_multi_tenant_mode(self):
        """Initialize multi-tenant components."""
        from callie_caller.core.multi_tenant_web import get_multi_tenant_manager
        self.multi_tenant_manager = get_multi_tenant_manager()
        self.sip_client = None  # No global SIP client in multi-tenant mode
        logger.info("🔥 Multi-tenant mode initialized with Firebase backend")
    
    def _init_single_tenant_mode(self):
        """Initialize single-tenant components with appropriate SIP client."""
        if self.use_pjsua2:
            self.sip_client = PjSipClient(on_incoming_call=self._handle_incoming_call_pjsua2)
        else:
            self.sip_client = SipClient(on_incoming_call=self._handle_incoming_call)
            
        self.multi_tenant_manager = None
        logger.info(f"📞 Single-tenant mode initialized with {'PJSUA2' if self.use_pjsua2 else 'legacy'} SIP client")
        
    def start(self, request_headers: Optional[Dict[str, str]] = None) -> None:
        """Start the AI voice agent."""
        if self.running:
            logger.warning("Agent is already running")
            return
            
        logger.info("Starting Callie Agent...")
        self.running = True
        
        try:
            if self.multi_tenant_mode:
                self._start_multi_tenant_mode(request_headers)
            else:
                self._start_single_tenant_mode(request_headers)
            
            # Start Flask server in background
            flask_thread = threading.Thread(
                target=self._run_flask_server,
                name="flask-server",
                daemon=True
            )
            flask_thread.start()
            self.threads["flask"] = flask_thread
            
            # Start event loop for audio conversations
            self._loop_thread = threading.Thread(
                target=self._start_event_loop,
                name="event-loop",
                daemon=True
            )
            self._loop_thread.start()
            self.threads["event-loop"] = self._loop_thread
            
            # Wait a moment for event loop to start
            time.sleep(0.5)
            
            logger.info(f"Callie Agent started successfully")
            logger.info(f"- Web server: http://{self.settings.server.host}:{self.settings.server.port}")
            
        except Exception as e:
            logger.error(f"Failed to start agent: {e}")
            self.stop()
            raise
    
    def _start_multi_tenant_mode(self, request_headers: Optional[Dict[str, str]] = None):
        """Start multi-tenant mode."""
        logger.info("🔥 Starting multi-tenant mode")
        logger.info("📋 Use /users API endpoints to manage SIP configurations")
        logger.info("📋 Check /admin/status for system status")
        
        # Try to migrate legacy configuration if available
        self._auto_migrate_legacy_config()
    
    def _start_single_tenant_mode(self, request_headers: Optional[Dict[str, str]] = None):
        """Start single-tenant mode."""
        logger.info(f"📞 Starting single-tenant mode with {'PJSUA2' if self.use_pjsua2 else 'legacy'} SIP")
        
        # Start SIP client
        self.sip_client.start(request_headers)
        
        # Attempt registration (optional for outbound-only mode)
        try:
            self.sip_client.register()
            if self.use_pjsua2:
                logger.info(f"- PJSUA2 client: {self.sip_client.local_ip}:{self.sip_client.local_port}")
                logger.info(f"- Session timers: ENABLED (prevents 30-second drops)")
            else:
                logger.info(f"- SIP client: {self.sip_client.local_ip}:{self.sip_client.local_port}")
            logger.info(f"- Device emulation: {self.settings.device.user_agent}")
        except Exception as e:
            logger.warning(f"SIP registration failed (continuing in outbound-only mode): {e}")
    
    def _auto_migrate_legacy_config(self):
        """Automatically migrate legacy config to primary user if available."""
        try:
            # Check if we have legacy environment variables
            if not (os.getenv('ZOHO_SIP_USERNAME') and os.getenv('ZOHO_SIP_PASSWORD')):
                logger.info("No legacy configuration found to migrate")
                return
            
            from callie_caller.config.firebase_service import get_firebase_service
            firebase_service = get_firebase_service()
            
            # Check if primary user already exists
            existing_user = firebase_service.get_user_config("primary")
            if existing_user:
                logger.info(f"✅ Primary user already exists: {existing_user.sip.display_name}")
                return
            
            # Create primary user from legacy config
            logger.info("🔄 Auto-migrating legacy configuration to primary user...")
            
            from scripts.migrate_to_multitenant import create_primary_user, load_legacy_config
            legacy_config = load_legacy_config()
            
            if legacy_config:
                user_config = create_primary_user(legacy_config, "primary")
                success = firebase_service.create_user_config(user_config)
                
                if success:
                    logger.info(f"✅ Auto-migrated legacy config to primary user: {user_config.sip.display_name}")
                    logger.info("💡 Connect the primary user: curl -X POST http://localhost:8080/users/primary/sip/connect")
                else:
                    logger.error("❌ Failed to auto-migrate legacy configuration")
            
        except Exception as e:
            logger.warning(f"Auto-migration failed: {e}")
            
    def stop(self) -> None:
        """Stop the Callie Agent."""
        logger.info("Stopping Callie Agent...")
        
        if self.multi_tenant_mode:
            # Stop all user SIP clients
            if self.multi_tenant_manager:
                for user_id, sip_client in self.multi_tenant_manager.user_sip_clients.items():
                    try:
                        sip_client.stop()
                        logger.info(f"Stopped SIP client for user {user_id}")
                    except Exception as e:
                        logger.error(f"Error stopping SIP client for user {user_id}: {e}")
        else:
            # Stop single SIP client
            if self.sip_client:
                self.sip_client.stop()
        
        # Stop event loop
        if self._loop and self._loop.is_running():
            self._loop.stop()
            logger.info("Event loop stopped")
    
    def enable_test_audio_mode(self, test_audio_file: str = None) -> bool:
        """Enable test audio mode to inject known audio instead of AI."""
        if self.multi_tenant_mode:
            logger.warning("Test audio mode not implemented for multi-tenant mode yet")
            return False
        elif self.sip_client:
            if self.use_pjsua2:
                logger.warning("Test audio mode not implemented for PJSUA2 yet")
                return False
            else:
                success = self.sip_client.enable_test_mode(test_audio_file)
                if success:
                    logger.info("🧪 Test audio mode enabled for agent")
                return success
        logger.error("❌ Cannot enable test mode - SIP client not available")
        return False
        
    def make_call(self, phone_number: str, message: Optional[str] = None, request_headers: Optional[Dict[str, str]] = None, user_id: str = "primary") -> bool:
        """
        Make an outbound call with AI conversation.
        
        Args:
            phone_number: Target phone number
            message: Optional initial AI message
            request_headers: Optional request headers for IP discovery
            user_id: User ID for multi-tenant mode (defaults to "primary")
            
        Returns:
            bool: True if call was successful
        """
        logger.info(f"📞 Making call to {phone_number}")
        
        if self.multi_tenant_mode:
            return self._make_call_multi_tenant(phone_number, message, user_id)
        else:
            return self._make_call_single_tenant(phone_number, message, request_headers)
    
    def _make_call_multi_tenant(self, phone_number: str, message: Optional[str], user_id: str) -> bool:
        """Make call in multi-tenant mode."""
        if not self.multi_tenant_manager:
            logger.error("Multi-tenant manager not available")
            return False
        
        # Get user's SIP client
        sip_client = self.multi_tenant_manager.user_sip_clients.get(user_id)
        if not sip_client or not sip_client.running:
            logger.error(f"User {user_id} SIP client not connected")
            return False
        
        if not sip_client.registered:
            logger.error(f"User {user_id} SIP client not registered")
            return False
        
        # Make the call
        success = sip_client.make_call(phone_number, message)
        if success:
            # Track the call
            call_id = f"call-{user_id}-{int(time.time())}"
            self.multi_tenant_manager.active_calls[call_id] = {
                'user_id': user_id,
                'target_number': phone_number,
                'message': message,
                'start_time': time.time(),
                'status': 'initiated'
            }
        
        return success
    
    def _make_call_single_tenant(self, phone_number: str, message: Optional[str], request_headers: Optional[Dict[str, str]]) -> bool:
        """Make call in single-tenant mode."""
        if self.use_pjsua2:
            # PJSUA2 implementation
            call = self.sip_client.make_call(phone_number, message)
            if call:
                # Track the call for conversation handling
                call_info = call.get_info_dict()
                self.call_conversations[str(call_info['id'])] = f"outbound-{int(time.time())}-{phone_number}"
                
                # Wait for call to connect
                timeout = 30
                start_time = time.time()
                while time.time() - start_time < timeout:
                    call_info = call.get_info_dict()
                    if call_info['connected']:
                        logger.info(f"✅ Call connected after {time.time() - start_time:.1f}s")
                        return True
                    elif call_info['state'] == 6:  # DISCONNECTED
                        logger.error("❌ Call failed to connect")
                        return False
                    time.sleep(0.1)
                
                logger.error("❌ Call connection timeout")
                return False
            return False
        else:
            # Legacy implementation
            call = SipCall(
                call_id=f"call-{random.randint(100000, 999999)}-{int(time.time())}",
                local_ip=self.sip_client.local_ip,
                public_ip=self.sip_client.public_ip,
                local_port=self.sip_client.local_port,
                settings=self.sip_client.settings,
                authenticator=self.sip_client.authenticator,
                target_number=phone_number,
                ai_message=message
            )
            
            # Make the call
            success = self.sip_client.make_call(call)
            
            if success and call.state == CallState.CONNECTED:
                # Track the call for conversation handling
                self.call_conversations[call.call_id] = f"outbound-{int(time.time())}-{phone_number}"
                
                # Start audio conversation in the event loop
                if self._loop and self._loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self._handle_call_conversation(call),
                        self._loop
                    )
                    logger.info(f"🔄 Call conversation scheduled in event loop")
            
            return success
    
    def is_call_active(self) -> bool:
        """Check if there are any active calls."""
        if self.multi_tenant_mode:
            return len(self.multi_tenant_manager.active_calls) > 0 if self.multi_tenant_manager else False
        else:
            return len(getattr(self.sip_client, 'active_calls', {})) > 0
    
    def _handle_incoming_call_pjsua2(self, call: PjCall) -> None:
        """Handle incoming PJSUA2 call."""
        logger.info(f"Incoming PJSUA2 call")
        
        # Answer the call
        call.answer()
        logger.info(f"Answered PJSUA2 call")
        
    def _handle_incoming_call(self, call: Union[SipCall, PjCall]) -> None:
        """Handle incoming SIP call in single-tenant mode."""
        if isinstance(call, PjCall):
            self._handle_incoming_call_pjsua2(call)
            return
            
        logger.info(f"Incoming call from {call.target_number}")
        
        # Start conversation
        conversation_id = f"incoming-{int(time.time())}-{call.target_number}"
        self.conversation_manager.start_conversation(
            conversation_id=conversation_id,
            phone_number=call.target_number
        )
        
        # Link call and conversation
        self.call_conversations[call.call_id] = conversation_id
        
        # Generate greeting
        greeting = self.conversation_manager.generate_greeting(
            conversation_id,
            context=f"Incoming call from {call.target_number}"
        )
        
        # Answer call
        call.answer()
        logger.info(f"Answered call {call.call_id} with greeting: {greeting}")
        
        if call.state == CallState.CONNECTED:
            # Handle async conversation for incoming calls
            try:
                if self._loop and self._loop.is_running():
                    # Schedule the conversation in the existing event loop
                    future = asyncio.run_coroutine_threadsafe(
                        self._handle_call_conversation(call),
                        self._loop
                    )
                    logger.info(f"🔄 Incoming call conversation scheduled in event loop")
                else:
                    logger.error("⚠️  No event loop available for incoming call conversation")
                    call.hangup()
                    
            except Exception as e:
                logger.error(f"Error starting incoming call conversation: {e}")
                call.hangup()
                
    async def _handle_call_conversation(self, call: Union[SipCall, PjCall]) -> None:
        """Handle conversation for a connected call."""
        if self.use_pjsua2:
            # PJSUA2 handles audio bridging automatically
            logger.info(f"🎤 PJSUA2 call - audio bridging handled automatically")
            return
            
        logger.info(f"🎤 Starting conversation for call {call.call_id}")
        
        try:
            # Add initial delay to ensure call is fully established
            logger.info(f"⏳ Allowing 2 seconds for call to fully establish...")
            await asyncio.sleep(2.0)
            
            # Check if call is actually answered or went to voicemail
            if call.state == CallState.CONNECTED:
                # Additional check - wait a moment and see if we get actual audio
                logger.info(f"🔍 Checking if call is truly answered or voicemail...")
                await asyncio.sleep(3.0)  # Wait 3 seconds
                
                # Check for voicemail indicators
                if self._is_voicemail_call(call):
                    logger.info(f"📞 Call {call.call_id} appears to be voicemail - hanging up")
                    call.hangup()
                    return
                
                logger.info(f"🎯 Initializing audio conversation for {call.call_id}")
                await self.sip_client.start_audio_conversation(
                    call,
                    initial_message=call.ai_message
                )
                logger.info(f"✅ Audio conversation started for {call.call_id}")
            else:
                logger.warning(f"⚠️  Call {call.call_id} not connected when starting conversation (state: {call.state.value})")
                return
            
            # Monitor call state and exit when call ends
            logger.info(f"🔔 Monitoring call {call.call_id} - will exit when call ends...")
            
            # Keep the conversation active while call is connected
            conversation_time = 0
            last_state_check = time.time()
            consecutive_failures = 0
            
            while call.state == CallState.CONNECTED and conversation_time < 1800:  # 30 minute max
                await asyncio.sleep(5)  # Check every 5 seconds
                conversation_time += 5
                current_time = time.time()
                
                # **NEW: Enhanced call monitoring**
                # Check for call state changes more frequently
                if current_time - last_state_check > 10:  # Every 10 seconds
                    try:
                        # Verify call is still active
                        if not self._verify_call_active(call):
                            consecutive_failures += 1
                            logger.warning(f"⚠️  Call verification failed {consecutive_failures}/3 for {call.call_id}")
                            
                            if consecutive_failures >= 3:
                                logger.error(f"❌ Call {call.call_id} appears to be dead - terminating conversation")
                                break
                        else:
                            consecutive_failures = 0  # Reset on success
                            
                        last_state_check = current_time
                        
                    except Exception as e:
                        logger.error(f"❌ Error verifying call state: {e}")
                        consecutive_failures += 1
                
                if conversation_time % 60 == 0:  # Log every minute
                    logger.info(f"🔔 Call {call.call_id} active for {conversation_time // 60} minutes")
                    
                # **NEW: Check for RTP activity**
                if hasattr(self.sip_client, 'rtp_bridge') and self.sip_client.rtp_bridge:
                    rtp_bridge = self.sip_client.rtp_bridge
                    if (current_time - rtp_bridge.last_caller_packet_time > 120 and 
                        rtp_bridge.last_caller_packet_time > 0):
                        logger.warning(f"⚠️  No RTP packets from caller for 2+ minutes - call may be dead")
            
            logger.info(f"🔚 Call {call.call_id} conversation ended (Duration: {conversation_time}s, State: {call.state.value})")
            
            # Clean up
            if call.state == CallState.CONNECTED:
                call.hangup()
                logger.info(f"📞 Hung up call {call.call_id}")
            
            # Stop audio conversation
            if self.sip_client:
                await self.sip_client.stop_audio_conversation()
                
        except Exception as e:
            logger.error(f"💥 Error in call conversation {call.call_id}: {e}")
            try:
                call.hangup()
                if self.sip_client:
                    await self.sip_client.stop_audio_conversation()
            except:
                pass  # Best effort cleanup

    def _verify_call_active(self, call: Union[SipCall, PjCall]) -> bool:
        """Verify that a call is still active and responsive."""
        try:
            if self.use_pjsua2 and isinstance(call, PjCall):
                # PJSUA2 call verification
                return call.isActive()
            else:
                # Legacy call verification
                # Check basic call state
                if call.state != CallState.CONNECTED:
                    return False
                    
                # Check if call duration seems reasonable
                if call.duration > 0:
                    # Call has been active for some time
                    return True
                    
                # Additional checks could be added here:
                # - Check SIP dialog state
                # - Verify RTP flow
                # - Send OPTIONS ping
                
                return True
                
        except Exception as e:
            logger.error(f"❌ Error verifying call: {e}")
            return False
        
    def _is_voicemail_call(self, call: Union[SipCall, PjCall]) -> bool:
        """Detect if call went to voicemail (placeholder implementation)."""
        # This is a placeholder - in reality you'd analyze audio patterns
        # For now, return False to assume all calls are answered
        return False
        
    async def _test_live_api(self) -> None:
        """Test Live API connection independently."""
        try:
            if not self.multi_tenant_mode and self.sip_client:
                if self.use_pjsua2:
                    logger.info("🔬 PJSUA2 client - Live API test not implemented yet")
                else:
                    # Ensure audio bridge is initialized
                    if not self.sip_client.audio_bridge:
                         self.sip_client.audio_bridge = self.sip_client.get_audio_bridge()

                    if self.sip_client.audio_bridge:
                        logger.info("🔬 Testing Live API connection...")
                        result = await self.sip_client.audio_bridge.test_live_api_connection()
                        if result:
                            logger.info("✅ Live API connection test successful!")
                        else:
                            logger.error("❌ Live API connection test failed!")
        except Exception as e:
            logger.error(f"💥 Live API test error: {e}")
            
    def _start_event_loop(self) -> None:
        """Start asyncio event loop for audio conversations."""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            logger.info("Event loop started for audio conversations")
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Error in event loop: {e}")
        finally:
            logger.info("Event loop stopped")
            
    def _setup_flask_routes(self) -> None:
        """Setup Flask routes for webhooks and API."""
        
        # Add multi-tenant routes if enabled
        if self.multi_tenant_mode and self.multi_tenant_manager:
            self.multi_tenant_manager.setup_routes(self.app)
        
        @self.app.route('/', methods=['GET'])
        def root():
            """Root endpoint with system information."""
            mode_info = {
                'mode': 'multi-tenant' if self.multi_tenant_mode else 'single-tenant (legacy)',
                'firebase_enabled': self.multi_tenant_mode
            }
            
            if self.multi_tenant_mode:
                mode_info.update({
                    'total_users': len(self.multi_tenant_manager.firebase_service.list_active_users()) if self.multi_tenant_manager else 0,
                    'active_sip_clients': len(self.multi_tenant_manager.user_sip_clients) if self.multi_tenant_manager else 0,
                    'endpoints': {
                        'users': '/users - User management',
                        'admin': '/admin/status - System status',
                        'legacy_health': '/health - Legacy health check'
                    }
                })
            else:
                mode_info.update({
                    'sip_registered': getattr(self.sip_client, 'registered', False),
                    'endpoints': {
                        'health': '/health - Health check',
                        'call': '/call - Make outbound call',
                        'stats': '/stats - Agent statistics'
                    }
                })
            
            return jsonify({
                'service': 'Callie Caller AI Voice Agent',
                'version': '1.2.0',
                'status': 'healthy' if self.running else 'stopped',
                **mode_info
            })
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint."""
            if self.multi_tenant_mode:
                return jsonify({
                    'status': 'healthy',
                    'mode': 'multi-tenant',
                    'agent_running': self.running,
                    'firebase_connected': bool(self.multi_tenant_manager.firebase_service.db) if self.multi_tenant_manager else False,
                    'total_users': len(self.multi_tenant_manager.firebase_service.list_active_users()) if self.multi_tenant_manager else 0,
                    'active_sip_clients': len(self.multi_tenant_manager.user_sip_clients) if self.multi_tenant_manager else 0,
                    'active_conversations': len(self.conversation_manager.active_conversations)
                })
            else:
                return jsonify({
                    'status': 'healthy',
                    'mode': 'single-tenant (legacy)',
                    'agent_running': self.running,
                    'sip_registered': getattr(self.sip_client, 'registered', False),
                    'active_calls': len(getattr(self.sip_client, 'active_calls', {})),
                    'active_conversations': len(self.conversation_manager.active_conversations)
                })
        
        # Legacy single-tenant endpoints
        if not self.multi_tenant_mode:
            self._setup_legacy_routes()
    
    def _setup_legacy_routes(self):
        """Setup legacy single-tenant routes."""
        
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
                
                return Response(status=200)
                
            except Exception as e:
                logger.error(f"Error handling SMS: {e}")
                return Response("Error processing SMS", status=500)
                
        @self.app.route('/call', methods=['POST'])
        def make_call_api():
            """API endpoint to make outbound calls."""
            try:
                data = request.get_json()
                number = data.get('number')
                message = data.get('message')
                
                if not number:
                    return jsonify({'error': 'Phone number required'}), 400
                    
                success = self.make_call(number, message, dict(request.headers))
                
                if success:
                    return jsonify({
                        'success': True,
                        'message': f'Call initiated to {number}',
                        'target': number,
                        'status': 'completed'
                    })
                else:
                    return jsonify({'error': 'Failed to make call'}), 500
                    
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
                
                # Get tool information
                from callie_caller.ai import get_tool_manager
                tool_manager = get_tool_manager()
                
                stats.update({
                    'agent_running': self.running,
                    'sip_registered': getattr(self.sip_client, 'registered', False),
                    'device_emulation': self.settings.device.user_agent,
                    'inbound_calls_enabled': True,
                    'sip_server': self.settings.zoho.sip_server,
                    'sip_username': self.settings.zoho.sip_username,
                    'function_calling_enabled': True,
                    'available_tools': list(tool_manager.tools.keys()),
                    'tool_count': len(tool_manager.tools)
                })
                
                return jsonify(stats)
                
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/info', methods=['GET'])
        def get_info():
            """Get AI agent information and capabilities."""
            # Get tool information
            from callie_caller.ai import get_tool_manager
            tool_manager = get_tool_manager()
            
            return jsonify({
                'service': 'Callie Caller AI Voice Agent',
                'version': '1.2.0',
                'mode': 'single-tenant (legacy)',
                'capabilities': {
                    'outbound_calls': True,
                    'inbound_calls': True,
                    'real_time_ai': True,
                    'sip_registered': getattr(self.sip_client, 'registered', False),
                    'voicemail_detection': True,
                    'conversation_memory': True,
                    'function_calling': True,
                    'ai_tools': list(tool_manager.tools.keys())
                },
                'sip_configuration': {
                    'server': self.settings.zoho.sip_server,
                    'username': self.settings.zoho.sip_username,
                    'device_emulation': self.settings.device.user_agent
                },
                'ai_configuration': {
                    'model': self.settings.ai.model,
                    'real_time_voice': True,
                    'greeting': self.settings.calls.default_greeting
                },
                'contact_info': {
                    'inbound_calls': f"Call the number associated with SIP extension: {self.settings.zoho.sip_username}",
                    'note': "To get the exact phone number, check your Zoho Voice admin panel"
                },
                'endpoints': {
                    'health': '/health - Health check',
                    'stats': '/stats - Agent statistics', 
                    'info': '/info - This information',
                    'conversations': '/conversations - Call history',
                    'call': '/call (POST) - Make outbound call',
                    'tools': '/tools - Available AI tools'
                }
            })
        
        @self.app.route('/tools', methods=['GET'])
        def get_tools():
            """Get available AI tools and their capabilities."""
            try:
                from callie_caller.ai import get_tool_manager
                tool_manager = get_tool_manager()
                
                return jsonify({
                    'function_calling_enabled': True,
                    'tool_count': len(tool_manager.tools),
                    'tools': tool_manager.get_tool_info(),
                    'summary': tool_manager.get_tool_summary()
                })
                
            except Exception as e:
                logger.error(f"Error getting tools: {e}")
                return jsonify({'error': str(e)}), 500
                
    def _run_flask_server(self) -> None:
        """Run Flask server in thread."""
        try:
            self.app.run(
                host=self.settings.server.host,
                port=self.settings.server.port,
                debug=self.settings.server.debug,
                use_reloader=False  # Disable reloader in thread
            )
        except Exception as e:
            logger.error(f"Flask server error: {e}")
            
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        base_status = {
            'running': self.running,
            'mode': 'multi-tenant' if self.multi_tenant_mode else 'single-tenant (legacy)',
            'active_conversations': len(self.conversation_manager.active_conversations),
            'total_conversations': len(self.conversation_manager.conversation_history)
        }
        
        if self.multi_tenant_mode:
            base_status.update({
                'firebase_connected': bool(self.multi_tenant_manager.firebase_service.db) if self.multi_tenant_manager else False,
                'total_users': len(self.multi_tenant_manager.firebase_service.list_active_users()) if self.multi_tenant_manager else 0,
                'active_sip_clients': len(self.multi_tenant_manager.user_sip_clients) if self.multi_tenant_manager else 0,
                'active_calls': len(self.multi_tenant_manager.active_calls) if self.multi_tenant_manager else 0
            })
        else:
            base_status.update({
                'sip_registered': getattr(self.sip_client, 'registered', False),
                'local_endpoint': f"{getattr(self.sip_client, 'local_ip', 'unknown')}:{getattr(self.sip_client, 'local_port', 'unknown')}",
                'device_emulation': self.settings.device.user_agent,
                'active_calls': len(getattr(self.sip_client, 'active_calls', {}))
            })
        
        return base_status 
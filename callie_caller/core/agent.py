"""
Main Callie Agent - AI Voice Assistant for Zoho Voice.
Coordinates SIP calling, AI conversation, and call management.
"""

import logging
import threading
import time
import asyncio
from typing import Optional, Dict, Any, Callable
from flask import Flask, request, Response, jsonify
import random

from callie_caller.config import get_settings
from callie_caller.sip.client import SipClient
from callie_caller.ai.conversation import ConversationManager
from callie_caller.sip.call import SipCall, CallState

logger = logging.getLogger(__name__)

class CallieAgent:
    """
    Main AI voice agent that coordinates all components.
    Handles incoming/outgoing calls with intelligent conversation.
    """
    
    def __init__(self):
        """Initialize Callie Agent."""
        self.settings = get_settings()
        
        # Initialize components
        self.conversation_manager = ConversationManager()
        self.sip_client = SipClient(on_incoming_call=self._handle_incoming_call)
        
        # Flask app for SMS and webhooks
        self.app = Flask(__name__)
        self._setup_flask_routes()
        
        # State management
        self.running = False
        self.threads: Dict[str, threading.Thread] = {}
        self.call_conversations: Dict[str, str] = {}  # call_id -> conversation_id
        
        # Event loop for async audio conversations
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        
        logger.info("Callie Agent initialized")
        
    def start(self) -> None:
        """Start the AI voice agent."""
        if self.running:
            logger.warning("Agent is already running")
            return
            
        logger.info("Starting Callie Agent...")
        self.running = True
        
        try:
            # Start SIP client
            self.sip_client.start()
            
            # Attempt registration (optional for outbound-only mode)
            try:
                self.sip_client.register()
            except Exception as e:
                logger.warning(f"SIP registration failed (continuing in outbound-only mode): {e}")
            
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
            logger.info(f"- SIP client: {self.sip_client.local_ip}:{self.sip_client.local_port}")
            logger.info(f"- Device emulation: {self.settings.device.user_agent}")
            logger.info(f"- Web server: http://{self.settings.server.host}:{self.settings.server.port}")
            
        except Exception as e:
            logger.error(f"Failed to start agent: {e}")
            self.stop()
            raise
            
    def stop(self) -> None:
        """Stop the Callie Agent."""
        logger.info("Stopping Callie Agent...")
        
        # Stop SIP client
        if self.sip_client:
            self.sip_client.stop()
        
        # Stop event loop
        if self._loop and self._loop.is_running():
            self._loop.stop()
            logger.info("Event loop stopped")
    
    def enable_test_audio_mode(self, test_audio_file: str = None) -> bool:
        """Enable test audio mode to inject known audio instead of AI."""
        if self.sip_client:
            success = self.sip_client.enable_test_mode(test_audio_file)
            if success:
                logger.info("🧪 Test audio mode enabled for agent")
            return success
        logger.error("❌ Cannot enable test mode - SIP client not available")
        return False
        
    def make_call(self, phone_number: str, message: Optional[str] = None) -> bool:
        """
        Make an outbound call with AI conversation.
        
        Args:
            phone_number: Target phone number
            message: Optional initial AI message
            
        Returns:
            bool: True if call was successful
        """
        logger.info(f"📞 Making call to {phone_number}")
        
        # Create a new call
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
            logger.info(f"🎉 Call {call.call_id} connected successfully!")
            
            # 🔧 FIX: Run async conversation in event loop
            try:
                if self._loop and self._loop.is_running():
                    # Schedule the conversation in the existing event loop
                    future = asyncio.run_coroutine_threadsafe(
                        self._handle_call_conversation(call),
                        self._loop
                    )
                    
                    # Wait for the conversation to complete
                    future.result()  # This will block until call ends
                    
                else:
                    # No event loop running, create a new one
                    logger.info("🔄 Creating new event loop for call conversation...")
                    asyncio.run(self._handle_call_conversation(call))
                    
            except Exception as e:
                logger.error(f"Error in async call handling: {e}")
                call.fail(f"Async error: {e}")
            
            logger.info(f"📞 Call {call.call_id} conversation completed")
            return True
            
        else:
            if not success:
                logger.error(f"❌ Call to {phone_number} failed to connect")
            elif call.state == CallState.RINGING:
                logger.info(f"📞 Call to {phone_number} is ringing but not answered")
                
                # 🔧 FIX: For ringing calls, still run conversation monitoring  
                try:
                    if self._loop and self._loop.is_running():
                        future = asyncio.run_coroutine_threadsafe(
                            self._handle_call_conversation(call),
                            self._loop
                        )
                        future.result()
                    else:
                        asyncio.run(self._handle_call_conversation(call))
                except Exception as e:
                    logger.error(f"Error in ringing call handling: {e}")
                    
            return False
        
    def _handle_incoming_call(self, call: SipCall) -> None:
        """Handle incoming SIP call."""
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
            # 🔧 FIX: Properly handle async conversation for incoming calls
            try:
                if self._loop and self._loop.is_running():
                    # Schedule the conversation in the existing event loop
                    future = asyncio.run_coroutine_threadsafe(
                        self._handle_call_conversation(call),
                        self._loop
                    )
                    logger.info(f"🔄 Incoming call conversation scheduled in event loop")
                    # Don't wait here - let it run asynchronously
                else:
                    # No event loop running, this shouldn't happen but handle gracefully
                    logger.error("⚠️  No event loop available for incoming call conversation")
                    call.hangup()
                    
            except Exception as e:
                logger.error(f"Error starting incoming call conversation: {e}")
                call.hangup()

    # The _monitor_call method is no longer needed as the SIP client now blocks
    # until a call is connected or fails. We can remove it.
        
    async def _handle_call_conversation(self, call: SipCall) -> None:
        """Handle conversation for a connected call."""
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
            
            # 🔔 Monitor call state and exit when call ends
            logger.info(f"🔔 Monitoring call {call.call_id} - will exit when call ends...")
            
            # Keep the conversation active while call is connected
            conversation_time = 0
            no_audio_time = 0
            last_audio_packets = 0
            
            while call.state == CallState.CONNECTED:
                await asyncio.sleep(1.0)  # Check every second
                conversation_time += 1
                
                # Check for audio activity to detect if call is actually active
                if self.sip_client.rtp_bridge:
                    current_packets = self.sip_client.rtp_bridge.packets_forwarded
                    if current_packets == last_audio_packets:
                        no_audio_time += 1
                    else:
                        no_audio_time = 0  # Reset if we got audio
                    last_audio_packets = current_packets
                    
                    # If no audio for too long, might be voicemail or dead call
                    if no_audio_time > 10 and conversation_time > 15:  # No audio for 10+ seconds after 15 seconds
                        logger.warning(f"⚠️  No audio activity for {no_audio_time}s - possible voicemail or dead call")
                        if no_audio_time > 30:  # 30 seconds of silence
                            logger.info(f"📞 Hanging up due to extended silence (likely voicemail)")
                            call.hangup()
                            break
                
                # Auto hangup after reasonable time limit
                if conversation_time > 300:  # 5 minutes max
                    logger.info(f"⏰ Call {call.call_id} reached maximum duration, hanging up")
                    call.hangup()
                    break
                
                # Log periodic status
                duration = call.duration
                if conversation_time % 10 == 0:  # Every 10 seconds
                    logger.info(f"📞 Call active for {duration:.0f} seconds - state: {call.state.value}")
                    
                    # Enhanced bridge statistics
                    if self.sip_client.rtp_bridge:
                        bridge_stats = {
                            'packets_forwarded': self.sip_client.rtp_bridge.packets_forwarded,
                            'packets_to_ai': self.sip_client.rtp_bridge.packets_to_ai,
                            'packets_from_ai': self.sip_client.rtp_bridge.packets_from_ai,
                            'caller_packets_recorded': self.sip_client.rtp_bridge.caller_packets_recorded,
                            'remote_packets_recorded': self.sip_client.rtp_bridge.remote_packets_recorded
                        }
                        
                        logger.info(f"🌉 Bridge stats: {bridge_stats['packets_forwarded']} received, {bridge_stats['packets_to_ai']} to AI, {bridge_stats['packets_from_ai']} from AI")
                        logger.info(f"🔇 Silence time: {no_audio_time}s")
                        
                        if bridge_stats['packets_forwarded'] == 0:
                            # Enhanced diagnostics for no packet flow
                            logger.warning("⚠️  NO RTP PACKETS through bridge - audio may not be flowing correctly")
                            logger.info("🔧 Troubleshooting suggestions:")
                            logger.info("   • Check if remote endpoint is sending to the correct IP/port")
                            logger.info("   • Verify NAT/firewall allows UDP traffic on bridge port")
                            logger.info(f"   • Bridge is listening on ALL INTERFACES:{self.sip_client.rtp_bridge.local_port}")
                            
                            if self.sip_client.rtp_bridge.remote_endpoint:
                                logger.info(f"   • Remote endpoint: {self.sip_client.rtp_bridge.remote_endpoint.ip}:{self.sip_client.rtp_bridge.remote_endpoint.port}")
                            else:
                                logger.warning("   • No remote endpoint configured yet!")
                        else:
                            logger.info(f"✅ Audio flowing! WAV Recording: {bridge_stats['caller_packets_recorded']} caller, {bridge_stats['remote_packets_recorded']} remote packets to WAV files")
                    else:
                        logger.warning("⚠️  No RTP bridge active - this shouldn't happen during a call")
                
                # Additional early logging for first few seconds
                elif conversation_time <= 5:
                    logger.info(f"🕐 Call conversation active for {conversation_time} seconds")
            
            # Call ended - log the reason
            logger.info(f"📞 Call {call.call_id} ended with state: {call.state.value}")
            logger.info(f"⏱️  Total call duration: {call.duration:.1f} seconds")
            
        except Exception as e:
            logger.error(f"💥 Error in call conversation: {e}")
            import traceback
            logger.error(f"📋 Stack trace: {traceback.format_exc()}")
            call.fail(f"Conversation error: {e}")
        finally:
            # Ensure proper cleanup
            try:
                logger.info(f"🧹 Cleaning up call {call.call_id}")
                
                # Stop audio conversation
                await self.sip_client.stop_audio_conversation()
                logger.info(f"🔇 Audio conversation stopped for {call.call_id}")
                
                # Properly terminate the call if not already ended
                if call.state not in [CallState.ENDED, CallState.FAILED]:
                    self.sip_client.terminate_call(call)
                    logger.info(f"📞 Call {call.call_id} properly terminated")
                    
            except Exception as cleanup_error:
                logger.error(f"💥 Error during call cleanup: {cleanup_error}")
    
    def _is_voicemail_call(self, call: SipCall) -> bool:
        """Detect if call went to voicemail based on various indicators."""
        # Check call duration - if "connected" immediately, likely voicemail
        if call.state == CallState.CONNECTED and call.duration < 2:
            logger.info("🔍 Call connected very quickly - checking for voicemail...")
            
            # Check if we have RTP bridge with no bidirectional audio
            if self.sip_client.rtp_bridge:
                # Wait a moment to see if we get actual conversation audio
                time.sleep(2)
                
                # If we only get audio in one direction or very regular patterns, likely voicemail
                packets_forwarded = self.sip_client.rtp_bridge.packets_forwarded
                packets_to_ai = self.sip_client.rtp_bridge.packets_to_ai
                
                if packets_forwarded > 0 and packets_to_ai == 0:
                    logger.info("🔍 Receiving audio but not sending to AI - likely voicemail greeting")
                    return True
                    
                if packets_forwarded > 50:  # Lots of one-way audio quickly
                    logger.info("🔍 High volume one-way audio - likely voicemail greeting")
                    return True
        
        return False
        
    async def _test_live_api(self) -> None:
        """Test Live API connection independently."""
        try:
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
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint."""
            return jsonify({
                'status': 'healthy',
                'agent_running': self.running,
                'sip_registered': getattr(self.sip_client, 'registered', False),
                'active_calls': len(getattr(self.sip_client, 'active_calls', {})),
                'active_conversations': len(self.conversation_manager.active_conversations)
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
                    
                call = self.make_call(number, message)
                
                if call:
                    return jsonify({
                        'success': True,
                        'call_id': call.call_id,
                        'target': call.target_number,
                        'state': call.state.value
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
                stats.update({
                    'agent_running': self.running,
                    'sip_registered': getattr(self.sip_client, 'registered', False),
                    'device_emulation': self.settings.device.user_agent
                })
                
                return jsonify(stats)
                
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
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
        return {
            'running': self.running,
            'sip_registered': getattr(self.sip_client, 'registered', False),
            'local_endpoint': f"{getattr(self.sip_client, 'local_ip', 'unknown')}:{getattr(self.sip_client, 'local_port', 'unknown')}",
            'device_emulation': self.settings.device.user_agent,
            'active_calls': len(getattr(self.sip_client, 'active_calls', {})),
            'active_conversations': len(self.conversation_manager.active_conversations),
            'total_conversations': len(self.conversation_manager.conversation_history)
        } 
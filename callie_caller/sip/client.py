"""
SIP Client for Yealink phone emulation.
Handles SIP registration, call management, and authentication with Zoho Voice.
"""

import socket
import time
import random
import logging
import asyncio
import threading
from typing import Optional, Callable, Dict, Any, List

from callie_caller.config import get_settings
from callie_caller.utils.network import get_public_ip
from callie_caller.sip.auth import SipAuthenticator
from callie_caller.sip.call import SipCall, CallState
from callie_caller.sip.sdp import extract_audio_params_from_sip_response
from callie_caller.sip.rtp import RtpHandler
from callie_caller.sip.rtp_bridge import RtpBridge
from callie_caller.ai import AudioBridge
from .parser import SipResponse, parse_sip_response

logger = logging.getLogger(__name__)

class SipClient:
    """
    Main SIP client for Yealink phone emulation.
    Handles registration, authentication, call management, and RTP audio.
    """
    
    def __init__(self, on_incoming_call: Optional[Callable[[SipCall], None]] = None):
        """
        Initialize SIP client.
        
        Args:
            on_incoming_call: Callback for handling incoming calls
        """
        self.settings = get_settings()
        self.authenticator = SipAuthenticator(self.settings)
        self.on_incoming_call = on_incoming_call
        
        self.socket: Optional[socket.socket] = None
        self.local_ip: Optional[str] = None
        self.public_ip: Optional[str] = None
        self.local_port: Optional[int] = None
        self.running = False
        self.registered = False
        self.active_calls: Dict[str, SipCall] = {}
        
        # Threading for message handling
        self._listener_thread: Optional[threading.Thread] = None
        self._response_events: Dict[str, threading.Event] = {}
        self._received_responses: Dict[str, SipResponse] = {}
        
        # RTP and audio handling
        self.rtp_bridge: Optional[RtpBridge] = None
        self.audio_bridge: Optional[AudioBridge] = None
        self._conversation_task: Optional[asyncio.Task] = None
        
    async def start_audio_conversation(self, call: SipCall, initial_message: Optional[str] = None) -> None:
        """
        Start real-time audio conversation for a connected call.
        
        Args:
            call: The active SIP call
            initial_message: Optional initial AI message
        """
        if call.state not in [CallState.CONNECTED, CallState.RINGING]:
            logger.warning(f"Cannot start conversation for call in state: {call.state}")
            return
            
        logger.info(f"🎤 Starting AI audio conversation for call {call.call_id}")
        
        try:
            # Initialize audio bridge if not already done
            if not self.audio_bridge:
                self.audio_bridge = AudioBridge()
                # Store reference to current event loop for sync callbacks
                self.audio_bridge._loop = asyncio.get_event_loop()
                
            # Connect the RTP bridge to the AI audio bridge
            if self.rtp_bridge:
                logger.info("🔗 Connecting RTP Bridge to AI...")
                
                # Connect audio pipeline  
                def rtp_to_ai_callback(audio_data: bytes, source: str):
                    """Callback to send RTP audio to AI"""
                    if self.audio_bridge and source == "caller":
                        self.audio_bridge.send_sip_audio_sync(audio_data)
                
                def ai_to_rtp_callback(ai_audio: bytes):
                    """Callback to send AI audio to RTP"""
                    logger.info(f"🤖 AI callback received {len(ai_audio)} bytes - forwarding to RTP bridge")
                    if self.rtp_bridge:
                        # Check if we're in test mode
                        if hasattr(self.rtp_bridge, 'test_mode') and self.rtp_bridge.test_mode:
                            # Inject test audio instead of AI audio
                            test_packet = self.rtp_bridge.get_test_audio_packet()
                            if test_packet:
                                logger.info(f"🧪 Injecting test audio packet instead of AI audio")
                                self.rtp_bridge.send_ai_audio(test_packet, target="caller")
                            return
                        
                        self.rtp_bridge.send_ai_audio(ai_audio, target="caller")
                    else:
                        logger.error("❌ No RTP bridge available for AI audio")
                
                # Set up RTP Bridge → AI callback (user's voice to AI)
                self.rtp_bridge.set_audio_callback(rtp_to_ai_callback)
                
                # Set up AI → RTP Bridge callback (AI's voice to user)
                if self.audio_bridge:
                    self.audio_bridge.set_sip_audio_callback(ai_to_rtp_callback)
                logger.info("✅ Audio pipeline connected: RTP Bridge ↔ AI ↔ RTP Bridge")

            # Start the conversation
            self._conversation_task = asyncio.create_task(
                self.audio_bridge.start_conversation(initial_message)
            )
            
            logger.info("🎵 Live AI conversation started!")
            
        except Exception as e:
            logger.error(f"Failed to start audio conversation: {e}")
    
    async def stop_audio_conversation(self) -> None:
        """Stop the active audio conversation."""
        if self.audio_bridge:
            await self.audio_bridge.stop_conversation()
            
        if self._conversation_task and not self._conversation_task.done():
            self._conversation_task.cancel()
            
        logger.info("🔇 Audio conversation stopped")

    def start(self) -> bool:
        """Start the SIP client and its message listener."""
        try:
            # Discover public IP for NAT traversal
            self.public_ip = get_public_ip()
            
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Get local IP and bind to dynamic port
            self.local_ip = self._get_local_ip()
            self.socket.bind((self.local_ip, 0))
            self.local_port = self.socket.getsockname()[1]
            
            logger.info(f"SIP client started on {self.local_ip}:{self.local_port} (Public: {self.public_ip})")
            logger.info(f"Emulating: {self.settings.device.user_agent}")
            
            # Start the background listener thread
            self.running = True
            self._listener_thread = threading.Thread(target=self._message_listener_loop, daemon=True)
            self._listener_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start SIP client: {e}")
            return False
    
    def register(self) -> bool:
        """Register with SIP server with authentication."""
        logger.info(f"Registering with {self.settings.zoho.sip_server}")
        
        # Create initial REGISTER message
        call_id = f"reg-{random.randint(100000, 999999)}-{int(time.time())}"
        from_tag = f"tag-{random.randint(1000, 9999)}"
        cseq = 1
        
        register_msg = self.authenticator.create_register_request(
            local_ip=self.local_ip,
            public_ip=self.public_ip,
            local_port=self.local_port,
            call_id=call_id,
            from_tag=from_tag,
            cseq=cseq
        )
        
        try:
            # Send initial REGISTER and wait for 401/407 response
            response = self._send_request_and_wait(f"{cseq} REGISTER", register_msg)
            
            if not response:
                logger.error("No response to initial REGISTER request")
                return False
                
            if response.status_code not in [401, 407]:
                logger.error(f"Unexpected response to REGISTER: {response.status_code} {response.status_text}")
                return False

            # We received a challenge, now create and send an authenticated REGISTER
            logger.info("Authentication required, sending authenticated REGISTER...")
            cseq += 1
            auth_header = response.headers.get('www-authenticate') or response.headers.get('proxy-authenticate')
            
            auth_register_msg = self.authenticator.create_register_request(
                local_ip=self.local_ip,
                public_ip=self.public_ip,
                local_port=self.local_port,
                call_id=call_id,
                from_tag=from_tag,
                cseq=cseq,
                auth_header=auth_header
            )
            
            # Send authenticated REGISTER and wait for 200 OK
            final_response = self._send_request_and_wait(f"{cseq} REGISTER", auth_register_msg)
            
            if final_response and final_response.status_code == 200:
                logger.info("✅ SIP registration successful!")
                self.registered = True
                return True
            else:
                status = f"{final_response.status_code} {final_response.status_text}" if final_response else "No Response"
                logger.error(f"❌ SIP registration failed. Final response: {status}")
                return False
                
        except Exception as e:
            logger.error(f"Registration failed: {e}", exc_info=True)
            return False

    def make_call(self, call: SipCall) -> bool:
        """
        Make an outbound call. This is a blocking operation until the call is
        connected or fails.
        
        Args:
            call: SipCall object with call details
            
        Returns:
            bool: True if call was successfully connected, False otherwise
        """
        logger.info(f"Making call to {call.target_number}")
        self.active_calls[call.call_id] = call
        
        try:
            # Step 1: Start RTP bridge BEFORE sending INVITE
            logger.info("🌉 Starting RTP bridge for media relay...")
            self.rtp_bridge = RtpBridge(self.local_ip)
            bridge_port = self.rtp_bridge.start_bridge()
            if not bridge_port:
                logger.error("❌ Failed to start RTP bridge")
                return False
            logger.info(f"🌉 RTP bridge listening on {self.local_ip}:{bridge_port}")
            
            # Step 2: Configure call to use bridge port in SDP
            call.rtp_port = bridge_port
            
            # Step 3: Send initial INVITE
            invite_msg = call.create_invite_message()
            response = self._send_request_and_wait(f"{call.cseq} INVITE", invite_msg)
            
            # Step 4: Handle authentication if required
            if response and response.status_code in [401, 407]:
                logger.info("Authentication required for call, sending authenticated INVITE...")
                call.cseq += 1
                auth_header = response.headers.get('www-authenticate') or response.headers.get('proxy-authenticate')
                
                auth_invite = call.create_authenticated_invite_message(
                    auth_header=auth_header,
                    is_proxy_auth=(response.status_code == 407)
                )
                # Don't wait here, the response will be handled by the main listener
                self._send_message(auth_invite)

            elif response and response.status_code >= 400:
                logger.error(f"Call failed with initial response: {response.status_code} {response.status_text}")
                call.fail(f"Initial error: {response.status_code}")
                return False
                
            # Step 5: Wait for the call to be connected
            return self._wait_for_call_to_connect(call)

        except Exception as e:
            logger.error(f"Call initiation failed: {e}", exc_info=True)
            call.fail(f"Initiation error: {e}")
            if self.rtp_bridge:
                self.rtp_bridge.stop_bridge()
                self.rtp_bridge = None
            return False

    def _wait_for_call_to_connect(self, call: SipCall) -> bool:
        """Waits for a 18x or 200 response to an INVITE."""
        call_setup_timeout = 60 
        start_time = time.time()

        logger.info("⏳ Waiting for call to connect...")
        while time.time() - start_time < call_setup_timeout:
            if call.state == CallState.CONNECTED:
                break
            if call.state in [CallState.FAILED, CallState.ENDED]:
                logger.error(f"❌ Call entered terminal state {call.state.value} while waiting to connect.")
                return False
            time.sleep(0.2) # <-- CRUCIAL: Give listener thread time to process messages

        if call.state == CallState.CONNECTED:
            logger.info("🎉 Call Answered and Connected!")
            
            # Send ACK for the 200 OK
            ack_msg = call.create_ack_message()
            self._send_message(ack_msg)
            
            # Configure RTP bridge with remote endpoint from 200 OK's SDP
            if call.remote_audio_params and self.rtp_bridge:
                logger.info(f"🎤 Remote audio endpoint: {call.remote_audio_params.ip_address}:{call.remote_audio_params.port}")
                self.rtp_bridge.set_remote_endpoint(call.remote_audio_params)
                bridge_port = self.rtp_bridge.get_bridge_port()
                logger.info(f"🌉 RTP bridge configured for media path: Phone ↔️ Bridge ({bridge_port}) ↔️ Remote")
                
                # Log SDP configuration for debugging
                logger.info(f"📋 SDP Configuration Summary:")
                logger.info(f"   • Bridge listening on: ALL INTERFACES:{bridge_port}")
                logger.info(f"   • SDP advertised: {call.public_ip or call.local_ip}:{bridge_port}")
                logger.info(f"   • Remote sends to: {call.remote_audio_params.ip_address}:{call.remote_audio_params.port}")
                logger.info(f"   • NAT Traversal: {'ENABLED' if call.public_ip else 'LOCAL ONLY'}")
                
                # Start test audio injection if test mode is enabled
                self._start_test_audio_injection_when_connected()
            else:
                logger.warning("⚠️ No remote audio params found, RTP bridge may not work.")
                
            return True
        else:
            logger.error(f"❌ Call failed to connect. Final state: {call.state.value}")
            return False

    def stop(self) -> None:
        """Stop the SIP client and cleanup."""
        logger.info("Stopping SIP client...")
        self.running = False
        
        if self.rtp_bridge:
            self.rtp_bridge.stop_bridge()
        
        if self.socket:
            self.socket.close()
            
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2)
        
        logger.info("SIP client stopped")

    def _send_request_and_wait(self, cseq_key: str, message: str, timeout: float = 5.0) -> Optional[SipResponse]:
        """Send a request and wait for its corresponding response."""
        event = threading.Event()
        self._response_events[cseq_key] = event
        
        self._send_message(message)
        
        event_was_set = event.wait(timeout)
        
        # Cleanup
        self._response_events.pop(cseq_key, None)
        
        if not event_was_set:
            logger.warning(f"Timeout waiting for response to '{cseq_key}'")
            return None
            
        return self._received_responses.pop(cseq_key, None)

    def _message_listener_loop(self) -> None:
        """Background thread for listening to SIP messages."""
        logger.info("👂 SIP message listener started")
        
        while self.running:
            try:
                self.socket.settimeout(1.0)  # Allow periodic checks
                data, addr = self.socket.recvfrom(4096)
                message = data.decode('utf-8')
                
                logger.debug(f"📨 Received from {addr}: {message[:200]}...")
                
                # Parse the message
                response = parse_sip_response(message)
                if response:
                    # Handle responses to our requests
                    cseq_key = response.headers.get('cseq', 'unknown')
                    logger.debug(f"📨 Response: {response.status_code} {response.status_text} for {cseq_key}")
                    
                    # Store the response for waiting threads
                    if cseq_key in self._response_events:
                        self._received_responses[cseq_key] = response
                        self._response_events[cseq_key].set()
                    
                    # Update call states
                    call_id = response.headers.get('call-id')
                    if call_id and call_id in self.active_calls:
                        call = self.active_calls[call_id]
                        self._handle_response_for_call(call, response)
                else:
                    # Check if it's a BYE request (call termination)
                    if message.startswith('BYE '):
                        logger.info("📞 Received BYE - call terminated by remote party")
                        self._handle_bye_request(message)
                    elif message.startswith('CANCEL '):
                        logger.info("📞 Received CANCEL - call cancelled by remote party")
                        self._handle_cancel_request(message)
                    else:
                        logger.debug(f"📨 Non-response message: {message[:50]}...")
                
            except socket.timeout:
                # Check for dead calls periodically
                self._check_call_states()
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error in message listener: {e}")
                break
        
        logger.info("👂 SIP message listener stopped")
    
    def _check_call_states(self) -> None:
        """Check for calls that should be considered ended."""
        current_time = time.time()
        dead_calls = []
        
        for call_id, call in self.active_calls.items():
            # Mark calls as ended if they've been in limbo too long
            if call.state == CallState.CONNECTED:
                # Check if call has been silent too long (no recent activity)
                if current_time - call.start_time > 300:  # 5 minutes max call
                    logger.warning(f"⏰ Call {call_id} exceeded maximum duration, marking as ended")
                    call.state = CallState.ENDED
                    dead_calls.append(call_id)
            elif call.state in [CallState.CALLING, CallState.RINGING]:
                # Timeout hanging calls
                if current_time - call.start_time > 60:  # 1 minute timeout
                    logger.warning(f"⏰ Call {call_id} timed out, marking as failed")
                    call.state = CallState.FAILED
                    dead_calls.append(call_id)
        
        # Clean up dead calls
        for call_id in dead_calls:
            del self.active_calls[call_id]
    
    def _handle_bye_request(self, message: str) -> None:
        """Handle incoming BYE request."""
        try:
            # Extract Call-ID from BYE message
            lines = message.split('\n')
            call_id = None
            for line in lines:
                if line.startswith('Call-ID:'):
                    call_id = line.split(':', 1)[1].strip()
                    break
            
            if call_id and call_id in self.active_calls:
                call = self.active_calls[call_id]
                call.state = CallState.ENDED
                call.end_time = time.time()
                logger.info(f"📞 Call {call_id} ended by remote party")
                
                # Send 200 OK response to BYE
                bye_response = f"""SIP/2.0 200 OK
Via: SIP/2.0/UDP {self.local_ip}:{self.local_port}
Call-ID: {call_id}
Content-Length: 0

"""
                self._send_message(bye_response)
                
        except Exception as e:
            logger.error(f"Error handling BYE request: {e}")
    
    def _handle_cancel_request(self, message: str) -> None:
        """Handle incoming CANCEL request."""
        try:
            # Extract Call-ID from CANCEL message
            lines = message.split('\n')
            call_id = None
            for line in lines:
                if line.startswith('Call-ID:'):
                    call_id = line.split(':', 1)[1].strip()
                    break
            
            if call_id and call_id in self.active_calls:
                call = self.active_calls[call_id]
                call.state = CallState.ENDED
                call.end_time = time.time()
                logger.info(f"📞 Call {call_id} cancelled by remote party")
                
        except Exception as e:
            logger.error(f"Error handling CANCEL request: {e}")

    def _dispatch_message(self, message: str, addr: tuple) -> None:
        """Parse and route incoming SIP messages."""
        # Only log full messages in debug mode
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"--- INCOMING SIP MESSAGE from {addr} ---\n{message}\n--------------------")
        
        first_line = message.split('\r\n')[0]
        
        # Log message type in production
        if not logger.isEnabledFor(logging.DEBUG):
            logger.info(f"Received SIP: {first_line.split()[0] if first_line else 'Unknown'} from {addr[0]}")
        
        if first_line.startswith('SIP/2.0'):
            # This is a response
            self._handle_sip_response(message, addr)
        else:
            # This is a request
            self._handle_sip_request(message, addr)

    def _handle_sip_response(self, message: str, addr: tuple) -> None:
        """Handle SIP response messages."""
        response = parse_sip_response(message)
        if not response:
            return
            
        cseq_header = response.headers.get("cseq", "")
        
        # Wake up the thread waiting for this response
        if cseq_header in self._response_events:
            self._received_responses[cseq_header] = response
            self._response_events[cseq_header].set()
        
        # Handle responses that also change call state (e.g., 200 OK to INVITE)
        call_id = response.headers.get("call-id")
        if call_id and call_id in self.active_calls:
            self._handle_response_for_call(self.active_calls[call_id], response)

    def _handle_sip_request(self, message: str, addr: tuple) -> None:
        """Handle SIP request messages."""
        response = parse_sip_response(message)  # Use the same parser for requests
        if not response: 
            return  # It will fail parsing the status line, but that's ok
        
        call_id = response.headers.get("call-id")
        call = self.active_calls.get(call_id)
        if not call: 
            return

        first_line = message.split('\r\n')[0]
        method = first_line.split()[0]
        if method == "BYE":
            self._handle_bye(call, response.headers)
        elif method == "CANCEL":
            self._handle_cancel(call, response.headers)

    def _handle_response_for_call(self, call: SipCall, response: SipResponse):
        """Update call state based on a SIP response."""
        if response.status_code == 180 or response.status_code == 183:
            logger.info(f"Phone is ringing ({response.status_code} {response.status_text})...")
            call.set_ringing()
        
        elif response.status_code == 200 and "INVITE" in response.headers.get("cseq", ""):
            if response.body:
                call.remote_audio_params = extract_audio_params_from_sip_response(response.body)
            call.answer()
            
        elif response.status_code >= 400:
            # IMPORTANT: Don't fail the call if it's an auth challenge,
            # as the main thread will handle re-sending with auth.
            if response.status_code not in [401, 407]:
                logger.error(f"Call failed with status: {response.status_code} {response.status_text}")
                call.fail(f"{response.status_code} {response.status_text}")
            else:
                logger.info(f"Received auth challenge ({response.status_code}), letting main thread handle it.")
    
    def _handle_bye(self, call: SipCall, headers: Dict[str, str]):
        """Handle an incoming BYE request."""
        logger.info(f"📞 Call terminated by remote party (BYE received) for call {call.call_id}")
        
        # Acknowledge the BYE with a 200 OK
        try:
            # Use the headers from the incoming BYE to construct the response
            to_header = headers.get("from")
            from_header = headers.get("to")
            
            # Create a basic response
            response = [
                "SIP/2.0 200 OK",
                headers.get("via", ""),
                f"To: {to_header}",
                f"From: {from_header}",
                f"Call-ID: {call.call_id}",
                f"CSeq: {headers.get('cseq')}",
                "Content-Length: 0",
                ""
            ]
            
            self._send_message("\r\n".join(response))
            logger.info("✅ Sent 200 OK for BYE")
            
        except Exception as e:
            logger.error(f"Failed to send 200 OK for BYE: {e}")
            
        # Finally, end the call internally
        call.hangup()
        
    def _handle_cancel(self, call: SipCall, headers: Dict[str, str]):
        """Handle an incoming CANCEL request."""
        logger.info(f"📞 Call cancelled by remote party (CANCEL received) for call {call.call_id}")
        call.hangup()
        # A full implementation would also send a 487 Request Terminated to the original INVITE
        # and a 200 OK to the CANCEL. For now, hanging up is sufficient.

    def _send_message(self, message: str) -> None:
        """Send a SIP message."""
        if not self.socket or not self.running:
            raise RuntimeError("SIP client not started or is stopped")
        
        # Only log full messages in debug mode
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"--- OUTGOING SIP MESSAGE to {self.settings.zoho.sip_server} ---\n{message}\n--------------------")
        else:
            # In production, just log the message type
            first_line = message.split('\n')[0] if message else ''
            logger.info(f"Sending SIP: {first_line}")
            
        self.socket.sendto(
            message.encode(),
            (self.settings.zoho.sip_server, self.settings.zoho.sip_port)
        )
        
    def _get_local_ip(self) -> str:
        """Get local IP address that can reach the SIP server."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((self.settings.zoho.sip_server, self.settings.zoho.sip_port))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1" 

    def terminate_call(self, call: SipCall) -> bool:
        """Properly terminate a call by sending BYE message."""
        try:
            if call.state in [CallState.CONNECTED, CallState.RINGING]:
                logger.info(f"📞 Terminating call {call.call_id}")
                
                # Create and send BYE message
                bye_msg = call.send_bye()
                if bye_msg:
                    self._send_message(bye_msg)
                    logger.info(f"📤 Sent BYE for call {call.call_id}")
                
                # Remove from active calls
                if call.call_id in self.active_calls:
                    del self.active_calls[call.call_id]
                
                # Stop RTP bridge if this was the last call
                if not self.active_calls and self.rtp_bridge:
                    self.rtp_bridge.stop_bridge()
                    self.rtp_bridge = None
                    logger.info("🔇 RTP bridge stopped - no active calls")
                
                return True
            else:
                logger.warning(f"⚠️  Cannot terminate call {call.call_id} in state {call.state.value}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error terminating call {call.call_id}: {e}")
            return False 

    def stop_client(self) -> None:
        """Stop the SIP client and clean up resources."""
        logger.info("Stopping SIP client...")
        
        # Stop RTP bridge first
        if self.rtp_bridge:
            self.rtp_bridge.stop_bridge()
            self.rtp_bridge = None
        
        # Close socket and stop listener
        self.running = False
        if self.socket:
            self.socket.close()
            
        logger.info("SIP client stopped")
    
    def enable_test_mode(self, test_audio_file: str = None) -> bool:
        """Enable test mode to inject known audio instead of AI audio."""
        if self.rtp_bridge:
            success = self.rtp_bridge.enable_test_mode(test_audio_file)
            if success:
                # Don't start injection here - wait for call to connect
                logger.info("🧪 Test mode enabled - will inject audio when call connects")
            return success
        return False
    
    def _start_test_audio_injection_when_connected(self) -> None:
        """Start test audio injection once the call is connected."""
        if (self.rtp_bridge and 
            hasattr(self.rtp_bridge, 'test_mode') and 
            self.rtp_bridge.test_mode):
            
            logger.info("🧪 Call connected - starting test audio injection")
            self.rtp_bridge.start_test_audio_injection()
        else:
            logger.warning("❌ Cannot start test audio - requirements not met") 
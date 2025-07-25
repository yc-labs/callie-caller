"""
Multi-tenant SIP Client for Yealink phone emulation.
Handles user-specific SIP registration, call management, and authentication with Zoho Voice.
"""

import socket
import time
import random
import logging
import asyncio
import threading
from typing import Optional, Callable, Dict, Any, List

from callie_caller.utils.network import get_public_ip
from callie_caller.config.firebase_service import UserConfiguration
from callie_caller.sip.auth import SipAuthenticator
from callie_caller.sip.call import SipCall, CallState
from callie_caller.sip.sdp import extract_audio_params_from_sip_response
from callie_caller.sip.rtp import RtpHandler
from callie_caller.sip.rtp_bridge import RtpBridge
from callie_caller.ai import AudioBridge
from .parser import SipResponse, parse_sip_response

logger = logging.getLogger(__name__)

class MultiTenantSipClient:
    """
    Multi-tenant SIP client for Yealink phone emulation.
    Handles registration, authentication, call management, and RTP audio for specific users.
    """
    
    def __init__(self, user_config: UserConfiguration, on_incoming_call: Optional[Callable[[SipCall], None]] = None):
        """
        Initialize multi-tenant SIP client.
        
        Args:
            user_config: User-specific configuration
            on_incoming_call: Callback for handling incoming calls
        """
        self.user_config = user_config
        self.authenticator = MultiTenantSipAuthenticator(user_config)
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
    
    @property
    def user_id(self) -> str:
        """Get the user ID for this client."""
        return self.user_config.user_id
    
    @property
    def display_name(self) -> str:
        """Get the display name for this client."""
        return self.user_config.sip.display_name
        
    async def start_audio_conversation(self, call: SipCall, initial_message: Optional[str] = None) -> None:
        """
        Start audio conversation with AI for this user.
        
        Args:
            call: The SIP call to handle
            initial_message: Optional initial message for the AI
        """
        try:
            if not self.rtp_bridge:
                logger.error("RTP bridge not available for audio conversation")
                return
            
            # Initialize AI audio bridge with user-specific greeting
            greeting = initial_message or self.user_config.calls.default_greeting
            self.audio_bridge = AudioBridge(
                sample_rate=8000,
                channels=1,
                chunk_size=320  # 20ms at 8kHz
            )
            
            # Set up RTP bridge for audio capture/playback
            self.rtp_bridge.set_audio_callback(self.audio_bridge.on_audio_received)
            
            # Start the conversation
            self._conversation_task = asyncio.create_task(
                self.audio_bridge.start_conversation(greeting)
            )
            
            logger.info(f"🎵 Live AI conversation started for user {self.user_id}!")
            
        except Exception as e:
            logger.error(f"Failed to start audio conversation for user {self.user_id}: {e}")
    
    async def stop_audio_conversation(self) -> None:
        """Stop the active audio conversation."""
        if self.audio_bridge:
            await self.audio_bridge.stop_conversation()
            
        if self._conversation_task and not self._conversation_task.done():
            self._conversation_task.cancel()
            
        logger.info(f"🔇 Audio conversation stopped for user {self.user_id}")

    def start(self, request_headers: Optional[Dict[str, str]] = None) -> bool:
        """Start the SIP client and its message listener."""
        try:
            # Discover public IP for NAT traversal
            self.public_ip = get_public_ip(request_headers)
            
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Get local IP and bind to dynamic port
            self.local_ip = self._get_local_ip()
            self.socket.bind((self.local_ip, 0))
            self.local_port = self.socket.getsockname()[1]
            
            logger.info(f"SIP client started for user {self.user_id} on {self.local_ip}:{self.local_port} (Public: {self.public_ip})")
            logger.info(f"Emulating: {self.user_config.device.user_agent}")
            
            # Start the background listener thread
            self.running = True
            self._listener_thread = threading.Thread(target=self._message_listener_loop, daemon=True)
            self._listener_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start SIP client for user {self.user_id}: {e}")
            return False
    
    def register(self) -> bool:
        """Register with SIP server with authentication."""
        logger.info(f"Registering user {self.user_id} ({self.user_config.sip.sip_username}) with {self.user_config.sip.sip_server}")
        
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
                logger.error(f"No response to initial REGISTER request for user {self.user_id}")
                return False
                
            if response.status_code not in [401, 407]:
                logger.error(f"Unexpected response to REGISTER for user {self.user_id}: {response.status_code} {response.status_text}")
                return False

            # We received a challenge, now create and send an authenticated REGISTER
            logger.info(f"Authentication required for user {self.user_id}, sending authenticated REGISTER...")
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
                self.registered = True
                logger.info(f"✅ User {self.user_id} successfully registered with Zoho Voice!")
                return True
            else:
                error_msg = f"Registration failed for user {self.user_id}"
                if final_response:
                    error_msg += f": {final_response.status_code} {final_response.status_text}"
                logger.error(error_msg)
                return False
                
        except Exception as e:
            logger.error(f"Registration error for user {self.user_id}: {e}")
            return False
    
    def make_call(self, target_number: str, ai_message: Optional[str] = None) -> bool:
        """
        Make an outbound call.
        
        Args:
            target_number: Number to call
            ai_message: Optional message for AI to deliver
            
        Returns:
            True if call was initiated successfully
        """
        if not self.registered:
            logger.error(f"Cannot make call for user {self.user_id}: not registered")
            return False
        
        # Create new call
        call_id = f"call-{random.randint(100000, 999999)}-{int(time.time())}"
        call = UserSipCall(
            call_id=call_id,
            local_ip=self.local_ip,
            public_ip=self.public_ip,
            local_port=self.local_port,
            user_config=self.user_config,
            authenticator=self.authenticator,
            target_number=target_number,
            ai_message=ai_message
        )
        
        self.active_calls[call_id] = call
        
        try:
            # Step 1: Start RTP bridge BEFORE sending INVITE
            logger.info(f"🌉 Starting RTP bridge for user {self.user_id} media relay...")
            self.rtp_bridge = RtpBridge(self.local_ip)
            bridge_port = self.rtp_bridge.start_bridge()
            if not bridge_port:
                logger.error(f"❌ Failed to start RTP bridge for user {self.user_id}")
                return False
            logger.info(f"🌉 RTP bridge listening on {self.local_ip}:{bridge_port} for user {self.user_id}")
            
            # Step 2: Configure call to use bridge port in SDP
            call.rtp_port = bridge_port
            
            # Step 3: Send initial INVITE
            invite_msg = call.create_invite_message()
            response = self._send_request_and_wait(f"{call.cseq} INVITE", invite_msg)
            
            # Step 4: Handle authentication if required
            if response and response.status_code in [401, 407]:
                logger.info(f"Authentication required for call from user {self.user_id}, sending authenticated INVITE...")
                call.cseq += 1
                auth_header = response.headers.get('www-authenticate') or response.headers.get('proxy-authenticate')
                
                auth_invite = call.create_authenticated_invite_message(
                    auth_header=auth_header,
                    is_proxy_auth=(response.status_code == 407)
                )
                # Don't wait here, the response will be handled by the main listener
                self._send_message(auth_invite)

            elif response and response.status_code >= 400:
                logger.error(f"Call failed for user {self.user_id} with initial response: {response.status_code} {response.status_text}")
                call.fail(f"Initial error: {response.status_code}")
                return False
                
            # Step 5: Wait for the call to be connected
            return self._wait_for_call_to_connect(call)
            
        except Exception as e:
            logger.error(f"Error making call for user {self.user_id}: {e}")
            call.fail(f"Call error: {e}")
            return False

    def _wait_for_call_to_connect(self, call: SipCall) -> bool:
        """Wait for call to reach connected state."""
        timeout = self.user_config.calls.answer_timeout
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if call.state == CallState.CONNECTED:
                break
            elif call.state == CallState.FAILED:
                logger.error(f"Call failed for user {self.user_id} during connection wait")
                return False
            time.sleep(0.1)

        if call.state == CallState.CONNECTED:
            logger.info(f"🎉 Call Answered and Connected for user {self.user_id}!")
            
            # Send ACK for the 200 OK
            ack_msg = call.create_ack_message()
            self._send_message(ack_msg)
            
            # Configure RTP bridge with remote endpoint from 200 OK's SDP
            if call.remote_audio_params and self.rtp_bridge:
                logger.info(f"🎤 Remote audio endpoint for user {self.user_id}: {call.remote_audio_params.ip_address}:{call.remote_audio_params.port}")
                self.rtp_bridge.set_remote_endpoint(call.remote_audio_params)
                bridge_port = self.rtp_bridge.get_bridge_port()
                logger.info(f"🌉 RTP bridge configured for user {self.user_id} media path: Phone ↔️ Bridge ({bridge_port}) ↔️ Remote")
                
                # Start test audio injection if test mode is enabled
                self._start_test_audio_injection_when_connected()
            else:
                logger.warning(f"⚠️ No remote audio params found for user {self.user_id}, RTP bridge may not work.")
                
            return True
        else:
            logger.error(f"❌ Call failed to connect for user {self.user_id}. Final state: {call.state.value}")
            return False

    def _message_listener_loop(self) -> None:
        """Background thread to listen for SIP messages."""
        logger.info(f"🎧 SIP message listener started for user {self.user_id}")
        
        while self.running:
            try:
                self.socket.settimeout(1.0)
                data, addr = self.socket.recvfrom(4096)
                message = data.decode('utf-8')
                
                logger.debug(f"--- INCOMING SIP MESSAGE for user {self.user_id} from {addr} ---\n{message}\n--------------------")
                
                # Parse SIP response
                response = parse_sip_response(message)
                if not response:
                    logger.warning(f"Failed to parse SIP message for user {self.user_id}")
                    continue
                
                # Handle different response types
                self._handle_sip_response(response)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:  # Only log if we're still supposed to be running
                    logger.error(f"Error in message listener for user {self.user_id}: {e}")
        
        logger.info(f"🎧 SIP message listener stopped for user {self.user_id}")

    def _handle_sip_response(self, response: SipResponse) -> None:
        """Handle incoming SIP response."""
        try:
            # Check if this is a response to a request we're waiting for
            cseq_header = response.headers.get('cseq', '')
            if cseq_header in self._response_events:
                self._received_responses[cseq_header] = response
                self._response_events[cseq_header].set()
                return
            
            # Handle call-specific responses
            call_id = response.headers.get('call-id')
            if call_id in self.active_calls:
                call = self.active_calls[call_id]
                
                if response.status_code == 200 and 'INVITE' in cseq_header:
                    # Call answered
                    call.state = CallState.CONNECTED
                    
                    # Extract audio parameters from SDP
                    call.remote_audio_params = extract_audio_params_from_sip_response(response)
                    logger.info(f"📞 Call answered for user {self.user_id}! Audio: {call.remote_audio_params}")
                    
                elif response.status_code >= 400:
                    # Call failed
                    call.state = CallState.FAILED
                    logger.error(f"📞 Call failed for user {self.user_id}: {response.status_code} {response.status_text}")
                    
                elif response.status_code == 180 or response.status_code == 183:
                    # Ringing
                    call.state = CallState.RINGING
                    logger.info(f"📞 Call ringing for user {self.user_id}...")
            
        except Exception as e:
            logger.error(f"Error handling SIP response for user {self.user_id}: {e}")

    def _send_request_and_wait(self, cseq: str, message: str, timeout: float = 5.0) -> Optional[SipResponse]:
        """Send SIP request and wait for response."""
        try:
            # Set up event for this request
            event = threading.Event()
            self._response_events[cseq] = event
            
            # Send the message
            self._send_message(message)
            
            # Wait for response
            if event.wait(timeout):
                response = self._received_responses.get(cseq)
                # Clean up
                del self._response_events[cseq]
                if cseq in self._received_responses:
                    del self._received_responses[cseq]
                return response
            else:
                logger.warning(f"Timeout waiting for response to {cseq} for user {self.user_id}")
                # Clean up
                if cseq in self._response_events:
                    del self._response_events[cseq]
                return None
                
        except Exception as e:
            logger.error(f"Error sending request for user {self.user_id}: {e}")
            return None

    def _send_message(self, message: str) -> None:
        """Send SIP message to server."""
        if not self.socket or not self.running:
            raise RuntimeError(f"SIP client not started or is stopped for user {self.user_id}")
        
        logger.debug(f"--- OUTGOING SIP MESSAGE for user {self.user_id} to {self.user_config.sip.sip_server} ---\n{message}\n--------------------")
        self.socket.sendto(
            message.encode(),
            (self.user_config.sip.sip_server, self.user_config.sip.sip_port)
        )
        
    def _get_local_ip(self) -> str:
        """Get local IP address that can reach the SIP server."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((self.user_config.sip.sip_server, self.user_config.sip.sip_port))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def _start_test_audio_injection_when_connected(self) -> None:
        """Start test audio injection if enabled."""
        # This would be implemented similar to the original SipClient
        pass

    def stop(self) -> None:
        """Stop the SIP client."""
        logger.info(f"Stopping SIP client for user {self.user_id}...")
        self.running = False
        
        # Stop RTP bridge
        if self.rtp_bridge:
            self.rtp_bridge.stop()
        
        # Close socket
        if self.socket:
            self.socket.close()
        
        # Wait for listener thread to finish
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2.0)
        
        logger.info(f"✅ SIP client stopped for user {self.user_id}")


class MultiTenantSipAuthenticator:
    """
    Handles SIP Digest Authentication for Zoho Voice with user-specific credentials.
    """
    
    def __init__(self, user_config: UserConfiguration):
        self.user_config = user_config
        
    def create_register_request(self, local_ip: str, public_ip: Optional[str], local_port: int, call_id: str, from_tag: str, cseq: int, auth_header: Optional[str] = None) -> str:
        """
        Create a full REGISTER request, either initial or authenticated.
        """
        branch = f"z9hG4bK-{random.randint(100000, 999999)}"
        
        # Use the public IP in the 'received' part of the Via header if available.
        via_header = f"Via: SIP/2.0/UDP {local_ip}:{local_port};branch={branch};rport"
        if public_ip:
            via_header += f";received={public_ip}"

        contact_ip = public_ip or local_ip
        
        headers = [
            f"REGISTER sip:{self.user_config.sip.sip_server} SIP/2.0",
            via_header,
            "Max-Forwards: 70",
            f"Contact: <sip:{self.user_config.sip.sip_username}@{contact_ip}:{local_port}>",
            f"To: <sip:{self.user_config.sip.sip_username}@{self.user_config.sip.sip_server}>",
            f"From: <sip:{self.user_config.sip.sip_username}@{self.user_config.sip.sip_server}>;tag={from_tag}",
            f"Call-ID: {call_id}",
            f"CSeq: {cseq} REGISTER",
            "Expires: 3600",
            f"User-Agent: {self.user_config.device.user_agent}"
        ]
        
        # Add authentication header if provided
        if auth_header:
            auth_response = self.calculate_auth_response(
                method="REGISTER",
                uri=f"sip:{self.user_config.sip.sip_server}",
                auth_header=auth_header
            )
            auth_header_name = "Proxy-Authorization" if "proxy-authenticate" in auth_header.lower() else "Authorization"
            headers.append(f"{auth_header_name}: {auth_response}")
        
        headers.append("Content-Length: 0")
        headers.append("")  # Empty line before body
        
        return "\r\n".join(headers)
    
    def calculate_auth_response(self, method: str, uri: str, auth_header: str) -> str:
        """Calculate digest authentication response."""
        # This would implement the same digest auth logic as the original SipAuthenticator
        # but using self.user_config.sip.sip_username and self.user_config.sip.sip_password
        from callie_caller.sip.auth import SipAuthenticator
        
        # Create a temporary authenticator with user-specific settings
        from callie_caller.config.settings import ZohoSettings, DeviceSettings, AISettings, ServerSettings, CallSettings, Settings
        
        # Convert user config to settings format for compatibility
        temp_settings = Settings(
            zoho=ZohoSettings(
                sip_server=self.user_config.sip.sip_server,
                sip_username=self.user_config.sip.sip_username,
                sip_password=self.user_config.sip.sip_password,
                sip_port=self.user_config.sip.sip_port,
                account_label=self.user_config.sip.account_label
            ),
            device=DeviceSettings(
                mac_address=self.user_config.device.mac_address,
                model=self.user_config.device.model,
                firmware=self.user_config.device.firmware,
                custom_user_agent=self.user_config.device.custom_user_agent
            ),
            ai=AISettings(api_key="dummy"),  # Not used for auth
            server=ServerSettings(),  # Not used for auth
            calls=CallSettings()  # Not used for auth
        )
        
        temp_auth = SipAuthenticator(temp_settings)
        return temp_auth.calculate_auth_response(method, uri, auth_header)


class UserSipCall(SipCall):
    """
    Represents a single SIP call for a specific user.
    Extends the base SipCall with user-specific configuration.
    """
    
    def __init__(self, call_id: str, local_ip: str, public_ip: Optional[str], local_port: int, 
                 user_config: UserConfiguration, authenticator: MultiTenantSipAuthenticator, 
                 target_number: str, ai_message: Optional[str] = None):
        """Initialize user-specific SIP call."""
        self.user_config = user_config
        
        # Call the parent constructor but we need to adapt the interface
        # Since the parent expects Settings, we'll override the relevant methods
        super().__init__(
            call_id=call_id,
            local_ip=local_ip,
            public_ip=public_ip,
            local_port=local_port,
            settings=None,  # We'll override methods that use this
            authenticator=authenticator,
            target_number=target_number,
            ai_message=ai_message
        )
    
    @property
    def invite_uri(self) -> str:
        """Get the INVITE URI for this call."""
        return f"sip:{self.target_number}@{self.user_config.sip.sip_server}"
        
    @property
    def from_header(self) -> str:
        """Get the From header for this call."""
        display_name = self.user_config.sip.account_label or self.user_config.sip.display_name
        return f'"{display_name}" <sip:{self.user_config.sip.sip_username}@{self.user_config.sip.sip_server}>;tag={self.tag}'
        
    @property
    def to_header(self) -> str:
        """Get the To header for this call."""
        return f"<sip:{self.target_number}@{self.user_config.sip.sip_server}>"
        
    @property
    def contact_header(self) -> str:
        """Get the Contact header for this call."""
        contact_ip = self.public_ip or self.local_ip
        return f"<sip:{self.user_config.sip.sip_username}@{contact_ip}:{self.local_port}>"

    def create_invite_message(self) -> str:
        """Create initial SIP INVITE message."""
        sdp_content = self.create_sdp_content()
        
        via_header = f"Via: SIP/2.0/UDP {self.local_ip}:{self.local_port};branch={self.branch};rport"
        if self.public_ip:
            via_header += f";received={self.public_ip}"
        
        full_invite = f"""INVITE {self.invite_uri} SIP/2.0
{via_header}
Max-Forwards: 70
Contact: {self.contact_header}
To: {self.to_header}
From: {self.from_header}
Call-ID: {self.call_id}
CSeq: {self.cseq} INVITE
Allow: INVITE,ACK,OPTIONS,CANCEL,BYE,SUBSCRIBE,NOTIFY,INFO,REFER,UPDATE
Content-Type: application/sdp
Accept: application/sdp
User-Agent: {self.user_config.device.user_agent}
Supported: replaces
Content-Length: {len(sdp_content)}

{sdp_content}"""
        
        logger.info(f"--- CONSTRUCTED SIP INVITE for user {self.user_config.user_id} ---\n{full_invite}\n--------------------")
        return full_invite 
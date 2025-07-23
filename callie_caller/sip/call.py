"""
SIP Call management for individual voice calls.
Handles call state, SIP message generation, and call lifecycle.
"""

import time
import random
import logging
from enum import Enum
from typing import Optional, Dict
from dataclasses import dataclass, field

from callie_caller.config.settings import Settings
from .sdp import AudioParams
from .auth import SipAuthenticator


logger = logging.getLogger(__name__)

class CallState(Enum):
    """SIP call states."""
    IDLE = "idle"
    CALLING = "calling" 
    RINGING = "ringing"
    CONNECTED = "connected"
    ENDED = "ended"
    FAILED = "failed"

@dataclass
class SipCall:
    """Represents a single SIP call."""
    call_id: str
    local_ip: str
    public_ip: Optional[str]
    local_port: int
    settings: Settings
    authenticator: SipAuthenticator
    target_number: str
    ai_message: Optional[str] = None
    state: CallState = CallState.IDLE
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    tag: Optional[str] = None
    branch: Optional[str] = None
    rtp_port: Optional[int] = None
    cseq: int = 1
    headers: Dict[str, str] = field(default_factory=dict)
    remote_audio_params: Optional[AudioParams] = None
    
    def __post_init__(self):
        """Initialize call after creation."""
        self.tag = f"tag-{random.randint(1000, 9999)}"
        self.branch = f"z9hG4bK-{random.randint(100000, 999999)}"
        self.start_time = time.time()
        self.state = CallState.CALLING
        
    @property
    def duration(self) -> float:
        """Get call duration in seconds."""
        if self.start_time:
            end = self.end_time or time.time()
            return end - self.start_time
        return 0.0
        
    @property
    def invite_uri(self) -> str:
        """Get the INVITE URI for this call."""
        return f"sip:{self.target_number}@{self.settings.zoho.sip_server}"
        
    @property
    def from_header(self) -> str:
        """Get the From header for this call."""
        display_name = self.settings.zoho.account_label or "AI Agent"
        return f'"{display_name}" <sip:{self.settings.zoho.sip_username}@{self.settings.zoho.sip_server}>;tag={self.tag}'
        
    @property
    def to_header(self) -> str:
        """Get the To header for this call."""
        return f"<sip:{self.target_number}@{self.settings.zoho.sip_server}>"
        
    @property
    def contact_header(self) -> str:
        """Get the Contact header for this call."""
        contact_ip = self.public_ip or self.local_ip
        return f"<sip:{self.settings.zoho.sip_username}@{contact_ip}:{self.local_port}>"
        
    def create_sdp_content(self) -> str:
        """
        Create SDP (Session Description Protocol) content for audio.
        Crucially, this uses the PUBLIC IP so the remote party knows where to send audio.
        """
        audio_port = self.rtp_port if self.rtp_port else (self.local_port + 1000)
        session_id = int(time.time())
        sdp_ip = self.public_ip or self.local_ip
        
        sdp = f"""v=0
o=- {session_id} {session_id} IN IP4 {sdp_ip}
s=Yealink SIP Session
c=IN IP4 {sdp_ip}
t=0 0
m=audio {audio_port} RTP/AVP 18 0 8 101
a=rtpmap:18 G729/8000
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=rtpmap:101 telephone-event/8000
a=fmtp:101 0-15
a=sendrecv
"""
        return sdp
        
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
User-Agent: {self.settings.device.user_agent}
Supported: timer,replaces
Content-Length: {len(sdp_content)}

{sdp_content}"""
        
        logger.info(f"--- CONSTRUCTED SIP INVITE ---\n{full_invite}\n--------------------")
        return full_invite
        
    def create_authenticated_invite_message(self, auth_header: str, is_proxy_auth: bool = False) -> str:
        """
        Create authenticated SIP INVITE message.
        """
        sdp_content = self.create_sdp_content()
        auth_header_name = "Proxy-Authorization" if is_proxy_auth else "Authorization"
        
        auth_response = self.authenticator.calculate_auth_response(
            method="INVITE",
            uri=self.invite_uri,
            auth_header=auth_header
        )

        via_header = f"Via: SIP/2.0/UDP {self.local_ip}:{self.local_port};branch={self.branch}-auth;rport"
        if self.public_ip:
            via_header += f";received={self.public_ip}"

        return f"""INVITE {self.invite_uri} SIP/2.0
{via_header}
Max-Forwards: 70
Contact: {self.contact_header}
To: {self.to_header}
From: {self.from_header}
Call-ID: {self.call_id}
CSeq: {self.cseq} INVITE
{auth_header_name}: {auth_response}
Allow: INVITE,ACK,OPTIONS,CANCEL,BYE,SUBSCRIBE,NOTIFY,INFO,REFER,UPDATE
Content-Type: application/sdp
Accept: application/sdp
User-Agent: {self.settings.device.user_agent}
Supported: timer,replaces
Content-Length: {len(sdp_content)}

{sdp_content}"""
        
    def create_ack_message(self) -> str:
        """Create ACK message to complete call setup."""
        # CSeq for ACK should match the INVITE it's acknowledging
        return f"""ACK {self.invite_uri} SIP/2.0
Via: SIP/2.0/UDP {self.local_ip}:{self.local_port};branch={self.branch}-ack
Max-Forwards: 70
To: {self.to_header}
From: {self.from_header}
Call-ID: {self.call_id}
CSeq: {self.cseq} ACK
User-Agent: {self.settings.device.user_agent}
Content-Length: 0

"""
        
    def create_bye_message(self) -> str:
        """Create BYE message to end the call."""
        self.cseq += 1
        return f"""BYE {self.invite_uri} SIP/2.0
Via: SIP/2.0/UDP {self.local_ip}:{self.local_port};branch={self.branch}-bye
Max-Forwards: 70
To: {self.to_header}
From: {self.from_header}
Call-ID: {self.call_id}
CSeq: {self.cseq} BYE
User-Agent: {self.settings.device.user_agent}
Content-Length: 0

"""
        
    def hangup(self) -> None:
        """End the call and update state."""
        if self.state not in [CallState.ENDED, CallState.FAILED]:
            logger.info(f"📞 Hanging up call {self.call_id}")
            self.state = CallState.ENDED
            self.end_time = time.time()
            logger.info(f"Call {self.call_id} ended after {self.duration:.1f} seconds")
            
    def answer(self) -> None:
        """Mark call as answered/connected."""
        if self.state in [CallState.CALLING, CallState.RINGING]:
            self.state = CallState.CONNECTED
            logger.info(f"Call {self.call_id} answered")
            
    def fail(self, reason: str = "Unknown") -> None:
        """Mark call as failed."""
        if self.state != CallState.FAILED:
            self.state = CallState.FAILED
            self.end_time = time.time()
            logger.error(f"Call {self.call_id} failed: {reason}")
        
    def set_ringing(self) -> None:
        """Mark call as ringing."""
        if self.state == CallState.CALLING:
            self.state = CallState.RINGING
            logger.info(f"Call {self.call_id} is ringing")
            
    def get_ai_message(self) -> str:
        """Get the AI message for this call."""
        return self.ai_message or self.settings.calls.default_greeting 
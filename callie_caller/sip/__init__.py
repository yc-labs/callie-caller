"""
This package handles the Session Initiation Protocol (SIP) communication
for emulating a Yealink desk phone and connecting to Zoho Voice.
"""

from .client import SipClient
from .call import SipCall, CallState
from .sdp import SdpParser, AudioParams, extract_audio_params_from_sip_response
from .rtp import RtpHandler, RtpPacket
from .rtp_bridge import RtpBridge
from .parser import SipResponse, parse_sip_response

__all__ = [
    "SipClient",
    "SipCall",
    "CallState",
    "SdpParser",
    "AudioParams",
    "extract_audio_params_from_sip_response",
    "RtpHandler",
    "RtpPacket",
    "RtpBridge",
    "SipResponse",
    "parse_sip_response"
] 
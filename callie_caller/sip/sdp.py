"""
SDP (Session Description Protocol) parser for extracting audio parameters.
Handles parsing of SDP content from SIP responses to get RTP connection details.
"""

import logging
import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class AudioParams:
    """Audio parameters extracted from SDP."""
    ip_address: str
    port: int
    codecs: List[Dict[str, str]]  # [{"payload": "0", "codec": "PCMU", "rate": "8000"}]
    rtcp_port: Optional[int] = None

@dataclass 
class SdpSession:
    """Complete SDP session information."""
    session_name: str
    audio: Optional[AudioParams] = None
    video: Optional[AudioParams] = None

class SdpParser:
    """Parser for SDP content in SIP messages."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_sdp(self, sdp_content: str) -> Optional[SdpSession]:
        """
        Parse SDP content and extract session information.
        
        Args:
            sdp_content: Raw SDP content from SIP message body
            
        Returns:
            SdpSession object with parsed information or None if invalid
        """
        if not sdp_content or not sdp_content.strip():
            self.logger.warning("Empty SDP content provided")
            return None
            
        try:
            lines = sdp_content.strip().split('\n')
            session = SdpSession(session_name="")
            
            # Current connection info (applies to subsequent media)
            current_ip = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Parse line type=value format
                if '=' not in line:
                    continue
                    
                line_type = line[0]
                content = line[2:]  # Skip "x="
                
                if line_type == 's':  # Session name
                    session.session_name = content
                    
                elif line_type == 'c':  # Connection information
                    # c=IN IP4 192.168.1.100
                    current_ip = self._parse_connection_line(content)
                    
                elif line_type == 'm':  # Media description
                    # m=audio 12345 RTP/AVP 0 8 18 101
                    media_type, port, protocol, codecs = self._parse_media_line(content)
                    
                    if media_type == 'audio':
                        audio_params = AudioParams(
                            ip_address=current_ip or "0.0.0.0",
                            port=port,
                            codecs=[]
                        )
                        
                        # Parse codec payload types
                        for codec_payload in codecs:
                            audio_params.codecs.append({
                                "payload": codec_payload,
                                "codec": "unknown",
                                "rate": "8000"
                            })
                            
                        session.audio = audio_params
                        
                elif line_type == 'a':  # Attributes
                    # a=rtpmap:0 PCMU/8000
                    # a=rtpmap:8 PCMA/8000
                    # a=rtcp:12346
                    self._parse_attribute_line(content, session)
            
            self.logger.info(f"Parsed SDP session: {session.session_name}")
            if session.audio:
                self.logger.info(f"Audio: {session.audio.ip_address}:{session.audio.port}")
                self.logger.info(f"Codecs: {len(session.audio.codecs)} available")
                
            return session
            
        except Exception as e:
            self.logger.error(f"Error parsing SDP: {e}")
            return None
    
    def _parse_connection_line(self, content: str) -> Optional[str]:
        """Parse connection line: IN IP4 192.168.1.100"""
        try:
            parts = content.split()
            if len(parts) >= 3 and parts[0] == 'IN' and parts[1] == 'IP4':
                ip_address = parts[2]
                self.logger.debug(f"Parsed connection IP: {ip_address}")
                return ip_address
        except Exception as e:
            self.logger.error(f"Error parsing connection line '{content}': {e}")
        return None
    
    def _parse_media_line(self, content: str) -> Tuple[str, int, str, List[str]]:
        """Parse media line: audio 12345 RTP/AVP 0 8 18 101"""
        try:
            parts = content.split()
            media_type = parts[0]  # audio, video
            port = int(parts[1])
            protocol = parts[2]    # RTP/AVP
            codec_payloads = parts[3:]  # [0, 8, 18, 101]
            
            self.logger.debug(f"Parsed media: {media_type} port {port} codecs {codec_payloads}")
            return media_type, port, protocol, codec_payloads
            
        except Exception as e:
            self.logger.error(f"Error parsing media line '{content}': {e}")
            return "", 0, "", []
    
    def _parse_attribute_line(self, content: str, session: SdpSession) -> None:
        """Parse attribute lines like rtpmap and rtcp."""
        try:
            if content.startswith('rtpmap:'):
                # rtpmap:0 PCMU/8000
                # rtpmap:8 PCMA/8000  
                # rtpmap:18 G729/8000
                match = re.match(r'rtpmap:(\d+)\s+([^/]+)/(\d+)', content)
                if match and session.audio:
                    payload_type = match.group(1)
                    codec_name = match.group(2)
                    sample_rate = match.group(3)
                    
                    # Update the codec info
                    for codec in session.audio.codecs:
                        if codec["payload"] == payload_type:
                            codec["codec"] = codec_name
                            codec["rate"] = sample_rate
                            break
                            
                    self.logger.debug(f"Mapped codec: payload {payload_type} = {codec_name}/{sample_rate}")
                    
            elif content.startswith('rtcp:'):
                # rtcp:12346
                match = re.match(r'rtcp:(\d+)', content)
                if match and session.audio:
                    session.audio.rtcp_port = int(match.group(1))
                    self.logger.debug(f"RTCP port: {session.audio.rtcp_port}")
                    
        except Exception as e:
            self.logger.error(f"Error parsing attribute '{content}': {e}")

def extract_audio_params_from_sip_response(sip_response_body: str) -> Optional[AudioParams]:
    """
    Convenience function to extract audio parameters from SIP response body.
    
    Args:
        sip_response_body: Body content of SIP 200 OK response
        
    Returns:
        AudioParams object or None
    """
    parser = SdpParser()
    session = parser.parse_sdp(sip_response_body)
    return session.audio if session else None 
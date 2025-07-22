"""
SIP Authentication for digest authentication with Zoho Voice.
Handles MD5 digest calculation and authentication header parsing.
"""

import hashlib
import random
import logging
from typing import Optional, Dict

from callie_caller.config.settings import Settings

logger = logging.getLogger(__name__)

class SipAuthenticator:
    """
    Handles SIP Digest Authentication for Zoho Voice.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        
    def create_register_request(self, local_ip: str, public_ip: Optional[str], local_port: int, call_id: str, from_tag: str, cseq: int, auth_header: Optional[str] = None) -> str:
        """
        Create a full REGISTER request, either initial or authenticated.
        """
        branch = f"z9hG4bK-{random.randint(100000, 999999)}"
        
        # Use the public IP in the 'received' part of the Via header if available.
        # The 'rport' parameter asks the server to respond to the port it received the request from.
        via_header = f"Via: SIP/2.0/UDP {local_ip}:{local_port};branch={branch};rport"
        if public_ip:
            via_header += f";received={public_ip}"

        contact_ip = public_ip or local_ip
        
        headers = [
            f"REGISTER sip:{self.settings.zoho.sip_server} SIP/2.0",
            via_header,
            "Max-Forwards: 70",
            f"Contact: <sip:{self.settings.zoho.sip_username}@{contact_ip}:{local_port}>",
            f"To: <sip:{self.settings.zoho.sip_username}@{self.settings.zoho.sip_server}>",
            f"From: <sip:{self.settings.zoho.sip_username}@{self.settings.zoho.sip_server}>;tag={from_tag}",
            f"Call-ID: {call_id}",
            f"CSeq: {cseq} REGISTER",
            "Expires: 3600",
            f"User-Agent: {self.settings.device.user_agent}"
        ]

        if auth_header:
            auth_response = self.calculate_auth_response(
                method="REGISTER",
                uri=f"sip:{self.settings.zoho.sip_server}",
                auth_header=auth_header
            )
            auth_header_name = "Proxy-Authorization" if "proxy-authenticate" in auth_header.lower() else "Authorization"
            headers.append(f"{auth_header_name}: {auth_response}")
            
        headers.append("Content-Length: 0")
        
        return "\r\n".join(headers) + "\r\n\r\n"

    def calculate_auth_response(self, method: str, uri: str, auth_header: str) -> str:
        """
        Calculate the Digest authentication response.
        """
        params = self._parse_auth_header(auth_header)
        realm = params.get("realm")
        nonce = params.get("nonce")
        
        if not realm or not nonce:
            raise ValueError("Realm or nonce not found in auth header")
            
        ha1 = self._calculate_ha1(realm)
        ha2 = self._calculate_ha2(method, uri)
        response = self._calculate_response(ha1, nonce, ha2)
        
        auth_parts = {
            "username": f'"{self.settings.zoho.sip_username}"',
            "realm": f'"{realm}"',
            "nonce": f'"{nonce}"',
            "uri": f'"{uri}"',
            "response": f'"{response}"',
            "algorithm": "MD5"
        }
        
        return "Digest " + ", ".join(f'{k}={v}' for k, v in auth_parts.items())

    def _parse_auth_header(self, header: str) -> Dict[str, str]:
        """Parse the WWW-Authenticate or Proxy-Authenticate header."""
        # Remove "Digest " prefix
        if header.strip().lower().startswith("digest "):
            header = header.strip()[7:]
            
        parts = [p.strip() for p in header.split(',')]
        return {key: value.strip('"') for key, value in (p.split('=', 1) for p in parts)}
        
    def _calculate_ha1(self, realm: str) -> str:
        """Calculate HA1 for Digest authentication."""
        return hashlib.md5(f"{self.settings.zoho.sip_username}:{realm}:{self.settings.zoho.sip_password}".encode()).hexdigest()
        
    def _calculate_ha2(self, method: str, uri: str) -> str:
        """Calculate HA2 for Digest authentication."""
        return hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        
    def _calculate_response(self, ha1: str, nonce: str, ha2: str) -> str:
        """Calculate the final response for Digest authentication."""
        return hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest() 
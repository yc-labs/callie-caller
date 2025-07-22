import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# A simple dataclass-like structure would be better, but avoiding new deps for now.
class SipResponse:
    """A simple container for parsed SIP responses."""
    def __init__(self, status_code: int, status_text: str, headers: Dict[str, str], body: str, raw: str):
        self.status_code = status_code
        self.status_text = status_text
        self.headers = headers
        self.body = body
        self.raw = raw

def parse_sip_response(response_str: str) -> Optional[SipResponse]:
    """
    Parse a raw SIP message string (which can be a response or a request)
    into a SipResponse object.
    """
    try:
        lines = response_str.splitlines()
        if not lines:
            return None
            
        # Parse first line (status line for responses, request line for requests)
        first_line = lines[0]
        parts = first_line.split(' ', 2)
        
        status_code = 0
        status_text = ""

        # Check if it's a response (e.g., "SIP/2.0 200 OK")
        if first_line.startswith("SIP/2.0"):
            if len(parts) >= 2:
                status_code = int(parts[1])
                status_text = parts[2] if len(parts) > 2 else ""
        # It's a request (e.g., "BYE sip:...")
        else:
            status_text = first_line # Store the full request line here
        
        # Parse headers
        headers = {}
        body_start_index = 1
        for i, line in enumerate(lines[1:], 1):
            if not line:
                body_start_index = i + 1
                break
            if ':' in line:
                key, value = line.split(':', 1)
                # Standardize header keys to lowercase for consistent access
                headers[key.strip().lower()] = value.strip()
        
        # Extract body
        body = "\r\n".join(lines[body_start_index:])
        
        return SipResponse(
            status_code=status_code,
            status_text=status_text,
            headers=headers,
            body=body,
            raw=response_str
        )
    except Exception as e:
        logger.error(f"Failed to parse SIP message: {e}\n--- Message was ---\n{response_str}\n----------------------", exc_info=True)
        return None 
"""
Settings and configuration management for Callie Caller.
Handles environment variables, validation, and default values.
"""

import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class ZohoSettings:
    """Zoho Voice SIP configuration."""
    sip_server: str
    sip_username: str  
    sip_password: str
    sip_port: int = 5060
    backup_server: Optional[str] = None
    account_label: Optional[str] = None

@dataclass  
class DeviceSettings:
    """Yealink device emulation settings."""
    mac_address: str
    model: str = "SIP-T46S"
    firmware: str = "66.85.0.5"
    custom_user_agent: Optional[str] = None
    
    @property
    def user_agent(self) -> str:
        """Generate proper Yealink User-Agent string."""
        if self.custom_user_agent:
            return self.custom_user_agent
        return f"Yealink {self.model} {self.firmware} ~{self.mac_address}"

@dataclass
class AISettings:
    """Google Gemini AI configuration."""
    api_key: str
    model: str = "gemini-2.0-flash-001"
    max_tokens: int = 150
    temperature: float = 0.7

@dataclass
class ServerSettings:
    """Flask web server configuration."""
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    
@dataclass
class CallSettings:
    """Call handling settings."""
    default_greeting: str = "Hello! This is an AI assistant. How can I help you today?"
    max_call_duration: int = 1800  # 30 minutes
    answer_timeout: int = 30
    # RTP port configuration for NAT traversal
    rtp_port_min: int = 10000  # Start of RTP port range
    rtp_port_max: int = 10100  # End of RTP port range (100 ports available)
    use_fixed_rtp_port: bool = True  # Use fixed port instead of random

@dataclass
class Settings:
    """Main settings container."""
    zoho: ZohoSettings
    device: DeviceSettings  
    ai: AISettings
    server: ServerSettings
    calls: CallSettings
    
    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables."""
        
        # Zoho Voice settings (required)
        zoho = ZohoSettings(
            sip_server=_get_required_env("ZOHO_SIP_SERVER"),
            sip_username=_get_required_env("ZOHO_SIP_USERNAME"), 
            sip_password=_get_required_env("ZOHO_SIP_PASSWORD"),
            sip_port=int(os.getenv("SIP_PORT", "5060")),
            backup_server=os.getenv("ZOHO_SIP_BACKUP_SERVER"),
            account_label=os.getenv("ACCOUNT_LABEL")
        )
        
        # Device emulation settings (required MAC address)
        device = DeviceSettings(
            mac_address="00:1a:2b:3c:4d:5e",  # MAC address registered with Zoho Voice
            model=os.getenv("DEVICE_MODEL", "SIP-T46S"),
            firmware=os.getenv("DEVICE_FIRMWARE", "66.85.0.5"),
            custom_user_agent=os.getenv("CUSTOM_USER_AGENT_OVERRIDE")
        )
        
        # AI settings (required API key)
        ai = AISettings(
            api_key=_get_required_env("GEMINI_API_KEY"),
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-001"),
            max_tokens=int(os.getenv("GEMINI_MAX_TOKENS", "150")),
            temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
        )
        
        # Server settings
        server = ServerSettings(
            host=os.getenv("FLASK_HOST", "0.0.0.0"),
            port=int(os.getenv("FLASK_PORT", "8080")),
            debug=os.getenv("FLASK_DEBUG", "false").lower() == "true"
        )
        
        # Call settings
        calls = CallSettings(
            default_greeting=os.getenv("DEFAULT_GREETING", "Hello! This is your AI voice assistant."),
            max_call_duration=int(os.getenv("MAX_CALL_DURATION", "300")),
            answer_timeout=int(os.getenv("ANSWER_TIMEOUT", "30")),
            rtp_port_min=int(os.getenv("RTP_PORT_MIN", "10000")),
            rtp_port_max=int(os.getenv("RTP_PORT_MAX", "10100")),
            use_fixed_rtp_port=os.getenv("USE_FIXED_RTP_PORT", "true").lower() == "true"
        )
        
        return cls(
            zoho=zoho,
            device=device,
            ai=ai, 
            server=server,
            calls=calls
        )
    
    def validate(self) -> None:
        """Validate all settings."""
        errors = []
        
        # Validate required fields are not empty
        if not self.zoho.sip_server:
            errors.append("ZOHO_SIP_SERVER is required")
        if not self.zoho.sip_username:
            errors.append("ZOHO_SIP_USERNAME is required")
        if not self.zoho.sip_password:
            errors.append("ZOHO_SIP_PASSWORD is required")
        if not self.device.mac_address:
            errors.append("CUSTOM_USER_AGENT (MAC address) is required")
        if not self.ai.api_key:
            errors.append("GEMINI_API_KEY is required")
            
        # Validate formats
        if self.device.mac_address and len(self.device.mac_address.replace(":", "")) != 12:
            errors.append("MAC address must be in format XX:XX:XX:XX:XX:XX")
            
        if self.zoho.sip_port < 1 or self.zoho.sip_port > 65535:
            errors.append("SIP port must be between 1 and 65535")
            
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")

def _get_required_env(key: str, default: Optional[str] = None) -> str:
    """Get required environment variable or raise error."""
    value = os.getenv(key, default)
    if not value:
        raise ValueError(f"Required environment variable {key} is not set")
    return value

# Global settings instance
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    """Get global settings instance (singleton pattern)."""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
        _settings.validate()
    return _settings

def reload_settings() -> Settings:
    """Reload settings from environment (useful for testing)."""
    global _settings
    load_dotenv(override=True)  # Reload .env file
    _settings = Settings.from_env()
    _settings.validate()
    return _settings 
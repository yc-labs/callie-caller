"""
PJSUA2-based SIP Client for robust telephony.
Handles SIP registration, call management, and session timers automatically.
"""

import logging
import time
import threading
from typing import Optional, Callable, Dict, Any, List
import pjsua2 as pj

from callie_caller.config import get_settings
from callie_caller.utils.network import get_public_ip
from .pjsua2_call import PjCall
from .pjsua2_audio_bridge import AIAudioMediaPort

logger = logging.getLogger(__name__)

class PjLogWriter(pj.LogWriter):
    """Custom log writer to redirect PJSUA2 logs to Python logging."""
    
    def write(self, entry):
        """Write PJSUA2 log entry to Python logger."""
        # Map PJSUA2 log levels to Python logging levels
        level_map = {
            0: logging.ERROR,    # Error
            1: logging.ERROR,    # Error  
            2: logging.WARNING,  # Warning
            3: logging.INFO,     # Info
            4: logging.DEBUG,    # Debug
            5: logging.DEBUG,    # Verbose
        }
        
        py_level = level_map.get(entry.level, logging.DEBUG)
        logger.log(py_level, f"[PJSIP] {entry.msg.strip()}")

class PjAccount(pj.Account):
    """
    Custom Account class to handle incoming calls and registration events.
    """
    
    def __init__(self, client: 'PjSipClient'):
        pj.Account.__init__(self)
        self.client = client
        logger.info("PjAccount initialized")
        
    def onRegState(self, prm):
        """Handle registration state changes."""
        info = self.getInfo()
        is_registered = (info.regIsActive and info.regStatus == 200)
        
        if is_registered:
            logger.info(f"✅ SIP registration successful! Expires in {info.regExpiresSec}s")
            self.client.registered = True
        else:
            status_text = info.regStatusText if info.regStatusText else "Unknown"
            logger.warning(f"⚠️ SIP registration state: {info.regStatus} {status_text}")
            self.client.registered = False
            
    def onIncomingCall(self, prm):
        """Handle incoming calls."""
        call = PjCall(self, prm.callId)
        call.client = self.client
        
        call_info = call.getInfo()
        remote_uri = call_info.remoteUri
        logger.info(f"📞 Incoming call from {remote_uri}")
        
        # Store the call
        self.client.active_calls[call_info.id] = call
        
        # Notify callback if set
        if self.client.on_incoming_call:
            self.client.on_incoming_call(call)
        else:
            # Auto-answer if no callback
            logger.info("Auto-answering incoming call (no callback set)")
            call.answer()

class PjSipClient:
    """
    PJSUA2-based SIP client with automatic session timer support.
    """
    
    def __init__(self, on_incoming_call: Optional[Callable[[PjCall], None]] = None):
        """
        Initialize PJSUA2 SIP client.
        
        Args:
            on_incoming_call: Callback for handling incoming calls
        """
        self.settings = get_settings()
        self.on_incoming_call = on_incoming_call
        
        # PJSUA2 components
        self.ep: Optional[pj.Endpoint] = None
        self.account: Optional[PjAccount] = None
        self.transport: Optional[pj.TransportId] = None
        
        # State
        self.local_ip: Optional[str] = None
        self.public_ip: Optional[str] = None
        self.local_port: Optional[int] = None
        self.running = False
        self.registered = False
        self.active_calls: Dict[int, PjCall] = {}
        
        # Audio bridge for AI integration
        self.ai_audio_port: Optional[AIAudioMediaPort] = None
        
        logger.info("PJSUA2 SIP client initialized")
    
    def start(self, request_headers: Optional[Dict[str, str]] = None) -> bool:
        """Start the PJSUA2 SIP client."""
        try:
            # Get IP addresses
            self.public_ip = get_public_ip(request_headers)
            self.local_ip = self._get_local_ip()
            
            # Create endpoint
            self.ep = pj.Endpoint()
            self.ep.libCreate()
            
            # Configure endpoint
            ep_cfg = pj.EpConfig()
            
            # Configure logging
            ep_cfg.logConfig.level = 4  # Debug level
            ep_cfg.logConfig.consoleLevel = 4
            log_writer = PjLogWriter()
            ep_cfg.logConfig.writer = log_writer
            
            # Configure media
            ep_cfg.medConfig.clockRate = 8000  # Standard telephony rate
            ep_cfg.medConfig.sndClockRate = 16000  # Higher quality for AI
            ep_cfg.medConfig.quality = 10  # Maximum quality
            
            # Initialize endpoint
            self.ep.libInit(ep_cfg)
            
            # Create UDP transport
            transport_cfg = pj.TransportConfig()
            transport_cfg.port = 0  # Use any available port
            
            # Try to bind to specific port range for NAT
            if hasattr(self.settings.calls, 'use_fixed_rtp_port') and self.settings.calls.use_fixed_rtp_port:
                port_min = getattr(self.settings.calls, 'rtp_port_min', 5060)
                port_max = getattr(self.settings.calls, 'rtp_port_max', 5160)
                
                for port in range(port_min, port_max + 1):
                    try:
                        transport_cfg.port = port
                        self.transport = self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, transport_cfg)
                        self.local_port = port
                        logger.info(f"🎯 SIP transport bound to fixed port: {port}")
                        break
                    except Exception:
                        continue
            
            if not self.transport:
                # Fallback to any port
                transport_cfg.port = 0
                self.transport = self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, transport_cfg)
                transport_info = self.ep.transportGetInfo(self.transport)
                self.local_port = transport_info.localAddress.split(':')[-1]
                logger.info(f"📡 SIP transport on random port: {self.local_port}")
            
            # Start the library
            self.ep.libStart()
            
            # Create AI audio port
            self.ai_audio_port = AIAudioMediaPort()
            self.ai_audio_port.createPort("AI_Audio_Port")
            logger.info("🎤 AI audio port created for media bridging")
            
            self.running = True
            logger.info(f"✅ PJSUA2 client started on {self.local_ip}:{self.local_port} (Public: {self.public_ip})")
            logger.info(f"🤖 Emulating: {self.settings.device.user_agent}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start PJSUA2 client: {e}")
            return False
    
    def register(self) -> bool:
        """Register with SIP server."""
        if not self.ep or not self.running:
            logger.error("Cannot register - client not started")
            return False
            
        try:
            logger.info(f"📞 Registering with {self.settings.zoho.sip_server}...")
            
            # Create account config
            acc_cfg = pj.AccountConfig()
            
            # Set SIP URI
            acc_cfg.idUri = f"sip:{self.settings.zoho.sip_username}@{self.settings.zoho.sip_server}"
            
            # Set registrar
            acc_cfg.regConfig.registrarUri = f"sip:{self.settings.zoho.sip_server}"
            acc_cfg.regConfig.registerOnAdd = True
            
            # Enable session timers (crucial for preventing 30-second drops)
            acc_cfg.callConfig.timerUse = pj.PJSUA_SIP_TIMER_ALWAYS
            acc_cfg.callConfig.timerSessExpiresSec = 1800  # 30 minutes
            
            # Set authentication
            cred = pj.AuthCredInfo()
            cred.scheme = "digest"
            cred.realm = "*"  # Will match any realm
            cred.username = self.settings.zoho.sip_username
            cred.dataType = pj.PJSIP_CRED_DATA_PLAIN_PASSWD
            cred.data = self.settings.zoho.sip_password
            acc_cfg.sipConfig.authCreds.append(cred)
            
            # NAT traversal settings
            if self.public_ip:
                acc_cfg.natConfig.sipStunUse = pj.PJSUA_STUN_USE_DEFAULT
                acc_cfg.natConfig.mediaStunUse = pj.PJSUA_STUN_USE_DEFAULT
                # Set public address for Contact header
                acc_cfg.sipConfig.contactParams = f";ob;reg-id=1;+sip.instance=\"<urn:uuid:00000000-0000-0000-0000-{self.settings.device.mac_address.replace(':', '')}\""
            
            # Set User-Agent
            acc_cfg.userAgent = self.settings.device.user_agent
            
            # Create account
            self.account = PjAccount(self)
            self.account.create(acc_cfg)
            
            # Wait for registration
            timeout = 10
            start_time = time.time()
            while not self.registered and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if self.registered:
                logger.info("✅ SIP registration successful!")
                return True
            else:
                logger.error("❌ SIP registration timeout")
                return False
                
        except Exception as e:
            logger.error(f"❌ Registration failed: {e}")
            return False
    
    def make_call(self, phone_number: str, initial_message: Optional[str] = None) -> Optional[PjCall]:
        """
        Make an outbound call.
        
        Args:
            phone_number: Target phone number
            initial_message: Optional initial AI message
            
        Returns:
            PjCall object if successful, None otherwise
        """
        if not self.account or not self.registered:
            logger.error("Cannot make call - not registered")
            return None
            
        try:
            logger.info(f"📞 Making call to {phone_number}")
            
            # Create call settings
            call_param = pj.CallOpParam()
            call_param.opt.audioCount = 1
            call_param.opt.videoCount = 0
            
            # Set custom headers
            hdr = pj.SipHeader()
            hdr.hName = "X-AI-Initial-Message"
            hdr.hValue = initial_message or self.settings.calls.default_greeting
            call_param.txOption.headers.append(hdr)
            
            # Make the call
            sip_uri = f"sip:{phone_number}@{self.settings.zoho.sip_server}"
            call = PjCall(self.account)
            call.client = self
            call.initial_message = initial_message
            
            call.makeCall(sip_uri, call_param)
            
            # Store the call
            call_info = call.getInfo()
            self.active_calls[call_info.id] = call
            
            logger.info(f"✅ Call initiated to {phone_number} (ID: {call_info.id})")
            return call
            
        except Exception as e:
            logger.error(f"❌ Failed to make call: {e}")
            return None
    
    def stop(self) -> None:
        """Stop the PJSUA2 client and cleanup."""
        logger.info("🛑 Stopping PJSUA2 client...")
        
        try:
            # Hangup all active calls
            for call_id, call in list(self.active_calls.items()):
                try:
                    if call.isActive():
                        logger.info(f"Hanging up call {call_id}")
                        call.hangup()
                except Exception as e:
                    logger.error(f"Error hanging up call {call_id}: {e}")
            
            # Delete account
            if self.account:
                try:
                    self.account.shutdown()
                    del self.account
                    self.account = None
                except Exception as e:
                    logger.error(f"Error deleting account: {e}")
            
            # Delete AI audio port
            if self.ai_audio_port:
                try:
                    del self.ai_audio_port
                    self.ai_audio_port = None
                except Exception as e:
                    logger.error(f"Error deleting audio port: {e}")
            
            # Destroy endpoint
            if self.ep:
                try:
                    self.ep.libDestroy()
                    del self.ep
                    self.ep = None
                except Exception as e:
                    logger.error(f"Error destroying endpoint: {e}")
            
            self.running = False
            logger.info("✅ PJSUA2 client stopped")
            
        except Exception as e:
            logger.error(f"❌ Error stopping client: {e}")
    
    def _get_local_ip(self) -> str:
        """Get local IP address that can reach the SIP server."""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((self.settings.zoho.sip_server, self.settings.zoho.sip_port))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
    
    def get_audio_endpoint(self) -> Optional[AIAudioMediaPort]:
        """Get the AI audio endpoint for call bridging."""
        return self.ai_audio_port
    
    def handle_call_media_state(self, call: PjCall) -> None:
        """Handle media state changes for a call."""
        try:
            call_info = call.getInfo()
            
            for mi in call_info.media:
                if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                    # Get call's audio media
                    audio_media = call.getAudioMedia(mi.index)
                    
                    # Connect audio streams through AI port
                    if self.ai_audio_port:
                        # Caller's voice → AI
                        audio_media.startTransmit2(self.ai_audio_port)
                        logger.info("🎤 Connected caller audio → AI")
                        
                        # AI → Caller
                        self.ai_audio_port.startTransmit2(audio_media)
                        logger.info("🤖 Connected AI audio → caller")
                        
                        # Start AI conversation
                        if hasattr(call, 'initial_message'):
                            self.ai_audio_port.start_ai_conversation(call.initial_message)
                    
                    logger.info(f"✅ Audio streams connected for call {call_info.id}")
                    
        except Exception as e:
            logger.error(f"❌ Error handling media state: {e}") 
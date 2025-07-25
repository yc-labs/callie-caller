"""
PJSUA2-based Call handling with automatic session timer management.
"""

import logging
import time
from typing import Optional, Dict, Any
import pjsua2 as pj

logger = logging.getLogger(__name__)

class PjCall(pj.Call):
    """
    Custom Call class that properly handles session timers and call lifecycle.
    """
    
    def __init__(self, account: pj.Account, call_id: int = -1):
        """Initialize call with account."""
        pj.Call.__init__(self, account, call_id)
        self.client = None  # Will be set by PjSipClient
        self.initial_message: Optional[str] = None
        self.start_time: Optional[float] = None
        self.connected_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.ai_conversation_started = False
        logger.info(f"PjCall initialized (ID: {call_id})")
    
    def onCallState(self, prm: pj.OnCallStateParam):
        """Handle call state changes."""
        try:
            call_info = self.getInfo()
            state = call_info.state
            state_text = call_info.stateText
            
            logger.info(f"📞 Call {call_info.id} state: {state} - {state_text}")
            
            # Track call lifecycle
            if state == pj.PJSIP_INV_STATE_CALLING and not self.start_time:
                self.start_time = time.time()
                logger.info("🔔 Call is ringing...")
                
            elif state == pj.PJSIP_INV_STATE_CONFIRMED:
                if not self.connected_time:
                    self.connected_time = time.time()
                    setup_time = self.connected_time - self.start_time if self.start_time else 0
                    logger.info(f"✅ Call CONNECTED! (Setup time: {setup_time:.1f}s)")
                    
                    # Log session timer info if available
                    if hasattr(call_info, 'sessionTimerStatus'):
                        timer_status = call_info.sessionTimerStatus
                        logger.info(f"⏱️ Session Timer Status: Active={timer_status.isActive}, "
                                  f"Interval={timer_status.interval}s, Role={timer_status.role}")
                    
            elif state == pj.PJSIP_INV_STATE_DISCONNECTED:
                self.end_time = time.time()
                duration = self.end_time - self.connected_time if self.connected_time else 0
                total_duration = self.end_time - self.start_time if self.start_time else 0
                
                logger.info(f"📞 Call ended - Duration: {duration:.1f}s (Total: {total_duration:.1f}s)")
                logger.info(f"📊 Disconnect reason: {call_info.lastReason}")
                
                # Remove from active calls
                if self.client and call_info.id in self.client.active_calls:
                    del self.client.active_calls[call_info.id]
                    
                # Cleanup AI conversation if needed
                if self.ai_conversation_started and self.client and self.client.ai_audio_port:
                    self.client.ai_audio_port.stop_ai_conversation()
                    
        except Exception as e:
            logger.error(f"❌ Error in onCallState: {e}")
    
    def onCallMediaState(self, prm: pj.OnCallMediaStateParam):
        """Handle media state changes - connect audio streams."""
        try:
            call_info = self.getInfo()
            logger.info(f"🎵 Media state change for call {call_info.id}")
            
            # Check if we have active audio media
            for mi in call_info.media:
                if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                    logger.info(f"🎤 Audio media is ACTIVE (index: {mi.index})")
                    
                    # Let the client handle media bridging
                    if self.client:
                        self.client.handle_call_media_state(self)
                        self.ai_conversation_started = True
                    
                elif mi.type == pj.PJMEDIA_TYPE_AUDIO:
                    logger.warning(f"⚠️ Audio media status: {mi.status}")
                    
        except Exception as e:
            logger.error(f"❌ Error in onCallMediaState: {e}")
    
    def onCallTsxState(self, prm: pj.OnCallTsxStateParam):
        """Handle transaction state changes (for debugging)."""
        try:
            # Log important transaction events
            if prm.e.type == pj.PJSIP_EVENT_TSX_STATE:
                tsx = prm.e.body.tsxState.tsx
                if tsx.method.name in ["INVITE", "BYE", "UPDATE"]:
                    logger.debug(f"📋 Transaction {tsx.method.name}: {tsx.state} - {tsx.statusCode}")
                    
        except Exception as e:
            logger.debug(f"Transaction state error: {e}")
    
    def onStreamCreated(self, prm: pj.OnStreamCreatedParam):
        """Handle stream creation - useful for RTP configuration."""
        try:
            logger.info("🌊 RTP stream created for call")
            # Could configure stream parameters here if needed
        except Exception as e:
            logger.error(f"❌ Error in onStreamCreated: {e}")
    
    def onStreamDestroyed(self, prm: pj.OnStreamDestroyedParam):
        """Handle stream destruction."""
        try:
            logger.info("🌊 RTP stream destroyed for call")
        except Exception as e:
            logger.error(f"❌ Error in onStreamDestroyed: {e}")
    
    def answer(self, status_code: int = 200) -> None:
        """Answer incoming call."""
        try:
            prm = pj.CallOpParam()
            prm.statusCode = status_code
            self.answer(prm)
            logger.info(f"📞 Answered call with {status_code}")
        except Exception as e:
            logger.error(f"❌ Error answering call: {e}")
    
    def hangup(self, status_code: int = 200) -> None:
        """Hangup the call."""
        try:
            if self.isActive():
                prm = pj.CallOpParam()
                prm.statusCode = status_code
                super().hangup(prm)
                logger.info(f"📞 Hanging up call with {status_code}")
        except Exception as e:
            logger.error(f"❌ Error hanging up call: {e}")
    
    def get_duration(self) -> float:
        """Get call duration in seconds."""
        if self.connected_time:
            end = self.end_time or time.time()
            return end - self.connected_time
        return 0.0
    
    def get_info_dict(self) -> Dict[str, Any]:
        """Get call information as dictionary."""
        try:
            info = self.getInfo()
            return {
                'id': info.id,
                'state': info.state,
                'state_text': info.stateText,
                'remote_uri': info.remoteUri,
                'duration': self.get_duration(),
                'connected': info.state == pj.PJSIP_INV_STATE_CONFIRMED,
                'start_time': self.start_time,
                'connected_time': self.connected_time,
                'ai_active': self.ai_conversation_started
            }
        except Exception as e:
            logger.error(f"Error getting call info: {e}")
            return {} 
"""
Callie Caller - AI Voice Assistant for Zoho Voice
A production-ready system for intelligent phone conversations.
"""

__version__ = "1.0.0"
__author__ = "Callie Development Team"
__description__ = "AI Voice Assistant with SIP integration and real-time conversation"

from callie_caller.core.agent import CallieAgent
from callie_caller.sip.client import SipClient
from callie_caller.ai.conversation import ConversationManager
from callie_caller.ai.live_client import AudioBridge

__all__ = ['CallieAgent', 'SipClient', 'ConversationManager', 'AudioBridge'] 
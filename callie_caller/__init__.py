"""
Callie Caller - AI Voice Agent
Production-ready AI voice assistant with SIP calling capabilities.

This package provides a complete solution for creating AI-powered phone conversations
using Google's Gemini Live API and SIP protocol integration.
"""

__version__ = "1.0.0"
__author__ = "Troy Fortin"
__description__ = "AI Voice Agent with SIP integration and real-time conversation capabilities"
__license__ = "MIT"

from callie_caller.core.agent import CallieAgent
from callie_caller.sip.client import SipClient
from callie_caller.ai.conversation import ConversationManager
from callie_caller.ai.live_client import AudioBridge

__all__ = ['CallieAgent', 'SipClient', 'ConversationManager', 'AudioBridge'] 
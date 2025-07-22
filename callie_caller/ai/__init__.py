"""
AI module for conversation generation and real-time audio.
"""

from .client import GeminiClient
from .conversation import ConversationManager
from .live_client import AudioBridge

__all__ = ['GeminiClient', 'ConversationManager', 'AudioBridge'] 
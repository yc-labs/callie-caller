"""
AI module for conversation generation, real-time audio, and function calling.
"""

from .client import GeminiClient
from .conversation import ConversationManager
from .live_client import AudioBridge
from .tools import get_tool_manager, ToolManager

__all__ = ['GeminiClient', 'ConversationManager', 'AudioBridge', 'get_tool_manager', 'ToolManager'] 
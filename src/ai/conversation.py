"""
Conversation Manager for AI chat capabilities.
Handles conversation state, history, and intelligent response generation.
"""

import time
import logging
import json
import os
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from ai.client import GeminiClient

logger = logging.getLogger(__name__)

class ConversationState(Enum):
    """Conversation states."""
    IDLE = "idle"
    ACTIVE = "active"
    WAITING = "waiting"
    ENDED = "ended"

@dataclass
class ConversationMessage:
    """Individual conversation message."""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: float = field(default_factory=time.time)
    sentiment: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Conversation:
    """Complete conversation context."""
    conversation_id: str
    phone_number: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    state: ConversationState = ConversationState.IDLE
    messages: List[ConversationMessage] = field(default_factory=list)
    summary: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration(self) -> float:
        """Get conversation duration in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time
        
    @property
    def message_count(self) -> int:
        """Get total message count."""
        return len(self.messages)
        
    @property
    def user_message_count(self) -> int:
        """Get user message count."""
        return len([m for m in self.messages if m.role == 'user'])
        
    @property
    def assistant_message_count(self) -> int:
        """Get assistant message count."""
        return len([m for m in self.messages if m.role == 'assistant'])

class ConversationManager:
    """Manages AI conversations and chat state."""

    HISTORY_FILE = os.getenv("CONVERSATION_HISTORY_FILE", "data/conversations.json")

    def __init__(self):
        """Initialize conversation manager."""
        self.ai_client = GeminiClient()
        self.active_conversations: Dict[str, Conversation] = {}
        self.conversation_history: List[Conversation] = []

        # Ensure history file exists
        if not os.path.exists(self.HISTORY_FILE):
            with open(self.HISTORY_FILE, "w") as f:
                json.dump([], f)

    def _load_history(self) -> List[Dict[str, Any]]:
        with open(self.HISTORY_FILE, "r") as f:
            return json.load(f)

    def _save_history(self, history: List[Dict[str, Any]]):
        with open(self.HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)

    def _serialize_conversation(self, conversation: Conversation) -> Dict[str, Any]:
        return {
            "conversation_id": conversation.conversation_id,
            "phone_number": conversation.phone_number,
            "start_time": conversation.start_time,
            "end_time": conversation.end_time,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "sentiment": m.sentiment,
                    "metadata": m.metadata,
                }
                for m in conversation.messages
            ],
            "summary": conversation.summary,
        }
        
    def start_conversation(self, conversation_id: str, phone_number: Optional[str] = None) -> Conversation:
        """
        Start a new conversation.
        
        Args:
            conversation_id: Unique conversation identifier
            phone_number: Optional phone number for context
            
        Returns:
            New conversation object
        """
        conversation = Conversation(
            conversation_id=conversation_id,
            phone_number=phone_number,
            state=ConversationState.ACTIVE
        )
        
        self.active_conversations[conversation_id] = conversation
        logger.info(f"Started conversation {conversation_id} with {phone_number or 'unknown number'}")
        
        return conversation
        
    def end_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """
        End an active conversation.
        
        Args:
            conversation_id: Conversation to end
            
        Returns:
            Ended conversation or None if not found
        """
        conversation = self.active_conversations.get(conversation_id)
        if not conversation:
            logger.warning(f"Attempted to end non-existent conversation {conversation_id}")
            return None
            
        conversation.state = ConversationState.ENDED
        conversation.end_time = time.time()
        
        # Generate conversation summary
        if conversation.messages:
            try:
                conversation.summary = self.ai_client.generate_call_summary(
                    [{'role': m.role, 'content': m.content} for m in conversation.messages]
                )
            except Exception as e:
                logger.error(f"Failed to generate conversation summary: {e}")
                conversation.summary = f"Conversation with {conversation.message_count} messages"

        # Move to history
        self.conversation_history.append(conversation)
        del self.active_conversations[conversation_id]

        # Persist to history file
        try:
            history = self._load_history()
            history.append(self._serialize_conversation(conversation))
            self._save_history(history)
        except Exception as e:
            logger.error(f"Failed to save conversation history: {e}")
        
        logger.info(f"Ended conversation {conversation_id} after {conversation.duration:.1f}s with {conversation.message_count} messages")
        return conversation
        
    def add_user_message(self, conversation_id: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Add a user message to the conversation.
        
        Args:
            conversation_id: Target conversation
            message: User's message content
            metadata: Optional message metadata
            
        Returns:
            True if message added successfully
        """
        conversation = self.active_conversations.get(conversation_id)
        if not conversation:
            logger.error(f"Cannot add message to non-existent conversation {conversation_id}")
            return False
            
        # Analyze sentiment
        sentiment = None
        try:
            sentiment = self.ai_client.analyze_sentiment(message)
        except Exception as e:
            logger.warning(f"Failed to analyze sentiment: {e}")
            
        # Create message
        conv_message = ConversationMessage(
            role='user',
            content=message,
            sentiment=sentiment,
            metadata=metadata or {}
        )
        
        conversation.messages.append(conv_message)
        logger.debug(f"Added user message to {conversation_id}: {message[:50]}...")
        
        return True
        
    def generate_response(self, conversation_id: str, context: Optional[str] = None) -> Optional[str]:
        """
        Generate AI response for the conversation.
        
        Args:
            conversation_id: Target conversation
            context: Optional additional context
            
        Returns:
            Generated response or None if failed
        """
        conversation = self.active_conversations.get(conversation_id)
        if not conversation:
            logger.error(f"Cannot generate response for non-existent conversation {conversation_id}")
            return None
            
        if not conversation.messages:
            logger.warning(f"No messages in conversation {conversation_id}")
            return None
            
        # Get last user message
        user_messages = [m for m in conversation.messages if m.role == 'user']
        if not user_messages:
            logger.warning(f"No user messages in conversation {conversation_id}")
            return None
            
        last_message = user_messages[-1].content
        
        # Build conversation history for context
        history = [
            {'role': m.role, 'content': m.content} 
            for m in conversation.messages[-10:]  # Last 10 messages
        ]
        
        try:
            # Generate response
            response = self.ai_client.generate_response(last_message, history)
            
            # Add response to conversation
            conv_response = ConversationMessage(
                role='assistant',
                content=response,
                metadata={'context': context} if context else {}
            )
            
            conversation.messages.append(conv_response)
            logger.debug(f"Generated response for {conversation_id}: {response[:50]}...")
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to generate response for {conversation_id}: {e}")
            return None
            
    def generate_greeting(self, conversation_id: str, context: Optional[str] = None) -> Optional[str]:
        """
        Generate a greeting for the conversation.
        
        Args:
            conversation_id: Target conversation
            context: Optional context about the call
            
        Returns:
            Generated greeting or None if failed
        """
        conversation = self.active_conversations.get(conversation_id)
        if not conversation:
            logger.error(f"Cannot generate greeting for non-existent conversation {conversation_id}")
            return None
            
        try:
            # Add phone number context if available
            full_context = context or ""
            if conversation.phone_number:
                full_context += f" Caller: {conversation.phone_number}"
                
            greeting = self.ai_client.generate_greeting(full_context)
            
            # Add greeting as assistant message
            conv_greeting = ConversationMessage(
                role='assistant',
                content=greeting,
                metadata={'type': 'greeting', 'context': context}
            )
            
            conversation.messages.append(conv_greeting)
            logger.debug(f"Generated greeting for {conversation_id}: {greeting}")
            
            return greeting
            
        except Exception as e:
            logger.error(f"Failed to generate greeting for {conversation_id}: {e}")
            return None
            
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get active conversation by ID."""
        return self.active_conversations.get(conversation_id)
        
    def get_conversation_history(self, phone_number: Optional[str] = None, limit: int = 10) -> List[Conversation]:
        """
        Get conversation history.
        
        Args:
            phone_number: Optional filter by phone number
            limit: Maximum number of conversations to return
            
        Returns:
            List of historical conversations
        """
        conversations = self.conversation_history
        
        if phone_number:
            conversations = [c for c in conversations if c.phone_number == phone_number]
            
        # Sort by start time (most recent first)
        conversations.sort(key=lambda c: c.start_time, reverse=True)
        
        return conversations[:limit]
        
    def get_conversation_stats(self) -> Dict[str, Any]:
        """Get conversation statistics."""
        total_conversations = len(self.conversation_history) + len(self.active_conversations)
        total_messages = sum(c.message_count for c in self.conversation_history)
        total_messages += sum(c.message_count for c in self.active_conversations.values())
        
        avg_duration = 0
        if self.conversation_history:
            avg_duration = sum(c.duration for c in self.conversation_history) / len(self.conversation_history)
            
        return {
            'total_conversations': total_conversations,
            'active_conversations': len(self.active_conversations),
            'completed_conversations': len(self.conversation_history),
            'total_messages': total_messages,
            'average_duration': avg_duration
        }
        
    def cleanup_old_conversations(self, max_age_hours: int = 24) -> int:
        """
        Clean up old conversations from history.
        
        Args:
            max_age_hours: Maximum age of conversations to keep
            
        Returns:
            Number of conversations removed
        """
        cutoff_time = time.time() - (max_age_hours * 3600)
        old_conversations = [c for c in self.conversation_history if c.start_time < cutoff_time]
        
        for conversation in old_conversations:
            self.conversation_history.remove(conversation)
            
        logger.info(f"Cleaned up {len(old_conversations)} old conversations")
        return len(old_conversations)



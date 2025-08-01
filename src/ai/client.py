"""
Google Gemini AI client for conversation generation.
Handles AI model communication and response generation.
"""

import logging
import os
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GeminiClient:
    """Client for Google Gemini AI model."""
    
    def __init__(self):
        """Initialize Gemini client with settings."""
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
            
        self.model = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash-preview-native-audio-dialog")
        self.client = genai.Client(
            http_options={"api_version": "v1beta"},
            api_key=self.api_key
        )
        self._test_connection()
        
    def _test_connection(self) -> None:
        """Test connection to Gemini API."""
        try:
            # Use a standard text model for connection testing
            # Audio models only work with Live API, not generate_content
            test_model = "models/gemini-2.0-flash-exp"
            response = self.client.models.generate_content(
                model=test_model,
                contents="Hello, this is a connection test. Please respond with 'OK'."
            )
            logger.info("Gemini AI connection tested successfully")
        except Exception as e:
            logger.error(f"Gemini AI connection test failed: {e}")
            raise RuntimeError(f"Failed to connect to Gemini AI: {e}")
    
    def generate_greeting(self, context: Optional[str] = None) -> str:
        """
        Generate a greeting message for calls.
        
        Args:
            context: Optional context about the call
            
        Returns:
            Generated greeting message
        """
        prompt = "Generate a brief, professional greeting for an AI voice assistant answering a phone call."
        
        if context:
            prompt += f" Context: {context}"
            
        prompt += " Keep it under 20 words and sound natural."
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            
            greeting = response.text.strip()
            logger.debug(f"Generated greeting: {greeting}")
            return greeting
            
        except Exception as e:
            logger.error(f"Failed to generate greeting: {e}")
            return "Hello! This is your AI voice assistant."
    
    def generate_response(self, message: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Generate a response to a user message.
        
        Args:
            message: User's message to respond to
            conversation_history: Previous conversation messages
            
        Returns:
            Generated response
        """
        # Build conversation context
        context_messages = []
        
        if conversation_history:
            for entry in conversation_history[-5:]:  # Last 5 messages for context
                role = entry.get('role', 'user')
                content = entry.get('content', '')
                if role == 'user':
                    context_messages.append(f"User: {content}")
                elif role == 'assistant':
                    context_messages.append(f"Assistant: {content}")
        
        # Create prompt
        prompt = """You are a helpful AI voice assistant. Respond to the user's message in a natural, conversational way.
Keep your response concise (under 50 words) since this is a voice conversation.
Be friendly, professional, and helpful.

"""
        
        if context_messages:
            prompt += "Conversation history:\n" + "\n".join(context_messages) + "\n\n"
            
        prompt += f"User: {message}\n\nAssistant:"
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            
            ai_response = response.text.strip()
            logger.debug(f"Generated response: {ai_response[:100]}...")
            return ai_response
            
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return "I'm sorry, I'm having trouble understanding right now. Could you please repeat that?"
    
    def generate_call_summary(self, conversation_history: List[Dict[str, str]]) -> str:
        """
        Generate a summary of the call conversation.
        
        Args:
            conversation_history: Complete conversation history
            
        Returns:
            Call summary
        """
        if not conversation_history:
            return "No conversation took place."
            
        # Build conversation text
        conversation_text = []
        for entry in conversation_history:
            role = entry.get('role', 'user')
            content = entry.get('content', '')
            if role == 'user':
                conversation_text.append(f"Caller: {content}")
            elif role == 'assistant':
                conversation_text.append(f"AI: {content}")
        
        prompt = f"""Summarize this phone conversation in 1-2 sentences:

{chr(10).join(conversation_text)}

Summary:"""
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            
            summary = response.text.strip()
            logger.info(f"Generated call summary: {summary}")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return "Call conversation summary unavailable."
    
    def analyze_sentiment(self, message: str) -> str:
        """
        Analyze sentiment of a message.
        
        Args:
            message: Message to analyze
            
        Returns:
            Sentiment (positive, negative, neutral)
        """
        prompt = f"""Analyze the sentiment of this message and respond with only one word: "positive", "negative", or "neutral".

Message: {message}

Sentiment:"""
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt
            )
            
            sentiment = response.text.strip().lower()
            if sentiment in ['positive', 'negative', 'neutral']:
                return sentiment
            else:
                return 'neutral'
                
        except Exception as e:
            logger.error(f"Failed to analyze sentiment: {e}")
            return 'neutral' 

async def test_gemini_connection() -> bool:
    """
    Test connection to Gemini API.
    
    Returns:
        True if connection successful, False otherwise
    """
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-native-audio-dialog")
        client = genai.Client(api_key=api_key)
        
        response = client.models.generate_content(
            model=model,
            contents="Hello, this is a connection test. Please respond with 'OK'."
        )
        
        if response and response.text:
            logger.info("Gemini AI connection test successful")
            return True
        else:
            logger.error("Gemini AI connection test failed - no response")
            return False
            
    except Exception as e:
        logger.error(f"Gemini AI connection test failed: {e}")
        return False 

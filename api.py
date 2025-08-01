import os
import asyncio
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import uvicorn

from voip.voip_client import VoipClient
from voip.gemini_voip_adapter import GeminiVoipAdapter
from ai.conversation import ConversationManager

app = FastAPI()
conversation_manager = ConversationManager()

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "API is running"}

class CallRequest(BaseModel):
    target_number: str
    initial_message: Optional[str] = None
    call_context: Optional[str] = None

@app.post("/call/sync")
def make_call_sync(request: CallRequest):
    """Make a call and wait for it to complete."""
    # This is a simplified synchronous wrapper. 
    # In a real-world scenario, you would have a more robust way to manage call state.
    
    cfg = {
        'primary_domain': os.getenv("ZOHO_PRIMARY_DOMAIN"),
        'fallback_domain': os.getenv("ZOHO_FALLBACK_DOMAIN"),
        'sip_user': os.getenv("ZOHO_SIP_USER"),
        'sip_password': os.getenv("ZOHO_SIP_PASSWORD"),
        'user_agent': os.getenv("ZOHO_USER_AGENT", "Python PJSUA2")
    }
    
    voip_client = VoipClient(cfg, test_mode="tone", tone_seconds=0)
    adapter = GeminiVoipAdapter(
        voip_client=voip_client,
        target_number=request.target_number,
        initial_message=request.initial_message,
        call_context=request.call_context,
    )
    
    # Get the conversation ID before starting
    conversation_id = adapter._bridge.conversation_id
    
    # This blocks until the call completes
    adapter.start()
    
    # After the call ends, try to get the conversation from history
    conversations = conversation_manager.get_conversation_history(phone_number=request.target_number, limit=1)
    
    if conversations:
        conversation = conversations[0]
        return {
            "status": "call_completed",
            "conversation_id": conversation.conversation_id,
            "transcript": conversation.messages,
            "summary": conversation.summary,
            "duration": conversation.duration,
            "message_count": conversation.message_count,
        }
    else:
        # Fallback if no conversation found
        return {
            "status": "call_completed",
            "conversation_id": conversation_id,
            "message": "Call completed but conversation details not available"
        }

def run_call(adapter: GeminiVoipAdapter):
    adapter.start()

@app.post("/call/async")
async def make_call_async(request: CallRequest, background_tasks: BackgroundTasks):
    """Make a call asynchronously."""
    cfg = {
        'primary_domain': os.getenv("ZOHO_PRIMARY_DOMAIN"),
        'fallback_domain': os.getenv("ZOHO_FALLBACK_DOMAIN"),
        'sip__user': os.getenv("ZOHO_SIP_USER"),
        'sip_password': os.getenv("ZOHO_SIP_PASSWORD"),
        'user_agent': os.getenv("ZOHO_USER_AGENT", "Python PJSUA2")
    }
    
    voip_client = VoipClient(cfg, test_mode="tone", tone_seconds=0)
    adapter = GeminiVoipAdapter(
        voip_client=voip_client,
        target_number=request.target_number,
        initial_message=request.initial_message,
        call_context=request.call_context,
    )
    
    background_tasks.add_task(run_call, adapter)
    
    return {"status": "call_initiated", "conversation_id": adapter._bridge.conversation_id}

@app.get("/call/status/{conversation_id}")
def get_call_status(conversation_id: str):
    """Get the status of a call."""
    conversation = conversation_manager.get_conversation(conversation_id)
    if conversation:
        return {"status": "in_progress"}
    
    conversation = conversation_manager.get_conversation_history(limit=100)
    conversation = next((c for c in conversation if c.conversation_id == conversation_id), None)

    if conversation:
        return {
            "status": "call_completed",
            "conversation_id": conversation.conversation_id,
            "transcript": conversation.messages,
            "summary": conversation.summary,
            "duration": conversation.duration,
            "message_count": conversation.message_count,
        }
    
    return {"status": "not_found"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

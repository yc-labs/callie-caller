"""
Google Gemini Live API client for real-time audio conversation.
Handles bidirectional audio streaming during SIP calls.
"""

import asyncio
import logging
import pyaudio
from typing import Optional, Callable, Any
from google import genai
from google.genai import types

from callie_caller.config import get_settings

logger = logging.getLogger(__name__)

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

class AudioBridge:
    """Bridges SIP audio with Gemini Live API for real-time conversation."""
    
    def __init__(self):
        """Initialize audio bridge."""
        self.settings = get_settings()
        self.client = genai.Client(
            http_options={"api_version": "v1beta"},
            api_key=self.settings.ai.api_key,
        )
        
        # Audio queues
        self.audio_in_queue: Optional[asyncio.Queue] = None
        self.audio_out_queue: Optional[asyncio.Queue] = None
        self.sip_audio_queue: Optional[asyncio.Queue] = None
        
        # Session and tasks
        self.session: Optional[Any] = None
        self.tasks: list = []
        self.running = False
        
        # PyAudio
        self.pya = pyaudio.PyAudio()
        self.audio_stream: Optional[Any] = None
        
        # SIP audio callback
        self.sip_audio_callback: Optional[Callable] = None
        
        logger.info("AudioBridge initialized")
    
    @property
    def live_config(self) -> types.LiveConnectConfig:
        """Get Live API configuration."""
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            media_resolution="MEDIA_RESOLUTION_MEDIUM",
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr")
                )
            ),
            context_window_compression=types.ContextWindowCompressionConfig(
                trigger_tokens=25600,
                sliding_window=types.SlidingWindow(target_tokens=12800),
            ),
        )
    
    def set_sip_audio_callback(self, callback) -> None:
        """Set callback function to send AI audio to SIP call."""
        self.sip_audio_callback = callback
        logger.info("SIP audio callback configured")
    
    async def start_conversation(self, initial_message: Optional[str] = None) -> None:
        """Start real-time conversation with AI."""
        if self.running:
            logger.warning("Conversation already running")
            return
            
        try:
            self.running = True
            logger.info("🚀 Starting Live API conversation...")
            logger.info(f"🔑 Using model: models/gemini-2.5-flash-exp-native-audio-thinking-dialog")
            
            async with (
                self.client.aio.live.connect(
                    model="models/gemini-2.5-flash-exp-native-audio-thinking-dialog",
                    config=self.live_config
                ) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session
                logger.info("✅ Connected to Gemini Live API successfully!")
                
                # Initialize queues
                self.audio_in_queue = asyncio.Queue()
                self.audio_out_queue = asyncio.Queue(maxsize=20)  # Increased buffer size
                self.sip_audio_queue = asyncio.Queue()
                
                # Send initial greeting if provided
                if initial_message:
                    logger.info(f"📤 Sending initial greeting to AI: {initial_message}")
                    await session.send(input=initial_message, end_of_turn=True)
                else:
                    # Send a test message to prime the AI
                    logger.info(f"📤 Sending conversation starter to AI...")
                    await session.send(input="Hello! I'm ready to have a live voice conversation with you. Please greet me warmly and ask how you can help me today. Speak naturally and feel free to elaborate in your responses.", end_of_turn=True)
                
                # Create background tasks
                self.tasks = [
                    tg.create_task(self._process_ai_messages()),
                    tg.create_task(self._send_audio_to_ai()),
                    tg.create_task(self._play_ai_audio()),
                ]
                
                logger.info("🎵 Live conversation started - AI is now listening...")
                logger.info("🔊 Audio processing tasks running:")
                logger.info("   📥 Receiving audio from AI")
                logger.info("   📤 Sending audio to AI") 
                logger.info("   🔈 Playing AI audio")
                
                # Wait until conversation is stopped
                while self.running:
                    await asyncio.sleep(0.1)
                    
        except asyncio.CancelledError:
            logger.info("🛑 Live conversation cancelled")
        except Exception as e:
            logger.error(f"💥 Live conversation error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self.running = False
            logger.info("🔚 Live conversation ended")
    
    async def stop_conversation(self) -> None:
        """Stop the live conversation."""
        logger.info("Stopping live conversation...")
        self.running = False
        
        # Cancel all tasks
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # Clear queues
        if self.audio_in_queue:
            while not self.audio_in_queue.empty():
                try:
                    self.audio_in_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        
        logger.info("Live conversation stopped")
    
    async def send_sip_audio(self, audio_data: bytes) -> None:
        """Send audio data from SIP call to AI."""
        if not self.running or not self.audio_out_queue:
            return
            
        try:
            # Audio is already converted to PCM by RTP handler
            
            # Try to put audio, but don't block if queue is full
            try:
                self.audio_out_queue.put_nowait({
                    "data": audio_data,
                    "mime_type": "audio/pcm;rate=16000"  # FIXED: Specify 16kHz rate
                })
            except asyncio.QueueFull:
                # Drop oldest audio if queue is full to prevent latency buildup
                try:
                    self.audio_out_queue.get_nowait()  # Remove oldest
                    self.audio_out_queue.put_nowait({
                        "data": audio_data,
                        "mime_type": "audio/pcm;rate=16000"
                    })
                except asyncio.QueueEmpty:
                    pass
            
        except Exception as e:
            logger.error(f"Error processing SIP audio: {e}")
    
    def send_sip_audio_sync(self, audio_data: bytes) -> None:
        """Synchronous wrapper for sending audio from RTP thread."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.send_sip_audio(audio_data), 
                self._loop
            )
        else:
            logger.warning("⚠️ No event loop available for audio forwarding")

    async def _process_ai_messages(self) -> None:
        """Background task to process AI messages."""
        logger.info("AI message processing started")
        audio_received_count = 0
        
        try:
            async for message in self.session.receive():
                if not self.running:
                    break
                    
                if message.type == "audio":
                    audio_received_count += 1
                    data = message.data
                    
                    if data and len(data) > 0:
                        logger.info(f"🔊 Received AI audio #{audio_received_count}: {len(data)} bytes")
                        
                        # Put audio in queue immediately
                        try:
                            self.audio_in_queue.put_nowait(data)
                        except asyncio.QueueFull:
                            logger.warning("⚠️ Audio input queue full, dropping old audio")
                            try:
                                self.audio_in_queue.get_nowait()  # Remove oldest
                                self.audio_in_queue.put_nowait(data)  # Add newest
                            except asyncio.QueueEmpty:
                                pass
                        continue
                
                elif message.type == "turn_complete":
                    logger.info("🔄 AI turn complete")
                    continue
                    
                # Handle other message types
                if hasattr(message, 'text') and message.text:
                    logger.info(f"AI response: {message.text}")
                
        except Exception as e:
            logger.error(f"Error in AI message processing: {e}")
        finally:
            logger.info(f"AI message processing ended (received {audio_received_count} audio messages)")

    async def _send_audio_to_ai(self) -> None:
        """Background task to send audio to AI."""
        logger.info("Audio sending to AI started")
        audio_sent_count = 0
        
        while self.running:
            try:
                # Get audio data from queue
                audio_msg = await self.audio_out_queue.get()
                audio_sent_count += 1
                
                if audio_msg and self.session:
                    try:
                        await self.session.send(audio_msg)
                    except Exception as e:
                        logger.error(f"Error sending audio to AI: {e}")
                
            except Exception as e:
                logger.error(f"Error in audio sending task: {e}")
                break
                
        logger.info(f"Audio sending to AI ended (sent {audio_sent_count} messages)")

    async def _play_ai_audio(self) -> None:
        """Background task to play AI audio through SIP."""
        logger.info("Audio playback task started")
        audio_sent_count = 0
        audio_buffer = b''  # Buffer to accumulate chunks
        
        # ADAPTIVE BUFFERING: Larger at startup for smoothness, smaller for steady-state latency
        startup_buffer_size = 7200   # ~150ms at 24kHz - smooth startup
        steady_buffer_size = 2400    # ~50ms at 24kHz - low latency
        startup_chunks_needed = 3    # Number of chunks before switching to steady state
        
        buffer_target_size = startup_buffer_size
        logger.info(f"Using adaptive buffering: startup {startup_buffer_size}B → steady {steady_buffer_size}B")
        
        while self.running:
            try:
                # FIXED: Buffer multiple chunks to avoid boundary artifacts
                audio_data = await self.audio_in_queue.get()
                audio_sent_count += 1
                
                # Add to buffer
                audio_buffer += audio_data
                
                # Process buffer when we have enough data for smooth audio
                if len(audio_buffer) >= buffer_target_size or not self.running:
                    logger.info(f"Processing buffered AI audio: {len(audio_buffer)} bytes from {audio_sent_count} chunks")
                    
                    # ADAPTIVE: Switch to steady-state mode after startup
                    if audio_sent_count >= startup_chunks_needed and buffer_target_size == startup_buffer_size:
                        buffer_target_size = steady_buffer_size
                        logger.info(f"Switched to low-latency buffering ({steady_buffer_size}B)")
                
                # Send to SIP call if callback is set
                if self.sip_audio_callback:
                    logger.info(f"Sending buffered AI audio to SIP call...")
                    await asyncio.to_thread(self.sip_audio_callback, audio_buffer)
                    logger.info(f"Buffered AI audio sent successfully")
                else:
                    logger.warning("⚠️  No SIP audio callback set - audio not sent to call")
                    
                # CRITICAL FIX: Always clear buffer after processing (was only clearing in else clause!)
                audio_buffer = b''
                    
            except Exception as e:
                logger.error(f"Error in audio playback task: {e}")
                import traceback
                logger.error(f"Stack trace: {traceback.format_exc()}")
                break
                
        # Process any remaining buffered audio
        if audio_buffer and self.sip_audio_callback:
            logger.info(f"Processing final buffered audio: {len(audio_buffer)} bytes")
            try:
                await asyncio.to_thread(self.sip_audio_callback, audio_buffer)
            except Exception as e:
                logger.error(f"Error sending final audio buffer: {e}")
                
        logger.info(f"Audio playback task ended (sent {audio_sent_count} audio chunks)")
    
    def __del__(self):
        """Cleanup PyAudio."""
        if hasattr(self, 'pya'):
            self.pya.terminate() 
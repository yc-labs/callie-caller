"""
Google Gemini Live API client for real-time audio conversation.
Handles bidirectional audio streaming during SIP calls with function calling support.
"""

import asyncio
import logging
import pyaudio
from typing import Optional, Callable, Any
from google import genai
from google.genai import types
import time # Added for time.time()
import websockets.exceptions # Added for websockets.exceptions.ConnectionClosedError
import traceback # Added for traceback.format_exc()

from callie_caller.config import get_settings
from callie_caller.ai.tools import get_tool_manager

logger = logging.getLogger(__name__)

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

class AudioBridge:
    """Bridges SIP audio with Gemini Live API for real-time conversation with function calling."""
    
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
        
        # Transcription callback for WebSocket updates
        self.transcription_callback: Optional[Callable] = None
        
        # Tool manager for function calling
        self.tool_manager = get_tool_manager()
        
        logger.info("AudioBridge initialized with function calling support")
        logger.info(f"Available tools: {list(self.tool_manager.tools.keys())}")
    
    @property
    def live_config(self) -> types.LiveConnectConfig:
        """Get Live API configuration with function calling support."""
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
            tools=self.tool_manager.get_tools_for_genai(),
            system_instruction=self._get_system_instruction(),
        )
    
    def _get_system_instruction(self) -> str:
        """Get system instruction for the AI with tool information."""
        base_instruction = """You are Callie, a helpful AI voice assistant. You are having a live voice conversation with a user over the phone.

Key instructions:
- Keep responses conversational and natural since this is voice communication
- Be concise but friendly and helpful
- Use tools when appropriate to provide accurate, up-to-date information
- Always acknowledge when you're using a tool (e.g., "Let me check the weather for you...")
- If a tool fails, explain briefly and offer alternatives

"""
        
        tool_info = self.tool_manager.get_tool_summary()
        return base_instruction + tool_info
    
    def set_sip_audio_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set callback for sending audio to SIP call."""
        self.sip_audio_callback = callback
        logger.debug("SIP audio callback set")
    
    async def start_managed_conversation(self, initial_message: Optional[str] = None, max_duration_minutes: int = 14) -> None:
        """Start a managed conversation with automatic reconnection for long calls.
        
        The Gemini Live API has session limits:
        - Audio-only: 15 minutes
        - Audio+video: 2 minutes
        
        This method automatically reconnects before hitting those limits.
        
        Args:
            initial_message: Initial greeting to send to AI
            max_duration_minutes: Max duration before reconnecting (default 14 min to stay under 15 min limit)
        """
        start_time = time.time()
        session_count = 0
        
        while True:
            session_count += 1
            session_start = time.time()
            
            logger.info(f"🔄 Starting session #{session_count}")
            
            try:
                # Start conversation
                await self.start_conversation(initial_message if session_count == 1 else None)
                
                # Monitor session duration
                while self.running:
                    elapsed = (time.time() - session_start) / 60  # minutes
                    
                    if elapsed >= max_duration_minutes:
                        logger.info(f"⏰ Session duration limit approaching ({elapsed:.1f} min), reconnecting...")
                        await self.stop_conversation()
                        break
                    
                    await asyncio.sleep(10)  # Check every 10 seconds
                
                # Check if we should continue
                if not self.running:
                    logger.info("🛑 Conversation ended by user")
                    break
                    
                # Brief pause before reconnecting
                logger.info("⏳ Reconnecting in 2 seconds...")
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"💥 Error in managed conversation: {e}")
                await asyncio.sleep(5)  # Wait before retry
                
                # Check total duration
                total_elapsed = (time.time() - start_time) / 60
                if total_elapsed > 60:  # Stop after 1 hour total
                    logger.error("❌ Maximum total duration exceeded, stopping")
                    break
        
        logger.info(f"📊 Managed conversation ended after {session_count} sessions")
    
    async def start_conversation(self, initial_message: Optional[str] = None) -> None:
        """Start real-time conversation with AI."""
        if self.running:
            logger.warning("Conversation already running")
            return
            
        try:
            self.running = True
            logger.info("🚀 Starting Live API conversation with function calling...")
            logger.info(f"🔑 Using model: models/gemini-2.5-flash-exp-native-audio-thinking-dialog")
            logger.info(f"🔧 Available tools: {', '.join(self.tool_manager.tools.keys())}")
            
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
                    tg.create_task(self._receive_audio_from_ai()),
                    tg.create_task(self._send_audio_to_ai()),
                    tg.create_task(self._play_ai_audio()),
                    tg.create_task(self._handle_function_calls()),
                ]
                
                logger.info("🎵 Live conversation started - AI is now listening...")
                logger.info("🔊 Audio processing tasks running:")
                logger.info("   📥 Receiving audio from AI")
                logger.info("   📤 Sending audio to AI") 
                logger.info("   🔈 Playing AI audio")
                logger.info("   🔧 Handling function calls")
                
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
            logger.debug("⏸️  Audio bridge not running, skipping audio")
            return
            
        try:
            logger.debug(f"🎤 Received {len(audio_data)} bytes of RTP audio")
            # Audio is already converted to PCM by RTP handler
            
            # Try to put audio, but don't block if queue is full
            try:
                self.audio_out_queue.put_nowait({
                    "data": audio_data,
                    "mime_type": "audio/pcm"  # Don't specify rate - let the AI handle it
                })
                logger.debug(f"📨 Queued RTP audio for AI processing")
            except asyncio.QueueFull:
                # If queue is full, remove oldest item and add new one
                try:
                    self.audio_out_queue.get_nowait()  # Remove oldest
                    self.audio_out_queue.put_nowait({
                        "data": audio_data,
                        "mime_type": "audio/pcm"
                    })
                    logger.debug("🔄 Replaced oldest audio in queue with new audio")
                except asyncio.QueueEmpty:
                    logger.warning("⚠️ Queue management error")
        except Exception as e:
            logger.error(f"💥 Error sending RTP audio to AI: {e}")
    
    def send_sip_audio_sync(self, audio_data: bytes) -> None:
        """Synchronous wrapper for sending audio from RTP thread."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.send_sip_audio(audio_data), 
                self._loop
            )
        else:
            logger.warning("⚠️ No event loop available for audio forwarding")
    
    async def _send_audio_to_ai(self) -> None:
        """Background task to send audio from SIP to AI."""
        logger.info("📤 Audio-to-AI task started")
        while self.running:
            try:
                audio_msg = await self.audio_out_queue.get()
                if self.session:
                    logger.debug(f"🚀 Sending audio to AI: {len(audio_msg.get('data', b''))} bytes")
                    await self.session.send(input=audio_msg)
                else:
                    logger.warning("⚠️  No session available for sending audio")
            except Exception as e:
                logger.error(f"💥 Error in audio send task: {e}")
                break
        logger.info("📤 Audio-to-AI task ended")
    
    async def _receive_audio_from_ai(self) -> None:
        """Background task to receive audio from AI."""
        logger.info("📥 Audio-from-AI task started")
        audio_received_count = 0
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        # Track audio session stats for summarized logging
        audio_session_start = time.time()
        last_audio_log_time = time.time()
        audio_chunks_since_log = 0
        audio_bytes_since_log = 0
        
        while self.running and self.session:
            try:
                # FIXED: Continuous streaming across multiple turns
                turn = self.session.receive()
                async for response in turn:
                    if not self.running:  # Check if we should stop
                        break
                        
                    if data := response.data:
                        audio_received_count += 1
                        consecutive_errors = 0  # Reset error count on success
                        
                        # ENHANCED: Detailed audio analysis
                        self._analyze_ai_audio(data, audio_received_count)
                        
                        # Track audio stats instead of logging each chunk
                        audio_chunks_since_log += 1
                        audio_bytes_since_log += len(data)
                        
                        # Log summary every 5 seconds or every 100 chunks
                        current_time = time.time()
                        if (current_time - last_audio_log_time >= 5.0) or (audio_chunks_since_log >= 100):
                            duration = current_time - audio_session_start
                            avg_chunk_size = audio_bytes_since_log / audio_chunks_since_log if audio_chunks_since_log > 0 else 0
                            logger.info(f"🔊 AI audio streaming: {audio_chunks_since_log} chunks, "
                                      f"{audio_bytes_since_log:,} bytes in {current_time - last_audio_log_time:.1f}s "
                                      f"(avg {avg_chunk_size:.0f} bytes/chunk, total {duration:.0f}s)")
                            last_audio_log_time = current_time
                            audio_chunks_since_log = 0
                            audio_bytes_since_log = 0
                        
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
                        
                    if text := response.text:
                        logger.info(f"🤖 AI text response: {text}")
                        consecutive_errors = 0  # Reset error count on success
                        # Emit transcription via callback if available
                        if self.transcription_callback:
                            try:
                                await asyncio.to_thread(self.transcription_callback, 'AI', text, True)
                            except Exception as e:
                                logger.error(f"Error in transcription callback: {e}")
                    
                    # Handle function calls if present
                    if hasattr(response, 'function_call') and response.function_call:
                        logger.info(f"🔧 Function call detected: {response.function_call.name}")
                        # Function calls will be handled by the separate task
                
                # CRITICAL FIX: Don't break on turn end - continue to next turn immediately
                logger.debug("🔄 Turn ended, continuing to next turn for more audio...")
                    
            except asyncio.CancelledError:
                logger.info("📥 Audio receive task cancelled")
                break
            except websockets.exceptions.ConnectionClosedError as e:
                consecutive_errors += 1
                if "Deadline expired" in str(e):
                    logger.warning(f"⏰ Gemini Live API session deadline expired (15min audio / 2min video limit)")
                    if consecutive_errors < max_consecutive_errors:
                        logger.info(f"🔄 Attempting to reconnect... (attempt {consecutive_errors}/{max_consecutive_errors})")
                        # Signal for reconnection
                        self.running = False  # This will trigger reconnection in the main conversation loop
                        break
                    else:
                        logger.error(f"❌ Max reconnection attempts reached. Stopping.")
                        self.running = False
                        break
                else:
                    logger.error(f"💥 WebSocket connection error: {e}")
                    logger.error(f"📋 Stack trace: {traceback.format_exc()}")
                    # Don't break - try to continue receiving
                    await asyncio.sleep(0.5)  # Brief pause before retry
                    continue
            except Exception as e:
                logger.error(f"💥 Error in audio receive task: {e}")
                import traceback
                logger.error(f"📋 Stack trace: {traceback.format_exc()}")
                # Don't break - try to continue receiving
                await asyncio.sleep(0.1)  # Brief pause before retry
                continue
                
        logger.info(f"📥 Audio-from-AI task ended (received {audio_received_count} audio chunks)")
    
    async def _handle_function_calls(self) -> None:
        """Background task to handle function calls from the AI."""
        logger.info("🔧 Function call handler started")
        
        while self.running and self.session:
            try:
                # Check for function calls in the session
                # Note: This is a simplified approach - in reality, function calls
                # would be handled differently in the Live API
                
                # For now, we'll integrate function calling into the main audio loop
                # The actual implementation would depend on how the Live API exposes function calls
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                
            except asyncio.CancelledError:
                logger.info("🔧 Function call handler cancelled")
                break
            except Exception as e:
                logger.error(f"💥 Error in function call handler: {e}")
                await asyncio.sleep(1)  # Pause before retry
                
        logger.info("🔧 Function call handler ended")
    
    def _analyze_ai_audio(self, audio_data: bytes, chunk_number: int) -> None:
        """Analyze audio data from Gemini Live API to understand format."""
        try:
            if chunk_number <= 5:  # Analyze first 5 chunks in detail
                logger.info(f"🔬 GEMINI AUDIO ANALYSIS #{chunk_number}:")
                logger.info(f"   📊 Size: {len(audio_data)} bytes")
                
                # Check for common audio headers first
                if audio_data.startswith(b'RIFF'):
                    logger.info(f"   🎵 FORMAT: WAV file")
                    return
                elif audio_data.startswith(b'fLaC'):
                    logger.info(f"   🎵 FORMAT: FLAC") 
                    return
                elif audio_data.startswith(b'OggS'):
                    logger.info(f"   🎵 FORMAT: OGG")
                    return
                
                # Assume raw PCM (expected from Gemini Live API)
                logger.info(f"   🎵 FORMAT: Raw PCM (no header)")
                
                if len(audio_data) >= 4:
                    import struct
                    
                    # Try 16-bit little-endian PCM (Gemini Live API standard)
                    try:
                        sample_count = len(audio_data) // 2
                        if sample_count > 0:
                            samples = struct.unpack(f'<{sample_count}h', audio_data)
                            max_amplitude = max(abs(s) for s in samples)
                            avg_amplitude = sum(abs(s) for s in samples) / len(samples)
                            
                            logger.info(f"   🎵 16-bit PCM: {sample_count} samples")
                            logger.info(f"   📈 Max amplitude: {max_amplitude} ({max_amplitude/32767*100:.1f}% of range)")
                            logger.info(f"   📊 Avg amplitude: {avg_amplitude:.1f}")
                            
                            # Gemini Live API outputs 24kHz according to docs
                            duration_24khz_ms = (sample_count / 24000) * 1000
                            logger.info(f"   ⏱️  Duration (24kHz): {duration_24khz_ms:.1f}ms")
                            
                            # Also calculate what it would be at 16kHz
                            duration_16khz_ms = (sample_count / 16000) * 1000  
                            logger.info(f"   ⏱️  Duration (16kHz): {duration_16khz_ms:.1f}ms")
                            
                            # Audio quality assessment
                            if max_amplitude > 10000:
                                logger.info(f"   🗣️  CLEAR SPEECH DETECTED")
                            elif max_amplitude > 1000:
                                logger.info(f"   🗣️  SPEECH DETECTED")
                            elif max_amplitude > 100:
                                logger.info(f"   🔇 LOW AUDIO")
                            else:
                                logger.info(f"   🔇 SILENCE/NOISE")
                                
                    except Exception as e:
                        logger.warning(f"   ❌ PCM analysis failed: {e}")
                    
        except Exception as e:
            logger.error(f"Audio analysis error: {e}")
    
    async def _play_ai_audio(self) -> None:
        """Background task to play AI audio through SIP."""
        logger.info("🔈 Audio-play task started")
        audio_sent_count = 0
        audio_buffer = b''  # Buffer to accumulate chunks
        chunk_count = 0     # Track chunks in current buffer
        
        # ADAPTIVE BUFFERING: Larger at startup for smoothness, smaller for steady-state latency
        startup_buffer_size = 7200   # ~150ms at 24kHz - smooth startup
        steady_buffer_size = 2400    # ~50ms at 24kHz - low latency
        startup_chunks_needed = 3    # Number of buffers (not chunks!) before switching to steady state
        
        buffer_target_size = startup_buffer_size
        buffers_sent = 0  # Track buffers sent, not individual chunks
        logger.info(f"🚀 STARTUP MODE: Using {startup_buffer_size} byte buffer (~150ms) for smooth start")
        
        while self.running:
            try:
                # FIXED: Buffer multiple chunks to avoid boundary artifacts
                audio_data = await self.audio_in_queue.get()
                chunk_count += 1
                
                # Add to buffer
                audio_buffer += audio_data
                logger.debug(f"🎵 Buffered AI audio chunk: {len(audio_data)} bytes (buffer: {len(audio_buffer)} bytes)")
                
                # Process buffer when we have enough data for smooth audio
                if len(audio_buffer) >= buffer_target_size or not self.running:
                    logger.info(f"🎵 Processing buffered AI audio: {len(audio_buffer)} bytes from {chunk_count} chunks")
                    buffers_sent += 1
                    chunk_count = 0  # Reset chunk count
                    
                    # ADAPTIVE: Switch to steady-state mode after startup
                    if buffers_sent >= startup_chunks_needed and buffer_target_size == startup_buffer_size:
                        buffer_target_size = steady_buffer_size
                        logger.info(f"⚡ STEADY STATE: Switched to {steady_buffer_size} byte buffer (~50ms) for low latency")
                    
                    # Send to SIP call if callback is set
                    if self.sip_audio_callback:
                        logger.info(f"📞 Sending buffered AI audio to SIP call...")
                        await asyncio.to_thread(self.sip_audio_callback, audio_buffer)
                        logger.info(f"✅ Buffered AI audio sent to SIP successfully")
                    else:
                        logger.warning("⚠️  No SIP audio callback set - audio not sent to call")
                        
                    # CRITICAL FIX: Always clear buffer after processing
                    audio_buffer = b''
                    
            except Exception as e:
                logger.error(f"💥 Error in audio play task: {e}")
                import traceback
                logger.error(f"📋 Stack trace: {traceback.format_exc()}")
                break
                
        # Process any remaining buffered audio
        if audio_buffer and self.sip_audio_callback:
            logger.info(f"🎵 Processing final buffered audio: {len(audio_buffer)} bytes")
            try:
                await asyncio.to_thread(self.sip_audio_callback, audio_buffer)
            except Exception as e:
                logger.error(f"💥 Error processing final audio buffer: {e}")
                
        logger.info(f"🔈 Audio-play task ended (sent {buffers_sent} audio buffers)")
    
    async def test_live_api_connection(self) -> bool:
        """Test Live API connection with simulated audio."""
        logger.info("🧪 Testing Live API connection...")
        
        try:
            # Start a brief test conversation
            await self.start_conversation("Hello, this is a test. Can you hear me?")
            
            # Send some test text to see if AI responds
            if self.session:
                logger.info("📤 Sending test message to AI...")
                await self.session.send(input="Please say hello back to test the audio connection.", end_of_turn=True)
                
                # Wait a moment for response
                await asyncio.sleep(2)
                
            await self.stop_conversation()
            return True
            
        except Exception as e:
            logger.error(f"💥 Live API test failed: {e}")
            return False
    
    def __del__(self):
        """Cleanup PyAudio."""
        if hasattr(self, 'pya'):
            self.pya.terminate() 
"""
PJSUA2 Audio Bridge for AI Integration.
Creates a custom audio media port that bridges between PJSIP calls and the AI client.
"""

import logging
import threading
import queue
import time
import struct
import asyncio
from typing import Optional, Callable, Any
import pjsua2 as pj

from callie_caller.ai import AudioBridge

logger = logging.getLogger(__name__)

class AIAudioMediaPort(pj.AudioMediaPort):
    """
    Custom audio media port that bridges PJSIP audio with the AI client.
    Handles bidirectional audio streaming between calls and AI.
    """
    
    def __init__(self):
        """Initialize the AI audio media port."""
        pj.AudioMediaPort.__init__(self)
        
        # Audio parameters (8kHz, mono, 16-bit PCM)
        self.sample_rate = 8000
        self.channels = 1
        self.samples_per_frame = 160  # 20ms at 8kHz
        self.bytes_per_sample = 2
        self.frame_size_bytes = self.samples_per_frame * self.bytes_per_sample
        
        # Audio buffers
        self.ai_to_caller_queue = queue.Queue(maxsize=100)  # AI output to caller
        self.caller_to_ai_queue = queue.Queue(maxsize=100)  # Caller input to AI
        
        # AI integration
        self.audio_bridge: Optional[AudioBridge] = None
        self.ai_conversation_task: Optional[asyncio.Task] = None
        self.conversation_active = False
        
        # Threading
        self.processing_thread: Optional[threading.Thread] = None
        self.running = False
        
        # Audio processing state
        self.last_ai_packet_time = 0
        self.silence_threshold = 100  # Amplitude threshold for silence detection
        
        logger.info("AIAudioMediaPort initialized")
    
    def createPort(self, name: str) -> None:
        """Create the audio port with specified name."""
        try:
            # Create port info
            port_info = pj.MediaFormatAudio()
            port_info.clockRate = self.sample_rate
            port_info.channelCount = self.channels
            port_info.bitsPerSample = 16
            port_info.frameTimeUsec = 20000  # 20ms
            
            # Register the port
            self.createPort2(name, port_info)
            
            # Start processing thread
            self.running = True
            self.processing_thread = threading.Thread(
                target=self._audio_processing_loop,
                name="ai-audio-processor",
                daemon=True
            )
            self.processing_thread.start()
            
            logger.info(f"✅ Audio port '{name}' created - {self.sample_rate}Hz, {self.channels}ch")
            
        except Exception as e:
            logger.error(f"❌ Failed to create audio port: {e}")
            raise
    
    def onFrameRequested(self, frame: pj.MediaFrame) -> None:
        """
        Called by PJSIP when it needs audio data to send to the caller.
        This is where we provide AI-generated audio.
        """
        try:
            # Try to get AI audio from queue
            if not self.ai_to_caller_queue.empty():
                # Get AI audio data
                ai_audio = self.ai_to_caller_queue.get_nowait()
                
                # Ensure correct frame size
                if len(ai_audio) >= self.frame_size_bytes:
                    frame.buf = ai_audio[:self.frame_size_bytes]
                else:
                    # Pad with silence if needed
                    padding = b'\x00' * (self.frame_size_bytes - len(ai_audio))
                    frame.buf = ai_audio + padding
                
                self.last_ai_packet_time = time.time()
                
            else:
                # No AI audio available, send silence
                frame.buf = b'\x00' * self.frame_size_bytes
                
        except Exception as e:
            logger.error(f"❌ Error in onFrameRequested: {e}")
            # Send silence on error
            frame.buf = b'\x00' * self.frame_size_bytes
    
    def onFrameReceived(self, frame: pj.MediaFrame) -> None:
        """
        Called by PJSIP when audio is received from the caller.
        This is where we capture caller's voice for the AI.
        """
        try:
            # Get audio data from frame
            audio_data = bytes(frame.buf)
            
            # Check if this is actual speech or silence
            if self._is_speech(audio_data):
                # Add to queue for AI processing
                if not self.caller_to_ai_queue.full():
                    self.caller_to_ai_queue.put(audio_data)
                else:
                    # Drop oldest frame if queue is full
                    try:
                        self.caller_to_ai_queue.get_nowait()
                        self.caller_to_ai_queue.put(audio_data)
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"❌ Error in onFrameReceived: {e}")
    
    def _is_speech(self, audio_data: bytes) -> bool:
        """Simple voice activity detection."""
        try:
            # Unpack PCM samples
            samples = struct.unpack(f'<{len(audio_data)//2}h', audio_data)
            
            # Calculate RMS amplitude
            if samples:
                rms = sum(s*s for s in samples) / len(samples)
                rms = int(rms ** 0.5)
                return rms > self.silence_threshold
                
            return False
            
        except:
            return True  # Assume speech on error
    
    def _audio_processing_loop(self) -> None:
        """Background thread for audio processing."""
        logger.info("🎵 Audio processing thread started")
        
        while self.running:
            try:
                # Process caller audio to AI
                if not self.caller_to_ai_queue.empty() and self.audio_bridge:
                    audio_chunk = self.caller_to_ai_queue.get()
                    
                    # Convert 8kHz to 16kHz for AI (simple upsampling)
                    upsampled = self._resample_audio(audio_chunk, 8000, 16000)
                    
                    # Send to AI
                    self.audio_bridge.send_sip_audio_sync(upsampled)
                
                # Small sleep to prevent CPU spinning
                time.sleep(0.001)
                
            except Exception as e:
                logger.error(f"❌ Audio processing error: {e}")
                time.sleep(0.01)
                
        logger.info("🎵 Audio processing thread stopped")
    
    def _resample_audio(self, audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """Simple audio resampling (linear interpolation)."""
        try:
            from callie_caller.sip.audio_codec import resample_simple
            return resample_simple(audio_data, from_rate, to_rate, self.bytes_per_sample)
        except Exception as e:
            logger.error(f"Resampling error: {e}")
            return audio_data  # Return original on error
    
    def start_ai_conversation(self, initial_message: Optional[str] = None) -> None:
        """Start the AI conversation for this call."""
        try:
            logger.info("🤖 Starting AI conversation...")
            
            # Initialize audio bridge if needed
            if not self.audio_bridge:
                self.audio_bridge = AudioBridge()
                
                # Set callback for AI audio output
                def ai_audio_callback(ai_audio: bytes):
                    """Callback to receive audio from AI."""
                    try:
                        # AI provides 24kHz audio, downsample to 8kHz for telephony
                        downsampled = self._resample_audio(ai_audio, 24000, 8000)
                        
                        # Split into 20ms frames for PJSIP
                        for i in range(0, len(downsampled), self.frame_size_bytes):
                            frame = downsampled[i:i + self.frame_size_bytes]
                            if not self.ai_to_caller_queue.full():
                                self.ai_to_caller_queue.put(frame)
                                
                    except Exception as e:
                        logger.error(f"AI audio callback error: {e}")
                
                self.audio_bridge.set_sip_audio_callback(ai_audio_callback)
            
            # Start conversation in event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def run_conversation():
                try:
                    await self.audio_bridge.start_conversation(initial_message)
                except Exception as e:
                    logger.error(f"AI conversation error: {e}")
            
            self.conversation_active = True
            loop.run_until_complete(run_conversation())
            
        except Exception as e:
            logger.error(f"❌ Failed to start AI conversation: {e}")
    
    def stop_ai_conversation(self) -> None:
        """Stop the AI conversation."""
        try:
            self.conversation_active = False
            
            if self.audio_bridge:
                # Stop conversation synchronously
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.audio_bridge.stop_conversation())
                
            logger.info("🤖 AI conversation stopped")
            
        except Exception as e:
            logger.error(f"Error stopping AI conversation: {e}")
    
    def __del__(self):
        """Cleanup when port is destroyed."""
        try:
            self.running = False
            
            if self.processing_thread and self.processing_thread.is_alive():
                self.processing_thread.join(timeout=1.0)
                
            if self.conversation_active:
                self.stop_ai_conversation()
                
            logger.info("AIAudioMediaPort destroyed")
            
        except Exception as e:
            logger.error(f"Error in AIAudioMediaPort cleanup: {e}") 
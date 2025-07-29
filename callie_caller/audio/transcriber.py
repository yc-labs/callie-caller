"""Real-time audio transcriber using Google Cloud Speech-to-Text."""
import logging
import queue
import threading
import time
from typing import Optional, Callable
import numpy as np

try:
    import speech_recognition as sr
except ImportError:
    sr = None
    logging.warning("speech_recognition not installed - transcription disabled")

logger = logging.getLogger(__name__)


class AudioTranscriber:
    """Transcribes audio in real-time using Google Speech Recognition."""
    
    def __init__(self, transcription_callback: Optional[Callable[[str, str, bool], None]] = None):
        """Initialize the transcriber.
        
        Args:
            transcription_callback: Function to call with (speaker, text, is_final)
        """
        self.transcription_callback = transcription_callback
        self.running = False
        self.processing_thread = None
        self.total_chunks_received = 0
        self.last_chunk_log_time = time.time()
        
        # Timing
        self.chunk_duration = 0.1  # 100ms chunks
        self.min_speech_duration = 0.5  # 500ms minimum speech
        self.silence_threshold = 1.0  # 1 second silence before processing
        
        # Audio buffers
        self.audio_queue = queue.Queue()
        self.caller_buffer = []
        self.ai_buffer = []
        self.buffer_lock = threading.Lock()
        
        # Last processing times
        self.last_caller_process = 0
        self.last_ai_process = 0
        
        # Processing queue for accumulated audio
        self.processing_queue = queue.Queue()
        
        # Initialize recognizer if available
        self.recognizer = sr.Recognizer() if sr else None
        
    def start(self):
        """Start the transcription thread."""
        if not sr:
            logger.warning("speech_recognition not available - transcription disabled")
            return
            
        self.running = True
        self.processing_thread = threading.Thread(target=self._process_audio_chunks, daemon=True)
        self.processing_thread.start()
        logger.info("✅ Audio transcriber started")
        
    def stop(self):
        """Stop the transcription thread."""
        self.running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=2.0)
        logger.info("🛑 Audio transcriber stopped")
        
    def add_audio_chunk(self, audio_data: bytes, is_caller: bool = True, sample_rate: int = 16000):
        """Add an audio chunk for transcription.
        
        Args:
            audio_data: PCM audio data (16-bit)
            is_caller: True if from caller, False if from AI
            sample_rate: Sample rate of the audio (AI uses 24kHz, caller uses 16kHz)
        """
        if not self.running:
            logger.warning("Transcriber not running, ignoring audio chunk")
            return
        
        # Log the first few chunks for debugging
        if not hasattr(self, '_chunks_logged'):
            self._chunks_logged = 0
        if self._chunks_logged < 5:
            logger.info(f"📝 Transcriber received {len(audio_data)} bytes from {'caller' if is_caller else 'AI'} at {sample_rate}Hz")
            self._chunks_logged += 1
            
        self.total_chunks_received += 1
        
        # Log every 5 seconds
        current_time = time.time()
        if current_time - self.last_chunk_log_time > 5:
            logger.info(f"📝 Transcriber status: {self.total_chunks_received} total chunks received, queue size: {self.audio_queue.qsize()}")
            self.last_chunk_log_time = current_time
            
        # AI audio is 24kHz, need to resample to 16kHz for speech recognition
        if not is_caller and sample_rate == 24000:
            try:
                # Simple downsample by taking every 3rd sample out of 2
                # This is not ideal but works for speech
                samples = np.frombuffer(audio_data, dtype=np.int16)
                # Resample from 24kHz to 16kHz (2:3 ratio)
                resampled = samples[::3] * 2  # Take every 3rd sample
                audio_data = resampled.astype(np.int16).tobytes()
            except Exception as e:
                logger.error(f"Error resampling audio: {e}")
                return
        
        # Add to appropriate buffer
        with self.buffer_lock:
            if is_caller:
                self.caller_buffer.append(audio_data)
            else:
                self.ai_buffer.append(audio_data)
        
        # Check if we should process accumulated audio
        current_time = time.time()
        
        # Process if we have enough audio and some silence
        if is_caller and current_time - self.last_caller_process > self.silence_threshold:
            if len(self.caller_buffer) * self.chunk_duration > self.min_speech_duration:
                self._queue_for_processing(True)
                self.last_caller_process = current_time
                
        elif not is_caller and current_time - self.last_ai_process > self.silence_threshold:
            if len(self.ai_buffer) * self.chunk_duration > self.min_speech_duration:
                self._queue_for_processing(False)
                self.last_ai_process = current_time
    
    def _queue_for_processing(self, is_caller: bool):
        """Queue accumulated audio for processing."""
        with self.buffer_lock:
            if is_caller and self.caller_buffer:
                # Combine all chunks
                combined_audio = b''.join(self.caller_buffer)
                self.caller_buffer.clear()
                self.processing_queue.put(('caller', combined_audio))
                logger.debug(f"📝 Queued {len(combined_audio)} bytes of caller audio for processing")
            elif not is_caller and self.ai_buffer:
                # Combine all chunks
                combined_audio = b''.join(self.ai_buffer)
                self.ai_buffer.clear()
                self.processing_queue.put(('AI', combined_audio))
                logger.debug(f"📝 Queued {len(combined_audio)} bytes of AI audio for processing")
    
    def _process_audio_chunks(self):
        """Background thread to process audio chunks."""
        logger.info("🎙️ Transcription processing thread started")
        chunks_processed = 0
        
        while self.running:
            try:
                # Get next chunk to process
                speaker, audio_data = self.processing_queue.get(timeout=0.5)
                
                chunks_processed += 1
                logger.info(f"🎙️ Processing chunk #{chunks_processed} from {speaker}: {len(audio_data)} bytes")
                
                # Skip if too short
                if len(audio_data) < 3200:  # Less than 100ms at 16kHz
                    logger.debug(f"Skipping short audio chunk: {len(audio_data)} bytes")
                    continue
                
                # Convert to AudioData for speech recognition
                try:
                    # Create AudioData object
                    audio = sr.AudioData(audio_data, 16000, 2)
                    
                    # Transcribe
                    try:
                        logger.info(f"🎙️ Sending {speaker} audio to Google Speech Recognition...")
                        text = self.recognizer.recognize_google(audio)
                        if text and self.transcription_callback:
                            logger.info(f"📝 Transcribed ({speaker}): {text}")
                            self.transcription_callback(speaker, text, True)
                        else:
                            logger.debug(f"No text recognized from {speaker} audio")
                    except sr.UnknownValueError:
                        # Could not understand audio
                        logger.debug(f"Could not understand {speaker} audio")
                        pass
                    except sr.RequestError as e:
                        logger.error(f"Speech recognition error: {e}")
                        
                except Exception as e:
                    logger.error(f"Error processing audio: {e}")
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in transcription thread: {e}")
                if not self.running:
                    break
        
        logger.info("🎙️ Transcription processing thread ended") 
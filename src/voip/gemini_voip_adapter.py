# callie_caller/voip/gemini_voip_adapter.py
import os
import time
import threading
import asyncio
import struct
import audioop
import logging
from typing import Optional

from ai.conversation import ConversationManager

from ai.live_client import AudioBridge  # your existing Gemini Live client

logger = logging.getLogger(__name__)

DEFAULT_GEMINI_OUT_RATE = int(os.getenv("GEM_OUT_RATE", "24000"))  # Gemini -> SIP (typical 24k)
DEFAULT_GEMINI_IN_RATE  = int(os.getenv("GEM_IN_RATE",  "16000"))  # SIP -> Gemini

def resample_pcm16(pcm_bytes, src_rate, dst_rate):
    """Resample mono 16-bit PCM using stdlib audioop."""
    if not pcm_bytes or src_rate == dst_rate:
        return pcm_bytes
    converted, _ = audioop.ratecv(pcm_bytes, 2, 1, src_rate, dst_rate, None)
    return converted

def _read_wav_fifo_stream_with_rate(fifo_path: str):
    """
    Open WAV-structured FIFO and return (rate_hz, generator-of-PCM-frames).
    Parses header (16-bit mono PCM). Returns ~20ms chunks at source rate.
    """
    logger.info(f"Opening RX FIFO for reading: {fifo_path}")
    f = open(fifo_path, "rb", buffering=0)

    header = f.read(44)
    if len(header) < 44:
        f.close()
        raise RuntimeError("FIFO closed before WAV header completed")

    rate_hz = struct.unpack("<I", header[24:28])[0]
    channels = struct.unpack("<H", header[22:24])[0]
    bits = struct.unpack("<H", header[34:36])[0]
    if channels != 1 or bits != 16:
        logger.warning(f"WAV format unexpected: channels={channels}, bits={bits}; continuing")
    logger.info(f"WAV FIFO reports sample rate: {rate_hz} Hz")

    def frames():
        # 20 ms chunk size at detected rate
        chunk_bytes = max(2, int(rate_hz * 0.02) * 2)
        while True:
            b = f.read(chunk_bytes)
            if not b:
                break
            yield b
        f.close()

    return rate_hz, frames()

class GeminiVoipAdapter:
    """
    Wires your AudioBridge (Gemini Live) to the PJSIP VoipClient.
    - SIP -> Gemini: read PCM from FIFO (true call rate), resample to gem_in_rate (e.g., 16k), send to AudioBridge
    - Gemini -> SIP: AudioBridge callback provides PCM (e.g., 24k), resample to call rate via voip.enqueue_pcm
    """
    def __init__(
        self,
        voip_client,
        target_number: str,
        rx_fifo_path: str = "/tmp/sip_rx.wavpipe",
        gem_out_rate: int = DEFAULT_GEMINI_OUT_RATE,
        gem_in_rate: int = DEFAULT_GEMINI_IN_RATE,
        initial_message: Optional[str] = None,
        max_session_minutes: int = 14,
        call_context: Optional[str] = None,
        conversation_manager: Optional[ConversationManager] = None,
    ):
        self.voip = voip_client
        self.target = target_number
        self.rx_fifo = rx_fifo_path
        self.gem_out_rate = gem_out_rate
        self.gem_in_rate = gem_in_rate
        self.initial_message = initial_message
        self.max_session_minutes = max_session_minutes
        self.call_context = call_context

        self._stop = threading.Event()
        self._running = True  # Track if adapter is running
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._fifo_thread: Optional[threading.Thread] = None
        self._loop_ready = threading.Event()  # Signal when event loop is ready

        self._bridge = AudioBridge(
            phone_number=self.target,
            call_context=self.call_context,
            voip_adapter=self,
            conversation_manager=conversation_manager,
        )

    # ---------- Event loop (Gemini) ----------

    def _loop_worker(self):
        # This thread never calls pjsua2; don't touch pjlib here.
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._bridge._loop = self._loop  # Set the loop reference in bridge
        self._loop_ready.set()  # Signal that the loop is ready
        logger.info(f"Starting Gemini conversation with initial message: {self.initial_message}")
        try:
            self._loop.run_until_complete(
                self._bridge.start_managed_conversation(
                    initial_message=self.initial_message,
                    max_duration_minutes=self.max_session_minutes,
                )
            )
        except Exception as e:
            logger.error(f"Error starting conversation: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                self._loop.run_until_complete(self._bridge.stop_conversation())
            except Exception:
                pass
            try:
                pending = asyncio.all_tasks(self._loop)
                for t in pending:
                    t.cancel()
                self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            self._loop.close()
            self._loop = None

    # ---------- FIFO reader (SIP -> Gemini) ----------

    def _fifo_reader(self):
        # This thread also doesn't call pjsua2; no pj thread registration needed.
        """
        Read PCM from VoIP recorder FIFO, resample to gem_in_rate, and forward to Gemini via AudioBridge.
        Uses send_sip_audio_sync to avoid manual futures.
        """
        # Wait for PJSUA to create the recorder file
        retry_count = 0
        while retry_count < 50:  # 5 seconds max
            if os.path.exists(self.rx_fifo):
                break
            time.sleep(0.1)
            retry_count += 1
        
        if not os.path.exists(self.rx_fifo):
            logger.error("RX FIFO was never created by recorder")
            return
        
        try:
            src_rate_hz, frames_iter = _read_wav_fifo_stream_with_rate(self.rx_fifo)
        except Exception as e:
            logger.error(f"FIFO open error: {e}")
            return

        for pcm_src in frames_iter:
            if self._stop.is_set():
                break
            try:
                pcm_dst = resample_pcm16(pcm_src, src_rate_hz, self.gem_in_rate)
                self._bridge.send_sip_audio_sync(pcm_dst)
            except Exception as e:
                logger.error(f"SIP->Gemini error: {e}")
                time.sleep(0.01)

    def _wav_file_reader(self):
        """
        Read PCM from WAV file being written by PJSUA, resample and forward to Gemini.
        """
        # Wait for WAV file to be created with initial data
        logger.info(f"Waiting for WAV file: {self.rx_wav_file}")
        for _ in range(200):  # Wait up to 20 seconds for call to connect
            if os.path.exists(self.rx_wav_file):
                try:
                    size = os.path.getsize(self.rx_wav_file)
                    if size > 44:  # Has more than just header
                        logger.info(f"WAV file created, size: {size} bytes")
                        break
                except Exception:
                    pass
            time.sleep(0.1)
        else:
            logger.error("WAV file not created in time")
            return

        logger.info(f"Starting WAV reader for {self.rx_wav_file}")
        
        # Read WAV header to get sample rate
        try:
            with open(self.rx_wav_file, "rb") as f:
                # Skip to sample rate field in WAV header
                f.seek(24)
                sample_rate = int.from_bytes(f.read(4), 'little')
                logger.info(f"WAV file sample rate: {sample_rate} Hz")
        except Exception as e:
            logger.error(f"Error reading WAV header: {e}")
            sample_rate = 8000  # Assume 8kHz default
        
        file_pos = 44  # Skip WAV header
        buffer = b""
        
        try:
            while self._running:
                try:
                    # Check current file size
                    current_size = os.path.getsize(self.rx_wav_file)
                    
                    # If we have new data to read
                    if current_size > file_pos:
                        with open(self.rx_wav_file, "rb") as f:
                            f.seek(file_pos)
                            # Read all available new data
                            new_data = f.read(current_size - file_pos)
                            if new_data:
                                file_pos = current_size
                                buffer += new_data
                                
                                # Process complete frames (2 bytes per sample)
                                frame_size = 2
                                # For 8kHz input, use 80 samples (10ms)
                                chunk_samples = 80 if sample_rate == 8000 else 160
                                chunk_bytes = chunk_samples * frame_size
                                
                                # Process all complete chunks in buffer
                                chunks_sent = 0
                                while len(buffer) >= chunk_bytes:
                                    pcm_chunk = buffer[:chunk_bytes]
                                    buffer = buffer[chunk_bytes:]
                                    
                                    # Resample if needed
                                    if sample_rate != self.gem_in_rate:
                                        pcm_chunk = resample_pcm16(pcm_chunk, sample_rate, self.gem_in_rate)
                                    
                                    # Send to Gemini
                                    self._bridge.send_sip_audio_sync(pcm_chunk)
                                    chunks_sent += 1
                                
                                if chunks_sent > 0:
                                    logger.debug(f"Sent {chunks_sent} chunks ({chunks_sent * len(pcm_chunk)} bytes) to Gemini")
                    else:
                        # No new data, wait a bit
                        time.sleep(0.01)
                        
                except Exception as e:
                    logger.error(f"Read error: {e}")
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Reader error: {e}")
        finally:
            logger.info("Reader thread exiting")

    # ---------- Public orchestration ----------

    def hangup_call(self):
        """Hang up the call."""
        self.voip.hangup_call()

    def start(self):
        """
        Start the Gemini loop thread and the FIFO reader thread,
        then place the SIP call and block until it ends.
        """
        # Gemini -> SIP: set callback. AudioBridge will call this with 24k PCM by default.
        def sip_audio_callback(ai_pcm: bytes):
            if not ai_pcm:
                return
            logger.debug(f"sip_audio_callback called with {len(ai_pcm)} bytes")
            
            # Debug: Analyze the audio from Gemini
            if len(ai_pcm) >= 100:
                import struct
                samples = struct.unpack(f'{50}h', ai_pcm[:100])  # First 50 samples
                max_sample = max(abs(s) for s in samples)
                avg_sample = sum(abs(s) for s in samples) / len(samples)
                logger.debug(f"Gemini audio: max_sample={max_sample}, avg_sample={avg_sample:.1f}")
                if max_sample < 100:
                    logger.warning("Gemini is sending silent audio!")
            
            try:
                # Resample to the actual call rate inside voip.enqueue_pcm (adaptive)
                self.voip.enqueue_pcm(ai_pcm, self.gem_out_rate)
            except Exception as e:
                logger.error(f"Gemini->SIP enqueue error: {e}")

        self._bridge.set_sip_audio_callback(sip_audio_callback)

        # Create a unique WAV file name to avoid conflicts
        import tempfile
        fd, self.rx_wav_file = tempfile.mkstemp(suffix='.wav', prefix='sip_rx_', dir='/tmp')
        os.close(fd)
        os.unlink(self.rx_wav_file)  # Delete it so PJSUA can create it fresh
        
        # Enable recording to WAV file
        self.voip.enable_rx_fifo(self.rx_wav_file)

        # Initialize VoIP first
        self.voip.initialize()

        # Start audio processing threads first (they'll wait for audio)
        self._loop_thread = threading.Thread(target=self._loop_worker, name="gemini-live-loop", daemon=True)
        self._loop_thread.start()

        # Start WAV file reader
        self._fifo_thread = threading.Thread(target=self._wav_file_reader, name="sip-wav-reader", daemon=True)
        self._fifo_thread.start()

        # Wait for the event loop to be ready
        logger.info("Waiting for Gemini event loop to initialize...")
        if not self._loop_ready.wait(timeout=10):
            logger.error("Gemini event loop failed to initialize in time")
            raise RuntimeError("Event loop initialization timeout")
        
        # Give a brief moment for everything to stabilize
        logger.info("Waiting 0.5 seconds before placing call...")
        time.sleep(0.5)

        # Place SIP call and block until it ends
        try:
            logger.info(f"Placing call to {self.target}...")
            self.voip.dial(self.target, max_duration_sec=3600)  # sessions auto-rotate inside AudioBridge
        finally:
            # Stop everything
            self._stop.set()
            self._running = False  # Stop the WAV reader thread
            try:
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(self._bridge.stop_conversation(), self._loop)
            except Exception:
                pass

            # Let threads wind down (daemon threads will exit with process)
            try:
                if hasattr(self, '_fifo_thread') and self._fifo_thread:
                    self._fifo_thread.join(timeout=0.5)
            except Exception:
                pass
            try:
                if self._loop_thread:
                    self._loop_thread.join(timeout=0.5)
            except Exception:
                pass

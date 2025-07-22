"""
RTP Bridge for bidirectional audio forwarding and AI integration.
Acts as a media proxy to capture and forward audio streams.
"""

import socket
import threading
import time
import logging
import os
import atexit
import struct
import wave
from dataclasses import dataclass
from typing import Optional, Callable, Any
from .sdp import AudioParams

logger = logging.getLogger(__name__)

@dataclass
class AudioEndpoint:
    """Represents an audio endpoint for RTP forwarding."""
    ip: str
    port: int
    socket: Optional[Any] = None

class WavRecorder:
    """Helper class for recording audio to WAV files."""
    
    def __init__(self, filename: str, sample_rate: int = 8000, channels: int = 1, sample_width: int = 2):
        self.filename = filename
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self.wav_file = None
        self.packets_written = 0
        
    def open(self):
        """Open the WAV file for writing."""
        try:
            self.wav_file = wave.open(self.filename, 'wb')
            self.wav_file.setnchannels(self.channels)
            self.wav_file.setsampwidth(self.sample_width)
            self.wav_file.setframerate(self.sample_rate)
            logger.info(f"🎵 Opened WAV file: {self.filename} ({self.sample_rate}Hz, {self.channels}ch)")
        except Exception as e:
            logger.error(f"❌ Failed to open WAV file {self.filename}: {e}")
            
    def write_rtp_packet(self, rtp_data: bytes) -> bool:
        """Decode RTP packet and write PCM audio to WAV file."""
        try:
            if not self.wav_file or len(rtp_data) < 12:
                return False
                
            # Parse RTP header to get payload
            payload_type = rtp_data[1] & 0x7F
            payload = rtp_data[12:]  # Skip 12-byte RTP header
            
            if not payload:
                return False
                
            # Convert RTP payload to PCM
            pcm_data = self._convert_rtp_payload_to_pcm(payload, payload_type)
            if pcm_data:
                self.wav_file.writeframes(pcm_data)
                self.packets_written += 1
                return True
                
        except Exception as e:
            logger.error(f"❌ Error writing RTP to WAV: {e}")
            
        return False
        
    def _convert_rtp_payload_to_pcm(self, payload: bytes, payload_type: int) -> Optional[bytes]:
        """Convert RTP audio payload to PCM format with automatic gain control."""
        try:
            from .audio_codec import ulaw_to_pcm, alaw_to_pcm
            
            # Convert using standard G.711
            if payload_type == 0:  # PCMU (μ-law)
                pcm_data = ulaw_to_pcm(payload)
            elif payload_type == 8:  # PCMA (A-law)  
                pcm_data = alaw_to_pcm(payload)
            else:
                logger.warning(f"Unsupported payload type {payload_type} for WAV recording")
                return None
                
            if not pcm_data:
                return None
                
            # ENHANCED: Apply Automatic Gain Control (AGC) for audible WAV recordings
            pcm_data = self._apply_agc_to_pcm(pcm_data)
            return pcm_data
                
        except Exception as e:
            logger.error(f"Error converting RTP payload: {e}")
            return None
            
    def _apply_agc_to_pcm(self, pcm_data: bytes) -> bytes:
        """Apply Automatic Gain Control (AGC) to make audio audible."""
        try:
            import struct
            import math
            
            if len(pcm_data) < 2:
                return pcm_data
                
            # Unpack samples
            sample_count = len(pcm_data) // 2
            samples = list(struct.unpack(f'<{sample_count}h', pcm_data))
            
            if not samples:
                return pcm_data
                
            # Calculate current audio levels
            max_amplitude = max(abs(s) for s in samples)
            rms = math.sqrt(sum(s*s for s in samples) / len(samples))
            
            # Only apply AGC if audio is too quiet (typical for G.711)
            if max_amplitude < 100:  # Very quiet, boost significantly
                gain = 150.0  # Increased from 50.0
            elif max_amplitude < 500:  # Quiet, boost moderately  
                gain = 60.0   # Increased from 20.0
            elif max_amplitude < 2000:  # Low but audible, boost gently
                gain = 20.0   # Increased from 8.0
            elif max_amplitude < 8000:  # Acceptable level, small boost
                gain = 5.0    # Increased from 3.0
            else:  # Already loud enough
                gain = 1.0
                
            # Apply gain with soft limiting to prevent harsh clipping
            boosted_samples = []
            for sample in samples:
                # Apply gain
                boosted = int(sample * gain)
                
                # Soft limiting to prevent harsh clipping
                if boosted > 20000:  # Soft limit at ~60% of max
                    boosted = 20000 + int((boosted - 20000) * 0.3)
                elif boosted < -20000:
                    boosted = -20000 + int((boosted + 20000) * 0.3)
                    
                # Hard limit to prevent overflow
                boosted = max(-32767, min(32767, boosted))
                boosted_samples.append(boosted)
            
            # Log AGC activity for debugging (only for first few packets)
            if not hasattr(self, '_agc_log_count'):
                self._agc_log_count = 0
            
            final_max = max(abs(s) for s in boosted_samples)
            if gain > 1.0 and self._agc_log_count < 3:
                logger.debug(f"🔊 AGC applied: {max_amplitude} → {final_max} (gain: {gain:.1f}x)")
                self._agc_log_count += 1
            
            # Pack back to bytes
            return struct.pack(f'<{len(boosted_samples)}h', *boosted_samples)
            
        except Exception as e:
            logger.error(f"❌ AGC error: {e}")
            return pcm_data  # Return original if AGC fails
            
    def close(self):
        """Close the WAV file."""
        if self.wav_file:
            try:
                self.wav_file.close()
                logger.info(f"🎵 Closed WAV file: {self.filename} ({self.packets_written} packets written)")
            except Exception as e:
                logger.error(f"❌ Error closing WAV file: {e}")
            finally:
                self.wav_file = None

class RtpBridge:
    """
    RTP bridge that forwards audio between two endpoints and captures for AI.
    Acts as a true media relay to intercept RTP packets.
    """
    
    def __init__(self, local_ip: str):
        self.local_ip = local_ip
        self.local_port = None
        self.socket = None
        self.running = False
        self.upnp_enabled = False
        
        # Test mode for debugging audio pipeline
        self.test_mode = False
        self.test_audio_file = None
        self.test_audio_data = None
        self.test_audio_packets = []
        self.test_packet_index = 0
        
        # AI audio streaming state - fixed for proper RTP timing
        self._ai_sequence_number = 0
        self._ai_timestamp_base = 0
        self._ai_samples_sent = 0  # Track samples sent for current stream
        self._is_first_ai_chunk = True # NEW: Flag to handle initial audio chunk
        
        # Endpoints - learned dynamically
        self.caller_endpoint: Optional[AudioEndpoint] = None  # Phone
        self.remote_endpoint: Optional[AudioEndpoint] = None  # Zoho server
        
        # Audio callbacks
        self.audio_callback: Optional[Callable[[bytes, str], None]] = None
        
        # Audio recording for verification - now using WAV format
        self.record_audio = True
        self.audio_dir = "captured_audio"
        self.caller_wav_recorder: Optional[WavRecorder] = None
        self.remote_wav_recorder: Optional[WavRecorder] = None
        self.max_recording_packets = 500  # Increased limit for WAV files
        
        # Statistics
        self.packets_forwarded = 0
        self.packets_to_ai = 0
        self.packets_from_ai = 0
        self.caller_packets_recorded = 0
        self.remote_packets_recorded = 0
        
        # Setup recording directory
        if self.record_audio:
            os.makedirs(self.audio_dir, exist_ok=True)
        
        # Register cleanup function
        atexit.register(self._cleanup_upnp)
        
        logger.info(f"🌉 RTP Bridge initialized for {local_ip}")
        if self.record_audio:
            logger.info(f"🎵 WAV audio recording enabled - will save to {self.audio_dir}/")
    
    def start_bridge(self, remote_audio: Optional[AudioParams] = None) -> Optional[int]:
        """Start the RTP bridge and return the local listening port."""
        try:
            # Create UDP socket for RTP
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Try to bind to a specific port range for NAT traversal
            port_assigned = False
            from ..config import get_settings
            from ..utils.network import upnp_manager
            settings = get_settings()
            
            # Initialize UPnP if enabled
            try:
                if upnp_manager.initialize():
                    self.upnp_enabled = True
                    logger.info("🎯 UPnP enabled - will automatically configure port forwarding")
                else:
                    logger.warning("⚠️  UPnP not available - manual port forwarding required")
            except Exception as e:
                logger.warning(f"⚠️  UPnP initialization failed: {e}")
            
            if hasattr(settings.calls, 'use_fixed_rtp_port') and settings.calls.use_fixed_rtp_port:
                # Try ports in the configured range
                port_min = getattr(settings.calls, 'rtp_port_min', 10000)
                port_max = getattr(settings.calls, 'rtp_port_max', 10100)
                
                logger.info(f"🔧 NAT TRAVERSAL: Trying fixed port range {port_min}-{port_max}")
                
                for port in range(port_min, port_max + 1):
                    try:
                        self.socket.bind(("0.0.0.0", port))
                        self.local_port = port
                        port_assigned = True
                        
                        # Try UPnP port forwarding
                        if self.upnp_enabled:
                            if upnp_manager.forward_port(port, 'UDP', f'Callie RTP {port}'):
                                logger.info(f"🎯 RTP Bridge bound to FIXED PORT: 0.0.0.0:{port} (UPnP forwarded)")
                            else:
                                logger.info(f"🎯 RTP Bridge bound to FIXED PORT: 0.0.0.0:{port} (UPnP failed)")
                                logger.info(f"📋 MANUAL NAT SETUP: Forward UDP port {port} to {self.local_ip}:{port}")
                        else:
                            logger.info(f"🎯 RTP Bridge bound to FIXED PORT: 0.0.0.0:{port}")
                            logger.info(f"📋 MANUAL NAT SETUP: Forward UDP port {port} to {self.local_ip}:{port}")
                        break
                    except OSError:
                        continue  # Port in use, try next one
                        
                if not port_assigned:
                    logger.warning(f"⚠️  All ports {port_min}-{port_max} in use, falling back to random port")
            
            if not port_assigned:
                # Fallback to random port (original behavior)
                self.socket.bind(("0.0.0.0", 0))  # Bind to all interfaces on any available port
                self.local_port = self.socket.getsockname()[1]
                
                # Try UPnP on random port
                if self.upnp_enabled:
                    if upnp_manager.forward_port(self.local_port, 'UDP', f'Callie RTP {self.local_port}'):
                        logger.info(f"🌉 RTP Bridge on random port {self.local_port} (UPnP forwarded)")
                    else:
                        logger.warning(f"🌉 RTP Bridge on random port {self.local_port} (UPnP failed)")
                        logger.warning(f"⚠️  MANUAL SETUP: Forward UDP port {self.local_port} to {self.local_ip}:{self.local_port}")
                else:
                    logger.info(f"🌉 RTP Bridge listening on ALL INTERFACES::{self.local_port} (random port)")
                    logger.warning(f"⚠️  MANUAL SETUP: Forward UDP port {self.local_port} to {self.local_ip}:{self.local_port}")
            
            logger.info(f"🔧 NAT FIX: Bridge can receive packets sent to public IP")
            
            # Set remote endpoint if provided
            if remote_audio:
                self.remote_endpoint = AudioEndpoint(
                    ip=remote_audio.ip_address,
                    port=remote_audio.port
                )
                logger.info(f"🎯 Remote endpoint configured: {self.remote_endpoint.ip}:{self.remote_endpoint.port}")
            
            # Setup audio recording files - now as WAV files
            if self.record_audio:
                timestamp = int(time.time())
                
                # Create WAV recorders
                caller_filename = f"{self.audio_dir}/caller_audio_{timestamp}.wav"
                remote_filename = f"{self.audio_dir}/remote_audio_{timestamp}.wav"
                
                self.caller_wav_recorder = WavRecorder(caller_filename, sample_rate=8000)
                self.remote_wav_recorder = WavRecorder(remote_filename, sample_rate=8000)
                
                self.caller_wav_recorder.open()
                self.remote_wav_recorder.open()
                
                logger.info(f"🎵 WAV recording files created for session {timestamp}")
            
            # Start bridge loop
            self.running = True
            bridge_thread = threading.Thread(target=self._bridge_loop, daemon=True)
            bridge_thread.start()
            
            return self.local_port
            
        except Exception as e:
            logger.error(f"❌ Failed to start RTP bridge: {e}")
            return None
    
    def set_remote_endpoint(self, remote_audio: AudioParams) -> None:
        """Set the remote endpoint after receiving 200 OK."""
        self.remote_endpoint = AudioEndpoint(
            ip=remote_audio.ip_address,
            port=remote_audio.port
        )
        
        # CRITICAL FIX: Also set caller_endpoint so AI audio can be sent immediately
        # In our setup, the remote endpoint (Zoho server) is where we send AI audio
        if not self.caller_endpoint:
            self.caller_endpoint = AudioEndpoint(
                ip=remote_audio.ip_address,
                port=remote_audio.port
            )
            logger.info(f"🎯 Caller endpoint initialized from SDP: {self.caller_endpoint.ip}:{self.caller_endpoint.port}")
        
        logger.info(f"🎯 Remote endpoint updated: {self.remote_endpoint.ip}:{self.remote_endpoint.port}")
    
    def set_audio_callback(self, callback: Callable[[bytes, str], None]) -> None:
        """Set callback for captured audio."""
        self.audio_callback = callback
        logger.info("🎤 Audio capture callback registered")
    
    def enable_test_mode(self, test_audio_file: str = None) -> bool:
        """Enable test mode to inject known audio instead of AI audio."""
        try:
            if not test_audio_file:
                # Create a simple test tone
                self._create_test_tone()
            else:
                # Load audio file
                if not self._load_test_audio_file(test_audio_file):
                    return False
            
            self.test_mode = True
            logger.info(f"🧪 Test mode enabled - will inject test audio instead of AI audio")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to enable test mode: {e}")
            return False
    
    def _create_test_tone(self) -> None:
        """Create a simple test tone for audio testing."""
        import math
        
        # Generate a 1kHz tone for 3 seconds at 8kHz sample rate
        sample_rate = 8000
        duration = 3.0
        frequency = 1000
        
        samples = []
        for i in range(int(sample_rate * duration)):
            # Generate sine wave
            sample = int(16000 * math.sin(2 * math.pi * frequency * i / sample_rate))
            samples.append(max(-32767, min(32767, sample)))  # Clamp to 16-bit range
        
        # Convert to PCM bytes
        pcm_data = struct.pack(f'<{len(samples)}h', *samples)
        
        # Convert PCM to μ-law and create RTP packets
        self._create_test_rtp_packets(pcm_data)
        logger.info(f"🎵 Created test tone: {len(self.test_audio_packets)} RTP packets")
    
    def _load_test_audio_file(self, filename: str) -> bool:
        """Load audio file and convert to RTP packets for testing."""
        try:
            import wave
            
            # Open WAV file
            with wave.open(filename, 'rb') as wav_file:
                if wav_file.getnchannels() != 1:
                    logger.error("❌ Test audio file must be mono")
                    return False
                
                if wav_file.getsampwidth() != 2:
                    logger.error("❌ Test audio file must be 16-bit")
                    return False
                
                sample_rate = wav_file.getframerate()
                frames = wav_file.readframes(wav_file.getnframes())
                
                # Resample to 8kHz if needed
                if sample_rate != 8000:
                    from .audio_codec import resample_simple
                    frames = resample_simple(frames, sample_rate, 8000, 2)
                
                self._create_test_rtp_packets(frames)
                logger.info(f"🎵 Loaded test audio: {filename} -> {len(self.test_audio_packets)} RTP packets")
                return True
                
        except Exception as e:
            logger.error(f"❌ Failed to load test audio file {filename}: {e}")
            return False
    
    def _create_test_rtp_packets(self, pcm_data: bytes) -> None:
        """Convert PCM audio to RTP packets for testing."""
        from .audio_codec import pcm_to_ulaw
        
        # Convert PCM to μ-law
        ulaw_data = pcm_to_ulaw(pcm_data)
        
        # Split into RTP packet payloads (160 bytes each for 20ms at 8kHz)
        payload_size = 160
        self.test_audio_packets = []
        
        for i in range(0, len(ulaw_data), payload_size):
            payload = ulaw_data[i:i + payload_size]
            if len(payload) < payload_size:
                # Pad last packet with silence
                payload += b'\x7f' * (payload_size - len(payload))
            
            # Create RTP packet
            rtp_packet = self._create_rtp_packet_for_test_audio(payload, i // payload_size)
            if rtp_packet:
                self.test_audio_packets.append(rtp_packet)
    
    def _create_rtp_packet_for_test_audio(self, ulaw_payload: bytes, sequence: int) -> Optional[bytes]:
        """Create RTP packet for test audio."""
        try:
            # RTP header
            version = 2
            padding = 0
            extension = 0
            csrc_count = 0
            marker = 0
            payload_type = 0  # PCMU (μ-law)
            sequence_number = sequence & 0xFFFF
            timestamp = (sequence * 160) & 0xFFFFFFFF  # 160 samples per packet at 8kHz
            ssrc = 0x12345678  # Test SSRC
            
            # Pack RTP header (12 bytes)
            byte0 = (version << 6) | (padding << 5) | (extension << 4) | csrc_count
            byte1 = (marker << 7) | payload_type
            
            header = struct.pack('!BBHII', byte0, byte1, sequence_number, timestamp, ssrc)
            return header + ulaw_payload
            
        except Exception as e:
            logger.error(f"❌ Error creating test RTP packet: {e}")
            return None
    
    def get_test_audio_packet(self) -> Optional[bytes]:
        """Get next test audio packet for injection."""
        if not self.test_mode or not self.test_audio_packets:
            return None
        
        packet = self.test_audio_packets[self.test_packet_index]
        self.test_packet_index = (self.test_packet_index + 1) % len(self.test_audio_packets)
        return packet
    
    def start_test_audio_injection(self) -> None:
        """Start injecting test audio immediately (simpler approach)."""
        if not self.test_mode or not self.test_audio_packets:
            logger.error("❌ Test mode not enabled or no test audio packets")
            return
        
        import threading
        import time
        
        def inject_test_audio_loop():
            logger.info("🧪 Starting test audio injection loop...")
            packet_count = 0
            
            while self.running and self.test_mode:
                if self.caller_endpoint:  # Send to learned caller endpoint, not remote_endpoint
                    test_packet = self.get_test_audio_packet()
                    if test_packet:
                        try:
                            # Send directly to caller endpoint (where Zoho expects our audio)
                            self.socket.sendto(test_packet, (self.caller_endpoint.ip, self.caller_endpoint.port))
                            packet_count += 1
                            
                            if packet_count % 50 == 0:  # Log every 50 packets (1 second)
                                logger.info(f"🧪 Sent {packet_count} test audio packets to {self.caller_endpoint.ip}:{self.caller_endpoint.port}")
                            
                        except Exception as e:
                            logger.error(f"❌ Error sending test audio: {e}")
                            break
                
                time.sleep(0.02)  # 20ms intervals
            
            logger.info(f"🧪 Test audio injection ended after {packet_count} packets")
        
        test_thread = threading.Thread(target=inject_test_audio_loop, daemon=True)
        test_thread.start()
        logger.info("🧪 Test audio injection thread started")
    
    def _bridge_loop(self) -> None:
        """Main bridge loop - forwards RTP packets and captures for AI."""
        logger.info("🌉 RTP Bridge loop started")
        logger.info(f"🔍 Listening for RTP packets on ALL INTERFACES port {self.local_port}")
        logger.info(f"🎯 Will capture caller audio for AI (NO ECHO FORWARDING)")
        
        last_stats_time = time.time()
        packet_sources = set()  # Track unique packet sources
        
        while self.running:
            try:
                self.socket.settimeout(1.0)  # 1 second timeout
                data, addr = self.socket.recvfrom(4096)
                
                # Track packet sources for debugging
                source_key = f"{addr[0]}:{addr[1]}"
                if source_key not in packet_sources:
                    packet_sources.add(source_key)
                    logger.info(f"🆕 NEW RTP SOURCE detected: {source_key}")
                    
                    # Analyze the first packet from this source
                    self._analyze_rtp_packet(data, addr, "INCOMING")
                
                # Learn caller endpoint from first packet (this is actually Zoho sending caller audio to us)
                if not self.caller_endpoint:
                    self.caller_endpoint = AudioEndpoint(ip=addr[0], port=addr[1])
                    logger.info(f"📞 Audio source endpoint learned: {self.caller_endpoint.ip}:{self.caller_endpoint.port}")
                    logger.info(f"🔧 ECHO PREVENTION: Will NOT forward caller audio back to this endpoint")
                
                # Handle incoming RTP packets - these are the caller's voice from Zoho
                if addr[0] == self.caller_endpoint.ip and addr[1] == self.caller_endpoint.port:
                    # Packet from Zoho (containing caller's voice) → capture for AI only, DON'T echo back
                    logger.debug(f"📥 Received caller audio from Zoho: {len(data)} bytes")
                    self._capture_for_ai(data, "caller")
                    self._record_audio(data, "caller")
                    # 🚫 CRITICAL: Do NOT forward back to prevent echo!
                    
                elif self.remote_endpoint and addr[0] == self.remote_endpoint.ip and addr[1] == self.remote_endpoint.port:
                    # This shouldn't happen in our setup since Zoho is both endpoints
                    # But handle gracefully
                    logger.debug(f"📥 Received audio from alternate endpoint: {len(data)} bytes")
                    self._capture_for_ai(data, "remote")
                    self._record_audio(data, "remote")
                    
                else:
                    # Log unknown sources for debugging
                    if len(packet_sources) <= 5:  # Only log first few unknowns
                        logger.info(f"🤔 Unknown RTP source: {addr[0]}:{addr[1]} (may be NAT/proxy)")
                
                self.packets_forwarded += 1
                
                # Enhanced statistics every 10 seconds
                if time.time() - last_stats_time > 10:
                    logger.info(f"🌉 Bridge stats: {self.packets_forwarded} received, {self.packets_to_ai} to AI, {self.packets_from_ai} from AI")
                    logger.info(f"📊 Packet sources seen: {len(packet_sources)} unique endpoints")
                    if self.record_audio:
                        logger.info(f"🎵 WAV Recording stats: {self.caller_packets_recorded} caller packets, {self.remote_packets_recorded} remote packets saved to WAV")
                    if self.packets_forwarded > 0:
                        logger.info("✅ SUCCESS! Audio packets flowing - NO ECHO forwarding")
                    else:
                        logger.warning("⚠️  Still waiting for RTP packets...")
                    last_stats_time = time.time()
                
            except socket.timeout:
                # Normal timeout, continue
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"❌ Bridge loop error: {e}")
                break
        
        logger.info("🌉 RTP Bridge loop ended")
    
    def _analyze_rtp_packet(self, data: bytes, addr: tuple, direction: str) -> None:
        """Analyze RTP packet for debugging."""
        try:
            if len(data) < 12:
                logger.warning(f"📦 {direction} packet too short: {len(data)} bytes from {addr[0]}:{addr[1]}")
                return
            
            # Parse RTP header
            version = (data[0] & 0xC0) >> 6
            padding = (data[0] & 0x20) >> 5
            extension = (data[0] & 0x10) >> 4
            csrc_count = data[0] & 0x0F
            marker = (data[1] & 0x80) >> 7
            payload_type = data[1] & 0x7F
            sequence = (data[2] << 8) | data[3]
            timestamp = (data[4] << 24) | (data[5] << 16) | (data[6] << 8) | data[7]
            ssrc = (data[8] << 24) | (data[9] << 16) | (data[10] << 8) | data[11]
            
            payload_size = len(data) - 12
            
            logger.info(f"📦 {direction} RTP ANALYSIS from {addr[0]}:{addr[1]}:")
            logger.info(f"   • Version: {version}, Payload Type: {payload_type} ({'PCMU' if payload_type == 0 else 'PCMA' if payload_type == 8 else 'OTHER'})")
            logger.info(f"   • Sequence: {sequence}, Timestamp: {timestamp}")
            logger.info(f"   • SSRC: 0x{ssrc:08x}, Payload: {payload_size} bytes")
            logger.info(f"   • Marker: {marker}, Padding: {padding}")
            
        except Exception as e:
            logger.error(f"❌ Error analyzing RTP packet: {e}")
    
    def _record_audio(self, data: bytes, source: str) -> None:
        """Record RTP packets as WAV audio files."""
        if not self.record_audio:
            return
            
        try:
            if source == "caller" and self.caller_packets_recorded < self.max_recording_packets:
                if self.caller_wav_recorder and self.caller_wav_recorder.write_rtp_packet(data):
                    self.caller_packets_recorded += 1
                    if self.caller_packets_recorded == 1:
                        logger.info(f"🎵 WAV RECORDING: First caller audio packet saved! ({len(data)} bytes RTP)")
                    elif self.caller_packets_recorded % 50 == 0:
                        logger.info(f"🎵 WAV RECORDING: {self.caller_packets_recorded} caller packets saved to WAV")
                        
            elif source == "remote" and self.remote_packets_recorded < self.max_recording_packets:
                if self.remote_wav_recorder and self.remote_wav_recorder.write_rtp_packet(data):
                    self.remote_packets_recorded += 1
                    if self.remote_packets_recorded == 1:
                        logger.info(f"🎵 WAV RECORDING: First remote audio packet saved! ({len(data)} bytes RTP)")
                    elif self.remote_packets_recorded % 50 == 0:
                        logger.info(f"🎵 WAV RECORDING: {self.remote_packets_recorded} remote packets saved to WAV")
                        
        except Exception as e:
            logger.error(f"❌ WAV recording error: {e}")
    
    def _forward_to_remote(self, data: bytes) -> None:
        """Forward RTP packet from caller to remote server."""
        if self.remote_endpoint:
            try:
                # Send to remote server (Zoho)
                self.socket.sendto(data, (self.remote_endpoint.ip, self.remote_endpoint.port))
                logger.debug(f"📤 Forwarded {len(data)} bytes to remote")
            except Exception as e:
                logger.error(f"❌ Failed to forward to remote: {e}")
    
    def _forward_to_caller(self, data: bytes) -> None:
        """Forward RTP packet from remote server to caller."""
        if self.caller_endpoint:
            try:
                # Send back to caller (phone)
                self.socket.sendto(data, (self.caller_endpoint.ip, self.caller_endpoint.port))
                logger.debug(f"📤 Forwarded {len(data)} bytes to caller")
            except Exception as e:
                logger.error(f"❌ Failed to forward to caller: {e}")
    
    def _capture_for_ai(self, rtp_data: bytes, source: str) -> None:
        """Capture and process RTP audio for AI."""
        try:
            if len(rtp_data) < 12:  # Minimum RTP header size
                return
                
            # Parse RTP header to get payload type and payload
            payload_type = rtp_data[1] & 0x7F  # Extract payload type
            payload = rtp_data[12:]  # Skip 12-byte RTP header
            
            if not payload:
                return
                
            # 🎵 Convert RTP payload to PCM audio for AI
            pcm_audio = self._convert_rtp_to_pcm(payload, payload_type)
            if pcm_audio and self.audio_callback:
                # Check if this audio contains voice (simple amplitude check)
                import struct
                samples = struct.unpack(f'<{len(pcm_audio)//2}h', pcm_audio)
                max_amplitude = max(abs(s) for s in samples) if samples else 0
                
                # Log voice detection for debugging
                if self.packets_to_ai <= 10 or max_amplitude > 1000:  # First 10 packets or voice detected
                    voice_detected = "🗣️  VOICE" if max_amplitude > 1000 else "🔇 silence"
                    logger.info(f"🎤 {source} audio #{self.packets_to_ai}: {len(payload)} bytes RTP → {len(pcm_audio)} bytes PCM (max: {max_amplitude}) {voice_detected}")
                
                self.audio_callback(pcm_audio, source)
                self.packets_to_ai += 1
                
                # Enhanced logging for voice activity
                if max_amplitude > 1000:  # Voice threshold
                    if not hasattr(self, '_last_voice_time'):
                        logger.info("🗣️  VOICE ACTIVITY DETECTED - AI should be hearing you now!")
                    self._last_voice_time = time.time()
                    
        except Exception as e:
            logger.error(f"Error capturing RTP for AI: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
    def _convert_rtp_to_pcm(self, rtp_payload: bytes, payload_type: int) -> Optional[bytes]:
        """Convert RTP audio payload to PCM format for AI processing."""
        try:
            from .audio_codec import ulaw_to_pcm, alaw_to_pcm, resample_simple
            
            # Map payload types to codecs (based on SDP we're advertising)
            # 0 = PCMU (μ-law), 8 = PCMA (A-law), 18 = G729
            if payload_type == 0:  # PCMU (μ-law)
                # Convert μ-law to PCM 8kHz
                pcm_8khz = ulaw_to_pcm(rtp_payload)
                # Apply AGC for consistent levels
                pcm_8khz = self._apply_agc_to_pcm(pcm_8khz)
                # Resample to 16kHz for AI
                pcm_16khz = resample_simple(pcm_8khz, 8000, 16000, 2)
                return pcm_16khz
                
            elif payload_type == 8:  # PCMA (A-law)
                # Convert A-law to PCM 8kHz
                pcm_8khz = alaw_to_pcm(rtp_payload)
                # Apply AGC for consistent levels
                pcm_8khz = self._apply_agc_to_pcm(pcm_8khz)
                # Resample to 16kHz for AI
                pcm_16khz = resample_simple(pcm_8khz, 8000, 16000, 2)
                return pcm_16khz
                
            elif payload_type == 18:  # G729
                logger.warning(f"G729 codec not yet supported for payload type {payload_type}")
                # TODO: Implement G729 decoder
                return None
                
            else:
                logger.warning(f"Unsupported RTP payload type: {payload_type}")
                return None
                
        except Exception as e:
            logger.error(f"Error converting RTP payload (type {payload_type}): {e}")
            return None
    
    def _enhance_audio_quality(self, pcm_data: bytes, sample_count: int) -> bytes:
        """
        Apply audio quality enhancement filters for better call quality.
        Includes normalization, noise reduction, and dynamic range optimization.
        """
        try:
            import struct
            import numpy as np
            
            # Convert to numpy array for processing
            samples = np.frombuffer(pcm_data, dtype=np.int16)
            samples_float = samples.astype(np.float32)
            
            # 1. Peak normalization to optimize dynamic range
            max_val = np.max(np.abs(samples_float))
            if max_val > 0:
                # Normalize to 85% of max range to prevent clipping but maintain clarity
                target_peak = 32767 * 0.85
                normalization_factor = target_peak / max_val
                samples_float *= normalization_factor
                
            # 2. Simple noise gate - reduce very low amplitude noise
            noise_threshold = 200  # Very low threshold to preserve quiet speech
            samples_float = np.where(np.abs(samples_float) < noise_threshold, 
                                   samples_float * 0.1, samples_float)
            
            # 3. Soft compression to improve clarity without artifacts
            # Apply gentle compression to loud sounds while preserving quiet ones
            def soft_compress(x, threshold=20000, ratio=0.7):
                abs_x = np.abs(x)
                compressed = np.where(abs_x > threshold,
                                    threshold + (abs_x - threshold) * ratio,
                                    abs_x)
                return np.sign(x) * compressed
            
            samples_float = soft_compress(samples_float)
            
            # 4. Final clipping protection
            samples_float = np.clip(samples_float, -32767, 32767)
            
            # Convert back to int16
            enhanced_samples = samples_float.astype(np.int16)
            
            logger.debug(f"🎵 Audio enhancement: {max_val:.0f} → {np.max(np.abs(enhanced_samples)):.0f} peak")
            
            return enhanced_samples.tobytes()
            
        except Exception as e:
            logger.warning(f"⚠️  Audio enhancement failed, using original: {e}")
            return pcm_data
            
    def _apply_agc_to_pcm(self, pcm_data: bytes) -> bytes:
        """ENHANCED AGC: Professional audio processing with clarity optimization."""
        try:
            import struct
            import math
            import numpy as np
            
            if len(pcm_data) < 2:
                return pcm_data
                
            # Unpack samples  
            sample_count = len(pcm_data) // 2
            samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32)
            
            if len(samples) == 0:
                return pcm_data
                
            # Calculate current audio levels
            max_amplitude = np.max(np.abs(samples))
            rms = np.sqrt(np.mean(samples**2))
            
            # ENHANCED: RMS-based AGC with reduced fuzziness 
            target_rms = 4000  # Optimal level for clarity without distortion
            
            if rms < 100:  # Very quiet
                gain = min(25.0, target_rms / max(rms, 50))  # Conservative gain
            elif rms < 500:  # Quiet  
                gain = min(10.0, target_rms / rms)  # Moderate boost
            elif rms < 1500:  # Low but audible
                gain = min(5.0, target_rms / rms)   # Gentle boost
            elif rms < 3000:  # Acceptable level  
                gain = min(2.0, target_rms / rms)   # Minimal boost
            else:  # Already good level
                gain = 1.0
                
            # Apply gain with soft limiting to prevent harsh clipping
            boosted_samples = []
            for sample in samples:
                # Apply gain
                boosted = int(sample * gain)
                
                # Soft limiting to prevent harsh clipping
                if boosted > 20000:  # Soft limit at ~60% of max
                    boosted = 20000 + int((boosted - 20000) * 0.3)
                elif boosted < -20000:
                    boosted = -20000 + int((boosted + 20000) * 0.3)
                    
                # Hard limit to prevent overflow
                boosted = max(-32767, min(32767, boosted))
                boosted_samples.append(boosted)
            
            # Log AGC activity for debugging (only for first few packets)
            if not hasattr(self, '_agc_log_count'):
                self._agc_log_count = 0
            
            final_max = max(abs(s) for s in boosted_samples)
            if gain > 1.0 and self._agc_log_count < 3:
                logger.debug(f"🔊 AGC applied: {max_amplitude} → {final_max} (gain: {gain:.1f}x)")
                self._agc_log_count += 1
            
            # Pack back to bytes
            return struct.pack(f'<{len(boosted_samples)}h', *boosted_samples)
            
        except Exception as e:
            logger.error(f"❌ AGC error: {e}")
            return pcm_data  # Return original if AGC fails
            
    def _stream_packets(self, rtp_packets: list[bytes], target_endpoint: AudioEndpoint) -> int:
        """Streams a list of RTP packets with precise timing, returns packets sent."""
        if not target_endpoint:
            logger.warning("⚠️ No target endpoint, cannot stream packets.")
            return 0

        if not rtp_packets:
            logger.warning("⚠️ No packets provided to stream.")
            return 0

        packet_interval = 0.010  # 10ms between packets (optimal)
        packets_sent = 0
        start_time = time.time()

        for i, packet in enumerate(rtp_packets):
            try:
                # Calculate when this packet should be sent
                target_time = start_time + (i * packet_interval)
                current_time = time.time()

                # If we're ahead of schedule, wait briefly
                if current_time < target_time:
                    delay = target_time - current_time
                    if delay > 0.0005:  # Sleep if delay > 0.5ms
                        time.sleep(delay)
                
                self.socket.sendto(packet, (target_endpoint.ip, target_endpoint.port))
                self.packets_from_ai += 1
                packets_sent += 1

                self._record_audio(packet, "remote")

                if i < 2:
                    self._analyze_rtp_packet(packet, (target_endpoint.ip, target_endpoint.port), f"AI_AUDIO_STREAM #{i+1}")
            
            except Exception as e:
                logger.error(f"❌ Error sending packet {i} during stream: {e}")
                break
        
        return packets_sent

    def send_ai_audio(self, audio_data: bytes, target: str = "caller") -> None:
        """Send AI-generated audio to the call by packetizing and streaming it."""
        # CRITICAL FIX: Use remote_endpoint as fallback if caller_endpoint not set
        target_endpoint = self.caller_endpoint or self.remote_endpoint
        
        if not target_endpoint:
            logger.warning("⚠️  No caller or remote endpoint available for AI audio")
            return
            
        try:
            # FIX: Pre-send silence to warm up the RTP stream and prevent initial choppiness
            if self._is_first_ai_chunk:
                logger.info("🔥 WARMING UP RTP STREAM with 100ms of silence...")
                # 100ms of silence at 24kHz, 16-bit PCM
                warmup_audio_data = b'\x00' * (24000 * 2 // 10)
                
                # Create and stream silence packets
                warmup_packets = self._create_rtp_packets_for_ai_audio(warmup_audio_data)
                if warmup_packets:
                    packets_sent = self._stream_packets(warmup_packets, target_endpoint)
                    logger.info(f"🔥 Sent {packets_sent} silence packets to prime the connection.")
                
                self._is_first_ai_chunk = False

            # Create a list of RTP packets from the AI's audio chunk
            rtp_packets = self._create_rtp_packets_for_ai_audio(audio_data)
            
            if not rtp_packets:
                logger.error("❌ Failed to create any RTP packets for AI audio")
                return
                
            logger.info(f"🎤 Streaming {len(rtp_packets)} AI audio packets to {target_endpoint.ip}:{target_endpoint.port}")
            packets_sent = self._stream_packets(rtp_packets, target_endpoint)
            logger.info(f"✅ Sent {packets_sent}/{len(rtp_packets)} AI audio packets")
            
        except Exception as e:
            logger.error(f"❌ Error in send_ai_audio: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _create_rtp_packets_for_ai_audio(self, ai_audio_data: bytes) -> list[bytes]:
        """
        Create a list of RTP packets from AI-generated audio.
        ENHANCED: Validates audio format and ensures precise conversion.
        """
        packets = []
        try:
            from .audio_codec import pcm_to_alaw, resample_simple
            import struct
            
            logger.info(f"🎵 Processing AI audio: {len(ai_audio_data)} bytes from Gemini Live API")
            
            # ENHANCED: Validate and analyze input audio
            if len(ai_audio_data) % 2 != 0:
                logger.warning(f"⚠️  AI audio size {len(ai_audio_data)} is not even - may not be 16-bit PCM")
                # Pad with zero byte if odd
                ai_audio_data += b'\x00'
            
            sample_count = len(ai_audio_data) // 2
            logger.info(f"🔬 AI Audio Analysis: {sample_count} samples, assumed 16-bit PCM")
            
            # Calculate expected timing based on 24kHz assumption
            expected_duration_ms = (sample_count / 24000) * 1000
            logger.info(f"⏱️  Expected duration (24kHz): {expected_duration_ms:.1f}ms")
            
            # OPTIMIZED: Direct and precise audio processing pipeline
            # Step 1: Validate that this is really 24kHz, 16-bit PCM
            try:
                samples = struct.unpack(f'<{sample_count}h', ai_audio_data)
                max_amplitude = max(abs(s) for s in samples) if samples else 0
                avg_amplitude = sum(abs(s) for s in samples) / len(samples) if samples else 0
                
                logger.info(f"📊 Audio levels: max={max_amplitude}, avg={avg_amplitude:.1f}")
                
                if max_amplitude > 32767:
                    logger.error(f"❌ Invalid PCM data - amplitude exceeds 16-bit range!")
                    return packets
                    
            except Exception as e:
                logger.error(f"❌ Failed to validate PCM audio: {e}")
                return packets
            
            # NEW Step 1.5: Enhance Voice Clarity (High-pass Filter)
            try:
                from pydub import AudioSegment
                
                # Load raw PCM data into an AudioSegment
                audio_segment = AudioSegment(
                    data=ai_audio_data,
                    sample_width=2,  # 16-bit
                    frame_rate=24000,
                    channels=1
                )
                
                # Apply a high-pass filter to remove low-frequency noise/muddiness
                # A cutoff of 100-120Hz is standard for voice clarity
                filtered_segment = audio_segment.high_pass_filter(120)
                
                # NEW: Apply dynamic range compression for consistent volume
                compressed_segment = filtered_segment.compress_dynamic_range(
                    threshold=-20.0,  # The level (in dBFS) above which to start compressing
                    ratio=4.0,      # The compression ratio (e.g., 4:1)
                    attack=5.0,     # Time (in ms) to react to loud sounds
                    release=100.0   # Time (in ms) to recover after loud sounds
                )

                # Get the enhanced audio data back
                ai_audio_data = compressed_segment.raw_data
                logger.info(f"✨ Voice Clarity Enhanced: Applied 120Hz high-pass filter and compression")

            except ImportError:
                logger.warning("⚠️ pydub not installed, skipping voice clarity enhancement.")
            except Exception as e:
                logger.warning(f"⚠️ Voice clarity enhancement failed: {e}")

            # Step 2: High-quality resample from 24kHz to 8kHz (telephony standard)
            pcm_8khz_data = resample_simple(ai_audio_data, from_rate=24000, to_rate=8000)
            logger.info(f"🔄 PRECISE resample 24kHz→8kHz: {len(ai_audio_data)} → {len(pcm_8khz_data)} bytes")
            
            # Validate resampling result
            expected_8khz_samples = sample_count // 3  # Exact 3:1 ratio (24kHz -> 8kHz)
            expected_8khz_bytes = expected_8khz_samples * 2
            if len(pcm_8khz_data) != expected_8khz_bytes:
                logger.warning(f"⚠️  Resampling error: expected {expected_8khz_bytes} bytes, got {len(pcm_8khz_data)}")
            
            # Step 3: Convert to A-law for RTP transmission  
            from .audio_codec import pcm_to_alaw
            alaw_data = pcm_to_alaw(pcm_8khz_data)
            logger.info(f"🔄 PCM→A-law: {len(pcm_8khz_data)} → {len(alaw_data)} bytes")
            
            # Set codec parameters for A-law
            codec_data = alaw_data
            payload_type_to_use = 8    # A-law (PCMA)
            samples_per_byte = 1       # A-law: each byte = 1 sample
            sample_rate = 8000         # 8kHz
            
            # Step 4: Initialize precise timing for 8kHz audio stream
            if not hasattr(self, '_ai_timestamp_base') or self._ai_timestamp_base == 0:
                # Initialize with current time but convert to 8kHz sample units
                self._ai_timestamp_base = int(time.time() * 8000) % (2**32)
                self._ai_samples_sent = 0
                logger.info(f"🕐 Initialized AI audio stream timing (8kHz) - base timestamp: {self._ai_timestamp_base}")
            
            # Step 5: Create precise RTP packets - OPTIMAL TIMING
            payload_size = 80  # 80 samples = 10ms at 8kHz (optimal balance)
            packet_index = 0
            
            if len(codec_data) == 0:
                logger.warning(f"⚠️  No A-law data to packetize")
                return packets
            
            for i in range(0, len(codec_data), payload_size):
                payload = codec_data[i:i+payload_size]
                
                # Pad with proper A-law silence if needed
                if len(payload) < payload_size:
                    # A-law silence value (0x55 = 0 in A-law encoding)
                    silence_padding = b'\x55' * (payload_size - len(payload))
                    payload += silence_padding
                    logger.debug(f"Padded packet #{packet_index} with {len(silence_padding)} A-law silence bytes")
                
                # Create RTP header with sample-accurate timing  
                version = 2
                payload_type = 8  # PCMA (A-law) - telephony standard
                ssrc = 0x87654321  # Unique SSRC for our AI audio
                
                # Sequence number increments by 1 for each packet
                sequence_number = self._ai_sequence_number
                self._ai_sequence_number = (self._ai_sequence_number + 1) & 0xFFFF
                
                # FIXED: Sample-accurate timestamp calculation
                timestamp = (self._ai_timestamp_base + self._ai_samples_sent) & 0xFFFFFFFF
                self._ai_samples_sent += len(payload)  # Each byte = 1 sample in A-law
                
                # Pack the RTP header (12 bytes) with optimal settings
                header = struct.pack('!BBHII', 
                                     (version << 6) | 0,  # V=2, P=0, X=0, CC=0
                                     payload_type,         # M=0, PT=8 (A-law)
                                     sequence_number,
                                     timestamp,
                                     ssrc)
                
                packets.append(header + payload)
                packet_index += 1
            
            # Final validation
            total_samples_sent = sum(len(p) - 12 for p in packets)  # Subtract RTP header size
            logger.info(f"✅ Created {len(packets)} HD VOICE RTP packets (16kHz G.722)")
            logger.debug(f"📊 HD VOICE Pipeline: 24kHz({sample_count}s)→16kHz→G.722({total_samples_sent}bytes)→RTP")
            
        except Exception as e:
            logger.error(f"❌ Error creating RTP packets for AI audio: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
        return packets
    
    def get_bridge_port(self) -> Optional[int]:
        """Get the local bridge port."""
        return self.local_port
    
    def stop_bridge(self) -> None:
        """Stop the RTP bridge."""
        self.running = False
        
        # Clean up UPnP port forwarding
        self._cleanup_upnp()
        
        # Close WAV recording files
        if self.record_audio:
            if self.caller_wav_recorder:
                self.caller_wav_recorder.close()
                logger.info(f"🎵 Caller WAV recording closed: {self.caller_packets_recorded} packets")
            if self.remote_wav_recorder:
                self.remote_wav_recorder.close()
                logger.info(f"🎵 Remote WAV recording closed: {self.remote_packets_recorded} packets")
        
        if self.socket:
            self.socket.close()
        logger.info(f"🛑 RTP Bridge stopped - Final stats: {self.packets_forwarded} forwarded, {self.packets_to_ai} to AI, {self.packets_from_ai} from AI")
    
    def _cleanup_upnp(self) -> None:
        """Clean up UPnP port forwarding when bridge stops."""
        if self.upnp_enabled and self.local_port:
            try:
                from ..utils.network import upnp_manager
                upnp_manager.remove_port(self.local_port, 'UDP')
                logger.info(f"🧹 Cleaned up UPnP forwarding for port {self.local_port}")
            except Exception as e:
                logger.warning(f"⚠️  UPnP cleanup error: {e}") 
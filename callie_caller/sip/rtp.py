"""
RTP (Real-time Transport Protocol) handler for audio capture and playback.
Handles RTP packet parsing, audio codec conversion, and streaming.
"""

import asyncio
import logging
import socket
import struct
import threading
import time
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

from callie_caller.sip.sdp import AudioParams
from callie_caller.sip.audio_codec import ulaw_to_pcm, alaw_to_pcm, pcm_to_ulaw, resample_simple

logger = logging.getLogger(__name__)

@dataclass
class RtpPacket:
    """Parsed RTP packet structure."""
    version: int
    padding: bool
    extension: bool
    csrc_count: int
    marker: bool
    payload_type: int
    sequence_number: int
    timestamp: int
    ssrc: int
    payload: bytes

class RtpHandler:
    """Handles RTP audio stream capture and playback."""
    
    def __init__(self, audio_params: AudioParams):
        """
        Initialize RTP handler.
        
        Args:
            audio_params: Audio parameters from SDP negotiation
        """
        self.audio_params = audio_params
        self.logger = logging.getLogger(__name__)
        
        # RTP sockets
        self.receive_socket: Optional[socket.socket] = None
        self.send_socket: Optional[socket.socket] = None
        
        # Audio processing
        self.audio_callback: Optional[Callable[[bytes], None]] = None
        self.running = False
        
        # Threading
        self.receive_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.packets_received = 0
        self.packets_sent = 0
        self.bytes_received = 0
        self.bytes_sent = 0
        
        # IMPROVED: Audio buffer for jitter handling
        self.audio_buffer = []
        self.buffer_size = 5  # Buffer 5 packets (100ms at 20ms per packet)
        self.last_played_timestamp = 0
        
        # IMPROVED: Proper timestamp tracking
        self._send_timestamp_base = 0
        self._send_samples_sent = 0
        
        self.logger.info(f"RTP handler initialized for {audio_params.ip_address}:{audio_params.port}")
        self.logger.info(f"Available codecs: {[c['codec'] for c in audio_params.codecs]}")
        self.logger.info(f"🔊 Audio buffer enabled: {self.buffer_size} packets (jitter compensation)")
    
    def set_audio_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set callback function for received audio data."""
        self.audio_callback = callback
        self.logger.debug("Audio callback set")
    
    def start(self) -> bool:
        """Start RTP audio capture."""
        if self.running:
            self.logger.warning("RTP handler already running")
            return True
            
        try:
            # Create receive socket
            self.receive_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.receive_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to local port for receiving RTP
            # We'll use a dynamic port since we're sending RTP to the remote side
            self.receive_socket.bind(('', 0))  # Bind to any available port
            local_port = self.receive_socket.getsockname()[1]
            
            self.logger.info(f"🎵 RTP receive socket bound to port {local_port}")
            
            # Create send socket
            self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Start receive thread
            self.running = True
            self.receive_thread = threading.Thread(
                target=self._receive_loop,
                name="rtp-receiver",
                daemon=True
            )
            self.receive_thread.start()
            
            self.logger.info("🎤 RTP handler started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start RTP handler: {e}")
            self.stop()
            return False
    
    def stop(self) -> None:
        """Stop RTP audio capture."""
        self.logger.info("🛑 Stopping RTP handler...")
        self.running = False
        
        if self.receive_socket:
            self.receive_socket.close()
            self.receive_socket = None
            
        if self.send_socket:
            self.send_socket.close()
            self.send_socket = None
            
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2)
            
        self.logger.info("✅ RTP handler stopped")
    
    def _receive_loop(self) -> None:
        """Background thread for receiving RTP packets."""
        self.logger.info("🎧 RTP receive loop started")
        
        stats_counter = 0
        
        while self.running and self.receive_socket:
            try:
                # Set timeout to allow for graceful shutdown
                self.receive_socket.settimeout(1.0)
                
                # Receive RTP packet
                data, addr = self.receive_socket.recvfrom(2048)
                self.packets_received += 1
                self.bytes_received += len(data)
                
                # Log first few packets and periodic stats
                if self.packets_received <= 5:
                    self.logger.info(f"🎵 RTP PACKET #{self.packets_received}: {len(data)} bytes from {addr}")
                
                if len(data) < 12:  # Minimum RTP header size
                    self.logger.warning(f"Received short RTP packet: {len(data)} bytes")
                    continue
                
                # Parse RTP packet
                packet = self._parse_rtp_packet(data)
                if not packet:
                    continue
                    
                self.logger.debug(f"📨 RTP packet: PT={packet.payload_type}, seq={packet.sequence_number}, "
                                f"ts={packet.timestamp}, {len(packet.payload)} bytes")
                
                # IMPROVED: Add to buffer for jitter compensation
                if self.audio_callback and packet.payload:
                    self._add_to_audio_buffer(packet)
                    self._process_audio_buffer()
                
            except socket.timeout:
                # Periodic statistics during timeout
                stats_counter += 1
                if stats_counter % 10 == 0:  # Every 10 seconds
                    self.logger.info(f"📊 RTP Stats: {self.packets_received} packets, {self.bytes_received} bytes received")
                    if self.packets_received == 0:
                        self.logger.warning("⚠️  NO RTP PACKETS RECEIVED YET - Audio may not be flowing to our client")
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Error in RTP receive loop: {e}")
                break
        
        self.logger.info(f"🏁 RTP receive loop ended - Final stats: {self.packets_received} packets, {self.bytes_received} bytes")
    
    def _parse_rtp_packet(self, data: bytes) -> Optional[RtpPacket]:
        """Parse RTP packet from raw bytes."""
        try:
            # RTP header is 12 bytes minimum
            if len(data) < 12:
                return None
                
            # Parse fixed header (first 12 bytes)
            header = struct.unpack('!BBHII', data[:12])
            
            byte0 = header[0]
            version = (byte0 >> 6) & 0x3
            padding = bool((byte0 >> 5) & 0x1)
            extension = bool((byte0 >> 4) & 0x1)
            csrc_count = byte0 & 0xF
            
            byte1 = header[1]
            marker = bool((byte1 >> 7) & 0x1)
            payload_type = byte1 & 0x7F
            
            sequence_number = header[2]
            timestamp = header[3]
            ssrc = header[4]
            
            # Skip CSRC identifiers if present
            header_length = 12 + (csrc_count * 4)
            
            # Extract payload
            payload = data[header_length:]
            
            return RtpPacket(
                version=version,
                padding=padding,
                extension=extension,
                csrc_count=csrc_count,
                marker=marker,
                payload_type=payload_type,
                sequence_number=sequence_number,
                timestamp=timestamp,
                ssrc=ssrc,
                payload=payload
            )
            
        except Exception as e:
            self.logger.error(f"Error parsing RTP packet: {e}")
            return None
    
    def _convert_to_pcm(self, audio_data: bytes, payload_type: int) -> Optional[bytes]:
        """Convert audio data to PCM format for AI processing."""
        try:
            # Find codec for this payload type
            codec_info = None
            for codec in self.audio_params.codecs:
                if int(codec["payload"]) == payload_type:
                    codec_info = codec
                    break
            
            if not codec_info:
                self.logger.warning(f"Unknown payload type: {payload_type}")
                return None
            
            codec_name = codec_info["codec"].upper()
            
            # Convert based on codec
            if codec_name == "PCMU":
                # G.711 μ-law to linear PCM
                pcm_data = ulaw_to_pcm(audio_data)
                
            elif codec_name == "PCMA":
                # G.711 A-law to linear PCM  
                pcm_data = alaw_to_pcm(audio_data)
                
            else:
                self.logger.warning(f"Unsupported codec for conversion: {codec_name}")
                return None
            
            # Resample from 8kHz to 16kHz for AI
            resampled = resample_simple(pcm_data, 8000, 16000, 2)
            
            self.logger.debug(f"Converted {len(audio_data)} bytes {codec_name} to {len(resampled)} bytes PCM")
            return resampled
            
        except Exception as e:
            self.logger.error(f"Error converting audio: {e}")
            return None
    
    def send_audio(self, pcm_data: bytes) -> bool:
        """Send PCM audio data as RTP packets."""
        try:
            if not self.send_socket or not self.running:
                return False
            
            # Convert PCM to G.711 μ-law (payload type 0)
            # Resample from 16kHz to 8kHz first
            resampled = resample_simple(pcm_data, 16000, 8000, 2)
            ulaw_data = pcm_to_ulaw(resampled)
            
            # Create RTP packet
            rtp_packet = self._create_rtp_packet(ulaw_data, payload_type=0)
            
            # Send to remote audio endpoint
            self.send_socket.sendto(rtp_packet, (self.audio_params.ip_address, self.audio_params.port))
            
            self.packets_sent += 1
            self.bytes_sent += len(rtp_packet)
            
            self.logger.debug(f"📤 Sent RTP packet: {len(rtp_packet)} bytes")
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending RTP audio: {e}")
            return False
    
    def _create_rtp_packet(self, payload: bytes, payload_type: int = 0) -> bytes:
        """Create RTP packet with audio payload."""
        # IMPROVED: Proper timestamp handling
        if self._send_timestamp_base == 0:
            self._send_timestamp_base = int(time.time() * 8000) % (2**32)
            self._send_samples_sent = 0
            
        # RTP header fields
        version = 2
        padding = 0
        extension = 0
        csrc_count = 0
        marker = 0
        sequence_number = getattr(self, '_sequence_number', 0)
        
        # FIXED: Use sample-based timestamp instead of wall-clock
        timestamp = (self._send_timestamp_base + self._send_samples_sent) & 0xFFFFFFFF
        self._send_samples_sent += len(payload)  # Track samples for accurate timing
        
        ssrc = getattr(self, '_ssrc', 0x12345678)
        
        # Update sequence number
        self._sequence_number = (sequence_number + 1) & 0xFFFF
        
        # Pack RTP header
        byte0 = (version << 6) | (padding << 5) | (extension << 4) | csrc_count
        byte1 = (marker << 7) | payload_type
        
        header = struct.pack('!BBHII', byte0, byte1, sequence_number, timestamp, ssrc)
        
        return header + payload
    
    def _add_to_audio_buffer(self, packet: RtpPacket) -> None:
        """Add RTP packet to jitter buffer."""
        try:
            # Add packet to buffer with timestamp for ordering
            self.audio_buffer.append({
                'packet': packet,
                'arrival_time': time.time(),
                'timestamp': packet.timestamp
            })
            
            # Sort buffer by RTP timestamp to handle out-of-order packets
            self.audio_buffer.sort(key=lambda x: x['timestamp'])
            
            # Remove old packets if buffer is too large
            if len(self.audio_buffer) > self.buffer_size * 2:
                self.audio_buffer = self.audio_buffer[-self.buffer_size:]
                
        except Exception as e:
            self.logger.error(f"Error adding to audio buffer: {e}")
    
    def _process_audio_buffer(self) -> None:
        """Process buffered audio packets to reduce jitter."""
        try:
            # Wait until we have minimum buffer size
            if len(self.audio_buffer) < self.buffer_size:
                return
                
            # Process oldest packet in buffer
            buffered_item = self.audio_buffer.pop(0)
            packet = buffered_item['packet']
            
            # Convert audio format and send to callback
            pcm_audio = self._convert_to_pcm(packet.payload, packet.payload_type)
            if pcm_audio and self.audio_callback:
                self.audio_callback(pcm_audio)
                self.last_played_timestamp = packet.timestamp
                
        except Exception as e:
            self.logger.error(f"Error processing audio buffer: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RTP statistics."""
        return {
            "packets_received": self.packets_received,
            "packets_sent": self.packets_sent,
            "bytes_received": self.bytes_received,
            "bytes_sent": self.bytes_sent,
            "running": self.running,
            "audio_params": {
                "ip": self.audio_params.ip_address,
                "port": self.audio_params.port,
                "codecs": self.audio_params.codecs
            }
        } 
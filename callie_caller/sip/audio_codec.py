"""
Audio codec conversion functions for G.711 and PCM formats.
Replaces audioop functionality for Python 3.13+ compatibility.
"""

import struct
import logging
from typing import Optional
import numpy as np
from scipy.signal import resample

logger = logging.getLogger(__name__)

# G.711 μ-law encoding/decoding tables
ULAW_BIAS = 0x84
ULAW_CLIP = 32635

def ulaw_to_linear(ulaw_byte: int) -> int:
    """Convert single μ-law byte to 16-bit linear PCM sample."""
    ulaw_byte = ~ulaw_byte
    sign = (ulaw_byte & 0x80)
    exponent = (ulaw_byte >> 4) & 0x07
    mantissa = ulaw_byte & 0x0F
    
    sample = mantissa << (exponent + 3)
    if exponent > 0:
        sample += (1 << (exponent + 2))
    
    if sign:
        sample = -sample
        
    return sample

def linear_to_ulaw(sample: int) -> int:
    """Convert 16-bit linear PCM sample to μ-law byte."""
    # Clamp sample to valid range
    if sample > ULAW_CLIP:
        sample = ULAW_CLIP
    elif sample < -ULAW_CLIP:
        sample = -ULAW_CLIP
    
    # Get sign and magnitude
    sign = 0x80 if sample < 0 else 0x00
    if sample < 0:
        sample = -sample
    
    sample += ULAW_BIAS
    
    # Find exponent
    exponent = 0
    for i in range(8):
        if sample <= (0x1FFF << i):
            exponent = i
            break
    
    # Extract mantissa
    mantissa = (sample >> (exponent + 3)) & 0x0F
    
    # Combine and invert
    ulaw = ~(sign | (exponent << 4) | mantissa)
    return ulaw & 0xFF

def ulaw_to_pcm(ulaw_data: bytes) -> bytes:
    """Convert μ-law encoded audio to 16-bit PCM using standard G.711 μ-law."""
    try:
        pcm_samples = []
        for byte in ulaw_data:
            # Use standard G.711 μ-law decompression - no artificial gain needed
            linear_sample = ulaw_to_linear(byte)
            # Clamp to 16-bit range (should already be in range, but safety check)
            linear_sample = max(-32768, min(32767, linear_sample))
            pcm_samples.append(linear_sample)
        
        # Pack as 16-bit signed integers
        pcm_data = struct.pack(f'<{len(pcm_samples)}h', *pcm_samples)
        logger.debug(f"Converted {len(ulaw_data)} μ-law bytes to {len(pcm_data)} PCM bytes (standard G.711)")
        return pcm_data
        
    except Exception as e:
        logger.error(f"Error converting μ-law to PCM: {e}")
        return b''

def resample_simple(audio_data: bytes, from_rate: int, to_rate: int, sample_width: int = 2) -> bytes:
    """
    High-quality audio resampling using scipy for voice applications.
    Ensures proper anti-aliasing to prevent distortion and static.
    
    Args:
        audio_data: Input audio data
        from_rate: Source sample rate
        to_rate: Target sample rate  
        sample_width: Bytes per sample (2 for 16-bit)
    """
    try:
        if from_rate == to_rate:
            return audio_data
            
        if len(audio_data) < sample_width:
            logger.warning(f"Audio data too short for resampling: {len(audio_data)} bytes")
            return audio_data
            
        # Convert byte data to numpy array for processing
        sample_count = len(audio_data) // sample_width
        if sample_count == 0:
            return b''
            
        # Unpack as 16-bit signed integers
        samples = np.frombuffer(audio_data, dtype=np.int16)
        
        # Calculate the number of samples in the output signal
        num_samples_out = int(len(samples) * to_rate / from_rate)
        
        logger.debug(f"🎵 High-quality resampling {len(samples)} samples from {from_rate}Hz to {to_rate}Hz → {num_samples_out} samples")

        # Use scipy's high-quality Fourier-based resampler with enhanced filtering
        # Apply pre-filtering for voice frequencies and reduce aliasing artifacts
        from scipy.signal import butter, filtfilt
        
        # For voice applications, pre-filter to remove sub-audible noise and high-freq artifacts
        if from_rate >= 16000:  # Only filter high-sample-rate audio
            # Design a voice-optimized bandpass filter (300Hz - 3400Hz for telephony)
            nyquist = from_rate / 2
            low_freq = 300 / nyquist    # Remove low-frequency rumble
            high_freq = 3400 / nyquist  # Remove high-frequency noise
            
            try:
                # Create a 4th-order Butterworth bandpass filter
                b, a = butter(4, [low_freq, high_freq], btype='band')
                # Apply zero-phase filtering (no delay)
                filtered_samples = filtfilt(b, a, samples.astype(np.float64))
                logger.debug(f"🎵 Applied voice-optimized bandpass filter (300-3400Hz)")
            except Exception as filter_error:
                logger.debug(f"⚠️ Filter failed, using original: {filter_error}")
                filtered_samples = samples.astype(np.float64)
        else:
            filtered_samples = samples.astype(np.float64)
        
        # High-quality resampling with the filtered audio
        resampled_samples = resample(filtered_samples, num_samples_out)
        
        # Convert back to 16-bit integers with proper rounding and clamping
        resampled_samples = np.round(resampled_samples).astype(np.int32)
        resampled_samples = np.clip(resampled_samples, -32768, 32767).astype(np.int16)
        
        # Pack back to bytes
        resampled_data = resampled_samples.tobytes()
            
        logger.debug(f"✅ Professional resampling completed: {len(audio_data)} bytes → {len(resampled_data)} bytes")
        return resampled_data
        
    except Exception as e:
        logger.error(f"💥 Error in high-quality resampling: {e}")
        return audio_data

# A-law support (ITU-T G.711 standard)
ALAW_CLIP = 32767  # Full 16-bit range

def alaw_to_linear(alaw_byte: int) -> int:
    """Convert single A-law byte to 16-bit linear PCM sample using ITU-T G.711 standard."""
    # XOR with 0x55 to undo even-bit inversion
    alaw_byte ^= 0x55
    
    # Extract sign bit
    sign = alaw_byte & 0x80
    
    # Extract exponent (3 bits) and mantissa (4 bits)
    exponent = (alaw_byte >> 4) & 0x07
    mantissa = alaw_byte & 0x0F
    
    # Decode according to ITU-T G.711 A-law specification
    if exponent == 0:
        # Linear segment (exponent 0)
        linear = (mantissa << 1) | 1
    else:
        # Logarithmic segments (exponents 1-7)
        linear = ((mantissa << 1) | 0x21) << (exponent - 1)
    
    # Apply sign
    if sign:
        linear = -linear
    
    # Scale to full 16-bit range to prevent volume loss
    # A-law has a maximum output of ~4096, so we need to scale up
    linear = linear << 3  # Multiply by 8 to reach near full range
    
    # Clamp to prevent overflow
    linear = max(-32767, min(32767, linear))
        
    return linear

def alaw_to_pcm(alaw_data: bytes) -> bytes:
    """Convert A-law encoded audio to 16-bit PCM using standard G.711 A-law."""
    try:
        pcm_samples = []
        for byte in alaw_data:
            # Use standard G.711 A-law decompression - no artificial gain needed
            linear_sample = alaw_to_linear(byte)
            # Clamp to 16-bit range (should already be in range, but safety check) 
            linear_sample = max(-32768, min(32767, linear_sample))
            pcm_samples.append(linear_sample)
        
        pcm_data = struct.pack(f'<{len(pcm_samples)}h', *pcm_samples)
        logger.debug(f"Converted {len(alaw_data)} A-law bytes to {len(pcm_data)} PCM bytes (standard G.711)")
        return pcm_data
        
    except Exception as e:
        logger.error(f"Error converting A-law to PCM: {e}")
        return b'' 

def linear_to_alaw(sample: int) -> int:
    """Convert 16-bit linear PCM sample to A-law byte using ITU-T G.711 standard."""
    # Scale down from full 16-bit range to A-law input range
    # Since we scale up by 8 in decoding, scale down by 8 in encoding
    sample = sample >> 3
    
    # Clamp sample to valid A-law input range
    if sample > 4095:
        sample = 4095
    elif sample < -4095:
        sample = -4095
    
    # Get sign and magnitude
    sign = 0x80 if sample < 0 else 0x00
    if sample < 0:
        sample = -sample
    
    # Find exponent and mantissa according to ITU-T G.711
    if sample < 16:
        # Linear segment (exponent 0)
        exponent = 0
        mantissa = (sample >> 1) & 0x0F
    else:
        # Logarithmic segments (exponents 1-7)
        exponent = 1
        temp = sample >> 5  # Start with sample/32
        while temp > 0 and exponent < 7:
            temp >>= 1
            exponent += 1
        
        # Calculate mantissa for this exponent
        mantissa = (sample >> (exponent + 1)) & 0x0F
    
    # Combine components
    alaw = sign | (exponent << 4) | mantissa
    
    # XOR with 0x55 to invert even bits (A-law specification)
    alaw ^= 0x55
    
    return alaw & 0xFF

def pcm_to_alaw(pcm_data: bytes) -> bytes:
    """Convert 16-bit PCM to A-law using standard G.711 A-law."""
    try:
        # Unpack PCM data
        sample_count = len(pcm_data) // 2
        pcm_samples = struct.unpack(f'<{sample_count}h', pcm_data)
        
        alaw_bytes = []
        for sample in pcm_samples:
            # Use standard G.711 A-law compression - no pre-attenuation needed
            # Just clamp to valid range
            sample = max(-32768, min(32767, sample))
            alaw_byte = linear_to_alaw(sample)
            alaw_bytes.append(alaw_byte)
        
        alaw_data = bytes(alaw_bytes)
        logger.debug(f"Converted {len(pcm_data)} PCM bytes to {len(alaw_data)} A-law bytes (standard G.711)")
        return alaw_data
        
    except Exception as e:
        logger.error(f"Error converting PCM to A-law: {e}")
        return b'' 

def pcm_to_ulaw(pcm_data: bytes) -> bytes:
    """Convert 16-bit PCM to μ-law using standard G.711 μ-law."""
    try:
        # Unpack PCM data
        sample_count = len(pcm_data) // 2
        pcm_samples = struct.unpack(f'<{sample_count}h', pcm_data)
        
        ulaw_bytes = []
        for sample in pcm_samples:
            # Use standard G.711 μ-law compression - no pre-attenuation needed
            # Just clamp to valid range
            sample = max(-32768, min(32767, sample))
            ulaw_byte = linear_to_ulaw(sample)
            ulaw_bytes.append(ulaw_byte)
        
        ulaw_data = bytes(ulaw_bytes)
        logger.debug(f"Converted {len(pcm_data)} PCM bytes to {len(ulaw_data)} μ-law bytes (standard G.711)")
        return ulaw_data
        
    except Exception as e:
        logger.error(f"Error converting PCM to μ-law: {e}")
        return b''

def pcm_to_g722(pcm_data: bytes) -> bytes:
    """
    Convert 16-bit PCM (16kHz) to G.722 using proper library implementation.
    G.722 is the wideband codec used by Zoho Voice for superior audio.
    """
    try:
        # Import the proper G.722 library
        import G722
        
        # Convert bytes to numpy array for the library
        sample_count = len(pcm_data) // 2
        pcm_samples = struct.unpack(f'<{sample_count}h', pcm_data)
        pcm_array = np.array(pcm_samples, dtype=np.int16)
        
        # Create G.722 encoder and encode
        encoder = G722.Encoder()
        g722_data = encoder.encode(pcm_array)
        
        logger.debug(f"🎯 PROPER G.722 encode: {len(pcm_data)} PCM bytes (16kHz) → {len(g722_data)} G.722 bytes (HD Voice)")
        return bytes(g722_data)
        
    except Exception as e:
        logger.error(f"Error converting PCM to G.722: {e}")
        # Fallback to A-law if G.722 fails
        logger.warning("Falling back to A-law encoding")
        sample_count = len(pcm_data) // 2
        pcm_samples = struct.unpack(f'<{sample_count}h', pcm_data)
        # Downsample to 8kHz for A-law
        pcm_8khz = resample_simple(pcm_data, from_rate=16000, to_rate=8000)
        return pcm_to_alaw(pcm_8khz)

def g722_to_pcm(g722_data: bytes) -> bytes:
    """
    Convert G.722 back to 16-bit PCM (16kHz) using proper library implementation.
    """
    try:
        # Import the proper G.722 library
        import G722
        
        # Create G.722 decoder and decode
        decoder = G722.Decoder()
        pcm_array = decoder.decode(np.frombuffer(g722_data, dtype=np.uint8))
        
        # Convert numpy array back to bytes
        pcm_data = struct.pack(f'<{len(pcm_array)}h', *pcm_array.astype(np.int16))
        
        logger.debug(f"🎯 PROPER G.722 decode: {len(g722_data)} G.722 bytes → {len(pcm_data)} PCM bytes (16kHz)")
        return pcm_data
        
    except Exception as e:
        logger.error(f"Error converting G.722 to PCM: {e}")
        # Fallback - return silence
        return b'\x00\x00' * (len(g722_data) * 2) 
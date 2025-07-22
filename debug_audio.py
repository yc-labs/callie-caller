#!/usr/bin/env python3
"""
Audio Pipeline Diagnostic Tool
Tests the audio components without requiring SIP credentials.
"""

import logging
import os
import sys
import time
import asyncio
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_audio_imports():
    """Test if all audio dependencies are available."""
    logger.info("🔍 Testing audio dependencies...")
    issues = []
    
    try:
        import pyaudio
        logger.info("✅ PyAudio imported successfully")
    except ImportError as e:
        issues.append(f"❌ PyAudio import failed: {e}")
    
    try:
        import numpy
        logger.info("✅ NumPy imported successfully")
    except ImportError as e:
        issues.append(f"❌ NumPy import failed: {e}")
    
    try:
        import scipy
        logger.info("✅ SciPy imported successfully") 
    except ImportError as e:
        issues.append(f"❌ SciPy import failed: {e}")
    
    try:
        from google import genai
        logger.info("✅ Google GenAI imported successfully")
    except ImportError as e:
        issues.append(f"❌ Google GenAI import failed: {e}")
    
    return issues

def test_audio_bridge_creation():
    """Test AudioBridge creation without API key."""
    logger.info("🔍 Testing AudioBridge creation...")
    
    # Temporarily set fake API key
    original_key = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "fake_key_for_testing"
    
    try:
        from callie_caller.ai.live_client import AudioBridge
        bridge = AudioBridge()
        logger.info("✅ AudioBridge created successfully")
        
        # Test callback setup
        def dummy_callback(data):
            logger.info(f"🔊 Dummy callback received {len(data)} bytes")
            
        bridge.set_sip_audio_callback(dummy_callback)
        logger.info("✅ SIP audio callback set successfully")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ AudioBridge creation failed: {e}")
        return False
    finally:
        # Restore original key
        if original_key:
            os.environ["GEMINI_API_KEY"] = original_key
        else:
            os.environ.pop("GEMINI_API_KEY", None)

def test_rtp_bridge_creation():
    """Test RTP bridge creation."""
    logger.info("🔍 Testing RTP Bridge creation...")
    
    try:
        from callie_caller.sip.rtp_bridge import RtpBridge
        
        # Create bridge with local IP
        bridge = RtpBridge("127.0.0.1")
        logger.info("✅ RTP Bridge created successfully")
        
        # Test test mode
        success = bridge.enable_test_mode()
        if success:
            logger.info("✅ Test mode enabled successfully")
        else:
            logger.warning("⚠️ Test mode could not be enabled")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ RTP Bridge creation failed: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return False

def test_audio_codecs():
    """Test audio codec functions."""
    logger.info("🔍 Testing audio codec functions...")
    
    try:
        from callie_caller.sip.audio_codec import ulaw_to_pcm, pcm_to_ulaw, resample_simple
        
        # Test with dummy data
        dummy_ulaw = b'\x00\x01\x02\x03' * 20  # 80 bytes of dummy μ-law
        
        # Test μ-law to PCM
        pcm_data = ulaw_to_pcm(dummy_ulaw)
        logger.info(f"✅ μ-law to PCM conversion: {len(dummy_ulaw)} → {len(pcm_data)} bytes")
        
        # Test PCM to μ-law
        ulaw_data = pcm_to_ulaw(pcm_data)
        logger.info(f"✅ PCM to μ-law conversion: {len(pcm_data)} → {len(ulaw_data)} bytes")
        
        # Test resampling
        resampled = resample_simple(pcm_data, 8000, 16000, 2)
        logger.info(f"✅ Resampling 8kHz→16kHz: {len(pcm_data)} → {len(resampled)} bytes")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Audio codec test failed: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return False

def test_configuration():
    """Test configuration loading."""
    logger.info("🔍 Testing configuration...")
    
    # Set minimum required env vars
    os.environ["ZOHO_SIP_SERVER"] = "test.server.com"
    os.environ["ZOHO_SIP_USERNAME"] = "test_user"
    os.environ["ZOHO_SIP_PASSWORD"] = "test_pass"
    os.environ["GEMINI_API_KEY"] = "test_key"
    
    try:
        from callie_caller.config.settings import get_settings
        settings = get_settings()
        logger.info("✅ Configuration loaded successfully")
        logger.info(f"   SIP Server: {settings.zoho.sip_server}")
        logger.info(f"   Username: {settings.zoho.sip_username}")
        logger.info(f"   Device: {settings.device.user_agent}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration test failed: {e}")
        return False

async def test_async_audio_pipeline():
    """Test async audio pipeline components."""
    logger.info("🔍 Testing async audio pipeline...")
    
    try:
        # Set fake API key
        os.environ["GEMINI_API_KEY"] = "fake_key_for_testing"
        
        from callie_caller.ai.live_client import AudioBridge
        
        bridge = AudioBridge()
        
        # Test queue creation
        bridge.audio_in_queue = asyncio.Queue(maxsize=10)
        bridge.audio_out_queue = asyncio.Queue(maxsize=10)
        
        logger.info("✅ Audio queues created successfully")
        
        # Test sync audio sending
        dummy_audio = b'\x00' * 1920  # 40ms of silence at 24kHz
        bridge.send_sip_audio_sync(dummy_audio)
        logger.info("✅ Sync audio sending test completed")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Async audio pipeline test failed: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return False

def main():
    """Run all audio diagnostic tests."""
    logger.info("🤖 Callie Caller - Audio Pipeline Diagnostics")
    logger.info("=" * 60)
    
    # Ensure we're in the right directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Add project to Python path
    sys.path.insert(0, str(project_root))
    
    issues = []
    
    # Test 1: Dependencies
    import_issues = test_audio_imports()
    issues.extend(import_issues)
    
    # Test 2: Configuration
    if not test_configuration():
        issues.append("Configuration loading failed")
    
    # Test 3: Audio Bridge
    if not test_audio_bridge_creation():
        issues.append("AudioBridge creation failed")
    
    # Test 4: RTP Bridge
    if not test_rtp_bridge_creation():
        issues.append("RTP Bridge creation failed")
    
    # Test 5: Audio Codecs
    if not test_audio_codecs():
        issues.append("Audio codec functions failed")
    
    # Test 6: Async Pipeline
    try:
        if not asyncio.run(test_async_audio_pipeline()):
            issues.append("Async audio pipeline failed")
    except Exception as e:
        issues.append(f"Async test error: {e}")
    
    # Summary
    logger.info("=" * 60)
    logger.info("🔍 DIAGNOSTIC SUMMARY")
    
    if not issues:
        logger.info("🎉 ALL TESTS PASSED!")
        logger.info("✅ Audio pipeline appears to be working correctly")
        logger.info("🔧 Issue may be in:")
        logger.info("   • SIP credentials/connectivity")
        logger.info("   • Network configuration")
        logger.info("   • Gemini API key/connectivity")
        logger.info("   • Container networking")
    else:
        logger.error("❌ ISSUES FOUND:")
        for issue in issues:
            logger.error(f"   • {issue}")
    
    logger.info("=" * 60)
    logger.info("📋 NEXT STEPS:")
    logger.info("1. Update docker.env with your real Zoho Voice credentials")
    logger.info("2. Update docker.env with your real Gemini API key")
    logger.info("3. Run: docker-compose -f docker-compose.debug.yml up")
    logger.info("4. Check logs for SIP connection and audio flow")

if __name__ == "__main__":
    main() 
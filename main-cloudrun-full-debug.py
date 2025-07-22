#!/usr/bin/env python3
"""
Callie Caller - Cloud Run Full SIP Entry Point with Audio Debugging
This debug version enables test audio and enhanced logging to troubleshoot audio issues.
"""

import os
import sys
import logging
import time
from callie_caller.core.logging import setup_logging

# Configure debug logging first
setup_logging(level="DEBUG")
logger = logging.getLogger(__name__)

def main():
    """Main entry point for Cloud Run with full SIP capabilities and audio debugging."""
    logger.info("🤖 Callie Caller v1.0.0 - AI Voice Agent (DEBUG MODE)")
    logger.info("🔧 AUDIO DEBUG MODE ENABLED - Extra logging and test audio")
    
    # Set Cloud Run specific environment variables
    os.environ["USE_UPNP"] = "false"  # Disable UPnP in Cloud Run
    os.environ["CONTAINER_MODE"] = "true"
    os.environ["CLOUD_RUN_MODE"] = "true"
    os.environ["LOG_LEVEL"] = "DEBUG"
    
    # Ensure PORT is set correctly for Cloud Run
    if "PORT" not in os.environ:
        os.environ["PORT"] = "8080"
    
    try:
        # Import the full agent
        from callie_caller.core.agent import CallieAgent
        
        # Create and start the agent
        agent = CallieAgent()
        
        logger.info("🌐 Starting Cloud Run agent with AUDIO DEBUG capabilities...")
        logger.info("📋 Debug Configuration:")
        logger.info("   • Debug logging enabled")
        logger.info("   • Audio pipeline tracing enabled")
        logger.info("   • Voice detection logging enabled")
        logger.info("   • RTP packet analysis enabled")
        logger.info("   • Audio recording enabled")
        
        # Start the agent (this includes SIP client and web server)
        agent.start()
        
        # Enable test audio mode for debugging
        logger.info("🧪 Enabling test audio mode for debugging...")
        if agent.sip_client:
            test_enabled = agent.enable_test_audio_mode()
            if test_enabled:
                logger.info("✅ Test audio mode enabled - will inject test tones instead of AI audio")
            else:
                logger.warning("⚠️ Could not enable test audio mode")
        
        # Get port from environment (Cloud Run sets PORT)
        port = int(os.getenv("PORT", "8080"))
        
        logger.info(f"🚀 Cloud Run agent started in DEBUG mode!")
        logger.info(f"🔧 Audio debugging features active")
        logger.info(f"📞 SIP calling available via API endpoints")
        logger.info(f"🌐 Web interface: http://0.0.0.0:{port}")
        logger.info(f"🎯 Test call endpoint: POST /call with {{\"number\": \"+16782960086\"}}")
        
        # Auto-test call after startup
        logger.info("⏳ Waiting 5 seconds for system to stabilize...")
        time.sleep(5)
        
        logger.info("🚀 Making automatic test call to debug audio...")
        try:
            # Make test call with audio debugging
            success = agent.make_call(
                "+16782960086", 
                "Hello! This is Callie, your AI voice assistant. I'm testing the audio pipeline. Can you hear me?"
            )
            if success:
                logger.info("🎉 Test call initiated successfully!")
            else:
                logger.error("❌ Test call failed to initiate")
        except Exception as e:
            logger.error(f"❌ Test call error: {e}")
            import traceback
            logger.error(f"Stack trace: {traceback.format_exc()}")
        
        # Keep the application running
        try:
            # The agent's Flask server is already running in a thread
            # Just keep the main thread alive
            while True:
                time.sleep(60)
                logger.info("🔄 Cloud Run agent running in debug mode...")
                
                # Log audio status every minute
                if hasattr(agent, 'sip_client') and agent.sip_client:
                    if hasattr(agent.sip_client, 'rtp_bridge') and agent.sip_client.rtp_bridge:
                        bridge = agent.sip_client.rtp_bridge
                        logger.info(f"🎤 Audio stats: {bridge.packets_to_ai} to AI, {bridge.packets_from_ai} from AI")
                        if hasattr(bridge, 'test_mode') and bridge.test_mode:
                            logger.info("🧪 Test mode active - injecting test audio")
                
        except KeyboardInterrupt:
            logger.info("👋 Shutting down debug session gracefully...")
            agent.stop()
        
    except KeyboardInterrupt:
        logger.info("👋 Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main() 
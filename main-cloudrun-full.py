#!/usr/bin/env python3
"""
Callie Caller - Cloud Run Full SIP Entry Point
This version uses the full SIP agent optimized for Cloud Run deployment.
"""

import os
import sys
import logging
from callie_caller.core.logging import setup_logging

# Configure logging first
setup_logging()
logger = logging.getLogger(__name__)

def main():
    """Main entry point for Cloud Run with full SIP capabilities."""
    logger.info("🤖 Callie Caller v1.0.0 - AI Voice Agent (Cloud Run Full SIP Mode)")
    
    # Set Cloud Run specific environment variables
    os.environ["USE_UPNP"] = "false"  # Disable UPnP in Cloud Run
    os.environ["CONTAINER_MODE"] = "true"
    os.environ["CLOUD_RUN_MODE"] = "true"
    
    # Ensure PORT is set correctly for Cloud Run
    if "PORT" not in os.environ:
        os.environ["PORT"] = "8080"
    
    try:
        # Import the full agent
        from callie_caller.core.agent import CallieAgent
        
        # Create and start the agent
        agent = CallieAgent()
        
        logger.info("🌐 Starting Cloud Run agent with full SIP capabilities...")
        logger.info("📋 Cloud Run Configuration:")
        logger.info("   • UPnP disabled (using fixed ports)")
        logger.info("   • VPC networking enabled")
        logger.info("   • Firewall rules configured for SIP/RTP")
        logger.info("   • API endpoints available for triggering calls")
        
        # Start the agent (this includes SIP client and web server)
        agent.start()
        
        # Get port from environment (Cloud Run sets PORT)
        port = int(os.getenv("PORT", "8080"))
        
        logger.info(f"🚀 Cloud Run agent started successfully!")
        logger.info(f"📞 SIP calling available via API endpoints")
        logger.info(f"🌐 Web interface: http://0.0.0.0:{port}")
        
        # Keep the application running
        try:
            # The agent's Flask server is already running in a thread
            # Just keep the main thread alive
            import time
            while True:
                time.sleep(60)
                logger.info("🔄 Cloud Run agent running...")
        except KeyboardInterrupt:
            logger.info("👋 Shutting down gracefully...")
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
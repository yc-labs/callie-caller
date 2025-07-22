#!/usr/bin/env python3
"""
Callie Caller - Cloud Run Entry Point
This version is optimized for Cloud Run deployment without direct SIP capabilities.
"""

import os
import sys
import logging
from callie_caller.core.logging import setup_logging

# Configure logging first
setup_logging()
logger = logging.getLogger(__name__)

def main():
    """Main entry point for Cloud Run deployment."""
    logger.info("🤖 Callie Caller v1.0.0 - AI Voice Agent (Cloud Run Mode)")
    
    # Check if running in Cloud Run mode
    cloud_run_mode = os.getenv("CLOUD_RUN_MODE", "false").lower() == "true"
    if not cloud_run_mode:
        logger.warning("⚠️  Not in Cloud Run mode, switching to local development")
    
    try:
        # Import the web-only application for Cloud Run
        from callie_caller.core.web_agent import create_app
        
        # Create Flask app (web-only mode)
        app = create_app()
        
        # Get port from environment (Cloud Run sets PORT)
        port = int(os.getenv("PORT", os.getenv("FLASK_PORT", "8080")))
        host = os.getenv("FLASK_HOST", "0.0.0.0")
        
        logger.info(f"🌐 Starting web server on {host}:{port}")
        logger.info("📋 Cloud Run Limitations:")
        logger.info("   • SIP calling requires external SIP infrastructure")
        logger.info("   • Use Cloud Functions or external services for SIP")
        logger.info("   • Web API available for call management")
        
        # Start the web server
        app.run(
            host=host,
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False
        )
        
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
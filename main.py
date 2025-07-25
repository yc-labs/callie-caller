#!/usr/bin/env python3
"""
Callie Caller - Main Entry Point
Unified application for local development, Docker, and Cloud Run.
"""

import os
import sys
import argparse
import asyncio
import signal
import logging
import time

# Set environment defaults for Cloud Run before other imports
if os.getenv("K_SERVICE"):
    os.environ.setdefault("CLOUD_RUN_MODE", "true")
    os.environ.setdefault("USE_UPNP", "false")
    os.environ.setdefault("CONTAINER_MODE", "true")
    os.environ.setdefault("LOG_LEVEL", "INFO")
    os.environ.setdefault("SERVER_PORT", os.getenv("PORT", "8080"))

from callie_caller.core.agent import CallieAgent
from callie_caller.config.settings import get_settings
from callie_caller.core.logging import setup_logging
from callie_caller import __version__, get_version_info

# Setup logging at the module level
setup_logging()
logger = logging.getLogger(__name__)

# --- Graceful Shutdown Handler ---
AGENT_INSTANCE = None

def graceful_shutdown(signum, frame):
    """Signal handler for graceful shutdown."""
    logger.info("Shutdown signal received, stopping agent...")
    if AGENT_INSTANCE:
        AGENT_INSTANCE.stop()
    sys.exit(0)

# --- Main Application Logic ---
def main():
    """Main function to run the Callie Caller application."""
    parser = argparse.ArgumentParser(
        description="Callie Caller - AI Voice Agent",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  python main.py                  # Start in server mode (for Docker/Cloud Run)
  python main.py --call +123...   # Make a single test call and exit
  python main.py --version        # Show version info
"""
    )
    parser.add_argument('--version', action='store_true', help='Show version info and exit.')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging.')
    parser.add_argument('--call', type=str, help='Make a test call to a number and exit.')
    parser.add_argument('--message', type=str, default="Hello, this is a test call.", help='Message for the test call.')

    args = parser.parse_args()

    # Handle version request
    if args.version:
        info = get_version_info()
        print(f"Callie Caller v{info['version']} (Build: {info['build']}, Commit: {info['commit']})")
        return

    # Set log level from args
    if args.debug:
        logging.getLogger("callie_caller").setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled.")

    logger.info(f"🤖 Starting Callie Caller v{__version__}...")

    global AGENT_INSTANCE
    try:
        # Initialize the full agent
        logger.info("Initializing full SIP agent...")
        agent = CallieAgent()
        AGENT_INSTANCE = agent

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, graceful_shutdown)
        signal.signal(signal.SIGTERM, graceful_shutdown)

        # Start the agent (which starts the SIP client and web server in threads)
        agent.start()
        
        # --- Mode Selection ---
        if args.call:
            # Command-line call mode
            logger.info(f"📞 Making a direct call to {args.call}...")
            if agent.make_call(args.call, args.message):
                logger.info("✅ Call initiated successfully. Waiting for completion...")
                # Wait for the call to finish or timeout
                timeout = 120  # 2-minute timeout
                start_time = time.time()
                while agent.is_call_active() and time.time() - start_time < timeout:
                    time.sleep(1)
                logger.info("Call has ended.")
            else:
                logger.error("❌ Failed to initiate call.")
            agent.stop()
        else:
            # Server mode (default for Docker/Cloud Run)
            settings = get_settings()
            logger.info("🚀 Agent running in server mode.")
            registration_status = "✅" if agent.sip_client.registered else "❌"
            logger.info(f"{registration_status} SIP client registered: {agent.sip_client.registered}")
            logger.info(f"✅ Web API listening on port {settings.server.port}")
            logger.info("Press Ctrl+C to stop.")
            # Keep the main thread alive while background threads run
            while True:
                time.sleep(3600)

    except Exception as e:
        logger.error(f"❌ An unexpected error occurred: {e}", exc_info=args.debug)
        sys.exit(1)

if __name__ == "__main__":
    main() 
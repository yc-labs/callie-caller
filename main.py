#!/usr/bin/env python3
"""
Main entry point for Callie Caller - AI Voice Agent.
Run this script to start the AI voice assistant.
"""

import argparse
import asyncio
import signal
import sys
import time
import logging
from pathlib import Path

from callie_caller.core.agent import CallieAgent
from callie_caller.config.settings import get_settings
from callie_caller.core.logging import setup_logging
from callie_caller import __version__, get_version_info

logger = logging.getLogger(__name__)

class GracefulShutdown:
    """Handle graceful shutdown of the agent."""
    def __init__(self):
        self.agent = None
        self.shutdown_requested = False

    def __call__(self, signum, frame):
        if self.shutdown_requested:
            logger.warning("Force shutdown requested")
            sys.exit(1)
        
        self.shutdown_requested = True
        logger.info("Shutdown signal received, stopping Callie Agent...")
        
        if self.agent:
            try:
                self.agent.stop()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
        
        sys.exit(0)

def main():
    """Main entry point for the Callie Caller application."""
    parser = argparse.ArgumentParser(
        description="Callie Caller - AI Voice Agent for phone conversations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                     # Start the agent in server mode
  python main.py --debug            # Start with debug logging
  python main.py --config-check     # Verify configuration
  python main.py --call +1234567890 # Make a test call
  python main.py --version          # Show version information
        """
    )
    
    parser.add_argument(
        '--version',
        action='store_true',
        help='Show version information and exit'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    parser.add_argument(
        '--config-check',
        action='store_true',
        help='Check configuration and exit'
    )
    
    parser.add_argument(
        '--call',
        type=str,
        help='Make a test call to the specified number and exit'
    )
    
    parser.add_argument(
        '--message',
        type=str,
        help='Custom message for test call (used with --call)'
    )
    
    parser.add_argument(
        '--log-file',
        type=str,
        help='Log file path (default: logs to console)'
    )
    
    args = parser.parse_args()
    
    # Handle version request
    if args.version:
        version_info = get_version_info()
        print(f"Callie Caller v{version_info['version']}")
        print(f"Build: {version_info['build']}")
        if version_info['commit'] != 'unknown':
            print(f"Commit: {version_info['commit']}")
        return 0
    
    # Setup logging
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level, log_file=args.log_file)
    
    # Setup graceful shutdown
    signal_handler = GracefulShutdown()
    
    logger.info(f"🤖 Callie Caller v{__version__} - AI Voice Agent")
    
    try:
        # Configuration check
        if args.config_check:
            logger.info("Checking configuration...")
            settings = get_settings()
            logger.info("Configuration validation successful:")
            logger.info(f"  SIP Server: {settings.zoho.sip_server}")
            logger.info(f"  Username: {settings.zoho.sip_username}")
            logger.info(f"  Device: {settings.device.user_agent}")
            logger.info(f"  AI Model: {settings.ai.model}")
            return 0
        
        # Initialize agent
        logger.info("Initializing Callie Agent...")
        agent = CallieAgent()
        signal_handler.agent = agent
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start agent
        logger.info("Starting AI voice agent...")
        agent.start()
        
        # Test call mode
        if args.call:
            logger.info(f"Making test call to {args.call}")
            success = agent.make_call(args.call, args.message)
            
            if success:
                logger.info("Call completed successfully")
                return 0
            else:
                logger.error("Call failed or was not answered")
                return 1
        
        # Normal operation mode
        logger.info("Callie Agent is running!")
        logger.info(f"Device emulation: {agent.settings.device.user_agent}")
        logger.info(f"Web interface: http://localhost:{agent.settings.server.port}")
        logger.info(f"Health check: http://localhost:{agent.settings.server.port}/health")
        
        if args.debug:
            logger.debug("Available endpoints:")
            logger.debug("  GET  /health        - Health check")
            logger.debug("  POST /call          - Make outbound call")
            logger.debug("  POST /sms           - SMS webhook")
            logger.debug("  GET  /conversations - Conversation history")
            logger.debug("  GET  /stats         - Agent statistics")
        
        logger.info("Press Ctrl+C to stop")
        
        # Keep running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            signal_handler(signal.SIGINT, None)
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Application error: {e}")
        if args.debug:
            import traceback
            logger.debug(f"Stack trace: {traceback.format_exc()}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 
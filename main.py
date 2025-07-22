#!/usr/bin/env python3
"""
Main entry point for Callie Caller - AI Voice Agent.
Run this script to start the AI voice assistant.
"""

import argparse
import signal
import sys
import time
from pathlib import Path

from callie_caller.core.logging import setup_logging
from callie_caller.core.agent import CallieAgent
from callie_caller.config import get_settings


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    print("\n🛑 Shutdown signal received, stopping Callie Agent...")
    if hasattr(signal_handler, 'agent'):
        signal_handler.agent.stop()
    sys.exit(0)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Callie Caller - AI Voice Agent for Zoho Voice",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Start with default settings
  python main.py --debug            # Start with debug logging
  python main.py --log-file app.log # Log to file
  python main.py --call +1234567890 # Make a test call
        """
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    parser.add_argument(
        '--log-file',
        type=str,
        default=None,
        help='Log file path (default: console only)'
    )
    
    parser.add_argument(
        '--call',
        type=str,
        metavar='NUMBER',
        help='Make a test call to the specified number and exit'
    )
    
    parser.add_argument(
        '--message',
        type=str,
        help='Custom message for test call (used with --call)'
    )
    
    parser.add_argument(
        '--test-audio',
        action='store_true',
        help='Enable test audio mode (inject test tone instead of AI audio)'
    )
    
    parser.add_argument(
        '--test-audio-file',
        type=str,
        metavar='FILE',
        help='Use specific WAV file for test audio (implies --test-audio)'
    )
    
    parser.add_argument(
        '--config-check',
        action='store_true',
        help='Check configuration and exit'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(level=log_level, log_file=args.log_file)
    
    print("🤖 Callie Caller - AI Voice Agent")
    print("=" * 40)
    
    try:
        # Configuration check
        if args.config_check:
            print("🔍 Checking configuration...")
            settings = get_settings()
            print(f"✅ Configuration valid:")
            print(f"   SIP Server: {settings.zoho.sip_server}")
            print(f"   Username: {settings.zoho.sip_username}")
            print(f"   Device: {settings.device.user_agent}")
            print(f"   AI Model: {settings.ai.model}")
            return
        
        # Initialize agent
        print("🚀 Initializing Callie Agent...")
        agent = CallieAgent()
        signal_handler.agent = agent  # Store for signal handler
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start agent
        print("🎯 Starting AI voice agent...")
        agent.start()
        
        # Test call mode
        if args.call:
            print(f"📞 Making test call to {args.call}...")
            
            # Enable test audio mode if requested
            if args.test_audio or args.test_audio_file:
                print("🧪 Test audio mode enabled")
                if args.test_audio_file:
                    print(f"🎵 Using test audio file: {args.test_audio_file}")
                    agent.enable_test_audio_mode(args.test_audio_file)
                else:
                    print("🎵 Using generated test tone")
                    agent.enable_test_audio_mode()
            
            success = agent.make_call(args.call, args.message)
            
            if success:
                print("✅ Call completed successfully")
            else:
                print("❌ Call failed or was not answered")
                
            print("🏁 Call session ended - shutting down agent...")
            agent.stop()
            return
        
        # Normal operation mode
        print("\n🎉 Callie Agent is running!")
        print(f"📱 Device emulation: {agent.settings.device.user_agent}")
        print(f"🌐 Web interface: http://localhost:{agent.settings.server.port}")
        print(f"📊 Health check: http://localhost:{agent.settings.server.port}/health")
        print("\n📋 Available endpoints:")
        print(f"   GET  /health        - Health check")
        print(f"   POST /call          - Make outbound call")
        print(f"   POST /sms           - SMS webhook")
        print(f"   GET  /conversations - Conversation history")
        print(f"   GET  /stats         - Agent statistics")
        print("\n🔧 Press Ctrl+C to stop")
        
        # Keep running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            signal_handler(signal.SIGINT, None)
            
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main() or 0) 
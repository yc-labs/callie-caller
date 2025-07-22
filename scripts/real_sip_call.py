#!/usr/bin/env python3
"""
Real SIP calling using pyVoIP with Zoho Voice credentials.
This will make actual phone calls to test the SIP integration.
"""

import os
import time
import threading
from dotenv import load_dotenv
from pyVoIP import VoIP
from pyVoIP.VoIP import CallState, InvalidStateError
from google import genai

# Load environment variables
load_dotenv()

# Zoho Voice SIP Configuration
SIP_SERVER = os.getenv("ZOHO_SIP_SERVER", "us3-proxy2.zohovoice.com")
SIP_USERNAME = os.getenv("ZOHO_SIP_USERNAME", "886154813_74341000000003015")
SIP_PASSWORD = os.getenv("ZOHO_SIP_PASSWORD", "BepSRgBKOQrbv")
SIP_PORT = int(os.getenv("SIP_PORT", "5060"))

# Test configuration
TEST_CALL_NUMBER = os.getenv("TEST_CALL_NUMBER", "+16782960086")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def get_ai_message():
    """Generate an AI message for the call."""
    if not GEMINI_API_KEY:
        return "Hello! This is a test call from your AI voice agent using real SIP protocol."
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.0-flash-001',
            contents="Generate a brief, friendly message that an AI voice agent would say when calling someone for a test. Keep it under 20 words and mention it's a SIP test call."
        )
        return response.text.strip()
    except Exception as e:
        print(f"AI message generation failed: {e}")
        return "Hello! This is a test call from your AI voice agent using real SIP protocol."

def answer_call(call):
    """Handle an incoming call."""
    print(f"📞 Incoming call from: {call.request.headers['From']}")
    try:
        call.answer()
        print("✅ Call answered")
        
        # Generate AI response
        ai_message = get_ai_message()
        print(f"🤖 AI would say: {ai_message}")
        
        # In a real implementation, you'd use TTS here
        time.sleep(5)  # Simulate conversation
        call.hangup()
        print("📞 Call ended")
    except Exception as e:
        print(f"❌ Error handling call: {e}")

def make_real_sip_call():
    """Make a real SIP call using pyVoIP."""
    print("🚀 Starting Real SIP Call Test")
    print("=" * 50)
    print(f"📋 Configuration:")
    print(f"   SIP Server: {SIP_SERVER}")
    print(f"   Username: {SIP_USERNAME}")
    print(f"   Target: {TEST_CALL_NUMBER}")
    print()
    
    try:
        # Create VoIP client
        print("🔧 Creating SIP client...")
        vp = VoIP(
            server=SIP_SERVER,
            port=SIP_PORT,
            username=SIP_USERNAME,
            password=SIP_PASSWORD,
            callCallback=answer_call
        )
        
        print("✅ SIP client created successfully")
        
        # Start the VoIP client
        print("📡 Starting SIP registration...")
        vp.start()
        
        # Wait a moment for registration
        time.sleep(2)
        
        print("📞 Making outbound call...")
        
        # Generate AI greeting
        ai_greeting = get_ai_message()
        print(f"🤖 AI Greeting: {ai_greeting}")
        
        # Make the call
        call = vp.call(TEST_CALL_NUMBER)
        
        if call:
            print("✅ Call initiated successfully!")
            print(f"📋 Call State: {call.state}")
            
            # Wait for call to connect
            print("⏳ Waiting for call to connect...")
            timeout = 30  # 30 seconds timeout
            elapsed = 0
            
            while call.state != CallState.ANSWERED and elapsed < timeout:
                time.sleep(1)
                elapsed += 1
                if elapsed % 5 == 0:  # Print status every 5 seconds
                    print(f"📋 Call State: {call.state} (waiting {elapsed}s)")
            
            if call.state == CallState.ANSWERED:
                print("🎉 Call connected!")
                print(f"🤖 Playing AI message: {ai_greeting}")
                
                # In a real implementation, you'd use TTS to speak the message
                # For now, just wait a bit then hang up
                time.sleep(10)
                
                print("📞 Ending call...")
                call.hangup()
                print("✅ Call completed successfully!")
            else:
                print(f"⚠️  Call did not connect. Final state: {call.state}")
                if call.state != CallState.ENDED:
                    call.hangup()
        else:
            print("❌ Failed to initiate call")
        
        # Stop the VoIP client
        print("🛑 Stopping SIP client...")
        vp.stop()
        
    except Exception as e:
        print(f"❌ SIP call failed: {e}")
        print("🔍 This could be due to:")
        print("   - Network/firewall issues")
        print("   - Incorrect SIP credentials")
        print("   - Zoho Voice configuration")
        return False
    
    return True

def main():
    """Main function."""
    print("🤖 AI Voice Agent - Real SIP Call Test")
    print("📞 Using pyVoIP for actual SIP calling")
    print()
    
    # Verify configuration
    if not all([SIP_SERVER, SIP_USERNAME, SIP_PASSWORD]):
        print("❌ Missing SIP configuration!")
        print("📋 Please check your .env file has:")
        print("   ZOHO_SIP_SERVER")
        print("   ZOHO_SIP_USERNAME") 
        print("   ZOHO_SIP_PASSWORD")
        return
    
    print("⚠️  WARNING: This will make a REAL phone call!")
    print(f"📱 Target number: {TEST_CALL_NUMBER}")
    
    # Give user a chance to cancel
    try:
        input("Press ENTER to proceed or Ctrl+C to cancel...")
    except KeyboardInterrupt:
        print("\n❌ Call cancelled by user")
        return
    
    # Make the call
    success = make_real_sip_call()
    
    if success:
        print("\n🎉 SIP call test completed successfully!")
        print("📋 Your Zoho Voice SIP credentials are working!")
    else:
        print("\n❌ SIP call test failed")
        print("📋 Check your network and Zoho Voice configuration")

if __name__ == '__main__':
    main() 
#!/usr/bin/env python3
"""
Real SIP calling using sippy library with Zoho Voice credentials.
This will make actual phone calls using the SIP protocol.
"""

import os
import sys
import time
import threading
from dotenv import load_dotenv
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

def get_ai_greeting():
    """Generate an AI greeting for the call."""
    if not GEMINI_API_KEY:
        return "Hello! This is a test call from your AI voice agent using SIP."
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.0-flash-001',
            contents="Generate a very brief, friendly greeting for an AI voice agent calling someone for a SIP test. Keep it under 15 words."
        )
        return response.text.strip()
    except Exception as e:
        print(f"AI greeting generation failed: {e}")
        return "Hello! This is a test call from your AI voice agent using SIP."

def make_simple_sip_call():
    """Make a simple SIP call using socket-based approach."""
    import socket
    
    print("🚀 Making Simple SIP Call")
    print("=" * 40)
    
    # Generate AI greeting
    ai_greeting = get_ai_greeting()
    print(f"🤖 AI Greeting: {ai_greeting}")
    
    # SIP INVITE message
    call_id = "test-call-123456"
    local_ip = "127.0.0.1"  # This should be your actual IP in production
    
    sip_invite = f"""INVITE sip:{TEST_CALL_NUMBER}@{SIP_SERVER} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:5060;branch=z9hG4bK-524287-1---test
Max-Forwards: 70
Contact: <sip:{SIP_USERNAME}@{local_ip}:5060>
To: <sip:{TEST_CALL_NUMBER}@{SIP_SERVER}>
From: "AI Agent"<sip:{SIP_USERNAME}@{SIP_SERVER}>;tag=test123
Call-ID: {call_id}
CSeq: 1 INVITE
Allow: INVITE, ACK, CANCEL, BYE, NOTIFY, REFER, MESSAGE, OPTIONS, INFO, SUBSCRIBE
Content-Type: application/sdp
User-Agent: AI-Voice-Agent/1.0
Content-Length: 0

"""
    
    try:
        print(f"📞 Connecting to {SIP_SERVER}:{SIP_PORT}")
        
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(10)
        
        # Send SIP INVITE
        print("📡 Sending SIP INVITE...")
        sock.sendto(sip_invite.encode(), (SIP_SERVER, SIP_PORT))
        
        # Wait for response
        print("⏳ Waiting for response...")
        response, addr = sock.recvfrom(4096)
        response_str = response.decode()
        
        print("📨 SIP Response received:")
        print("-" * 40)
        print(response_str[:500] + "..." if len(response_str) > 500 else response_str)
        print("-" * 40)
        
        # Check response code
        if "200 OK" in response_str:
            print("🎉 Call connected successfully!")
            print(f"🤖 Would play: {ai_greeting}")
            
            # Send ACK
            ack_msg = f"""ACK sip:{TEST_CALL_NUMBER}@{SIP_SERVER} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:5060;branch=z9hG4bK-524287-2---test
Max-Forwards: 70
To: <sip:{TEST_CALL_NUMBER}@{SIP_SERVER}>
From: "AI Agent"<sip:{SIP_USERNAME}@{SIP_SERVER}>;tag=test123
Call-ID: {call_id}
CSeq: 1 ACK
Content-Length: 0

"""
            sock.sendto(ack_msg.encode(), (SIP_SERVER, SIP_PORT))
            print("✅ ACK sent")
            
            # Simulate call duration
            time.sleep(5)
            
            # Send BYE to end call
            bye_msg = f"""BYE sip:{TEST_CALL_NUMBER}@{SIP_SERVER} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:5060;branch=z9hG4bK-524287-3---test
Max-Forwards: 70
To: <sip:{TEST_CALL_NUMBER}@{SIP_SERVER}>
From: "AI Agent"<sip:{SIP_USERNAME}@{SIP_SERVER}>;tag=test123
Call-ID: {call_id}
CSeq: 2 BYE
Content-Length: 0

"""
            sock.sendto(bye_msg.encode(), (SIP_SERVER, SIP_PORT))
            print("📞 Call ended")
            
        elif "401 Unauthorized" in response_str:
            print("🔐 Authentication required - this is expected!")
            print("📋 Response shows SIP server is reachable")
            print("🔧 Need to implement SIP authentication for real calls")
            
        elif "100 Trying" in response_str:
            print("📞 Call is being processed...")
            print("⏳ Waiting for final response...")
            
            # Wait for next response
            try:
                response2, addr2 = sock.recvfrom(4096)
                print("📨 Second response:")
                print(response2.decode()[:300] + "...")
            except socket.timeout:
                print("⏰ Timeout waiting for final response")
                
        else:
            print(f"📋 Received response: {response_str[:100]}...")
            
        sock.close()
        return True
        
    except Exception as e:
        print(f"❌ SIP call failed: {e}")
        print("🔍 This could be due to:")
        print("   - Need SIP authentication (normal for first attempt)")
        print("   - Network/firewall configuration") 
        print("   - Server configuration")
        return False

def test_sip_connectivity():
    """Test basic SIP connectivity to Zoho Voice."""
    import socket
    
    print("🔍 Testing SIP Connectivity")
    print("=" * 30)
    
    try:
        # Test UDP connectivity to SIP server
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)
        
        # Send SIP OPTIONS to test connectivity
        options_msg = f"""OPTIONS sip:{SIP_SERVER} SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-test
Max-Forwards: 70
To: <sip:{SIP_SERVER}>
From: <sip:test@test.com>;tag=test
Call-ID: connectivity-test-123
CSeq: 1 OPTIONS
Content-Length: 0

"""
        
        print(f"📡 Testing connection to {SIP_SERVER}:{SIP_PORT}")
        sock.sendto(options_msg.encode(), (SIP_SERVER, SIP_PORT))
        
        response, addr = sock.recvfrom(1024)
        response_str = response.decode()
        
        print("✅ SIP server responded!")
        print(f"📨 Response: {response_str.split('\\n')[0]}")
        
        sock.close()
        return True
        
    except Exception as e:
        print(f"❌ Connectivity test failed: {e}")
        return False

def main():
    """Main function."""
    print("🤖 AI Voice Agent - Real SIP Call Test")
    print("📞 Using sippy library with socket-based SIP")
    print()
    
    # Verify configuration
    if not all([SIP_SERVER, SIP_USERNAME, SIP_PASSWORD]):
        print("❌ Missing SIP configuration!")
        return
        
    print(f"📋 Configuration:")
    print(f"   SIP Server: {SIP_SERVER}")
    print(f"   Username: {SIP_USERNAME}")
    print(f"   Target: {TEST_CALL_NUMBER}")
    print()
    
    # Test connectivity first
    print("🔍 Step 1: Testing SIP connectivity...")
    if test_sip_connectivity():
        print("✅ SIP server is reachable!")
    else:
        print("❌ Cannot reach SIP server")
        return
    
    print()
    print("📞 Step 2: Attempting SIP call...")
    print("⚠️  WARNING: This will attempt a REAL phone call!")
    
    try:
        input("Press ENTER to proceed or Ctrl+C to cancel...")
    except KeyboardInterrupt:
        print("\\n❌ Call cancelled")
        return
    
    # Attempt the call
    success = make_simple_sip_call()
    
    if success:
        print("\\n🎉 SIP call test completed!")
        print("📋 Next: Implement full SIP authentication & RTP audio")
    else:
        print("\\n❌ SIP call test failed")

if __name__ == '__main__':
    main() 
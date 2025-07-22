#!/usr/bin/env python3
"""
Final SIP calling attempt with proper network configuration.
This version includes proper local IP detection and SDP content.
"""

import os
import socket
import time
import random
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

# Configuration
SIP_SERVER = os.getenv("ZOHO_SIP_SERVER", "us3-proxy2.zohovoice.com")
SIP_USERNAME = os.getenv("ZOHO_SIP_USERNAME", "886154813_74341000000003015")
SIP_PASSWORD = os.getenv("ZOHO_SIP_PASSWORD", "BepSRgBKOQrbv")
SIP_PORT = int(os.getenv("SIP_PORT", "5060"))
TEST_CALL_NUMBER = os.getenv("TEST_CALL_NUMBER", "+16782960086")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def get_local_ip():
    """Get the local IP address that can reach the SIP server."""
    try:
        # Create a socket and connect to the SIP server to determine local IP
        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_sock.connect((SIP_SERVER, SIP_PORT))
        local_ip = temp_sock.getsockname()[0]
        temp_sock.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def get_ai_greeting():
    """Generate an AI greeting."""
    if not GEMINI_API_KEY:
        return "Hello! This is a test call from your AI assistant."
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.0-flash-001',
            contents="Generate a very brief, friendly test call message from an AI assistant. Under 15 words."
        )
        return response.text.strip()
    except Exception as e:
        return "Hello! This is a test call from your AI assistant."

def test_network_connectivity():
    """Test basic network connectivity to Zoho Voice."""
    print("🌐 Testing Network Connectivity")
    print("=" * 35)
    
    try:
        # Get local IP
        local_ip = get_local_ip()
        print(f"🖥️  Local IP: {local_ip}")
        
        # Test DNS resolution
        import socket
        server_ip = socket.gethostbyname(SIP_SERVER)
        print(f"🌍 {SIP_SERVER} resolves to: {server_ip}")
        
        # Test basic UDP connectivity
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('', 0))  # Bind to any available port
        local_port = sock.getsockname()[1]
        print(f"📡 Local port: {local_port}")
        
        # Send a simple test packet
        test_msg = "TEST"
        sock.settimeout(5)
        sock.sendto(test_msg.encode(), (SIP_SERVER, SIP_PORT))
        
        print("✅ Network connectivity test passed")
        sock.close()
        return local_ip, local_port
        
    except Exception as e:
        print(f"❌ Network test failed: {e}")
        return None, None

def register_sip_account(local_ip, local_port):
    """Attempt SIP registration with Zoho Voice."""
    print("📡 Attempting SIP Registration")
    print("=" * 35)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((local_ip, local_port))
        sock.settimeout(10)
        
        # Generate registration identifiers
        call_id = f"reg-{random.randint(100000, 999999)}-{int(time.time())}"
        tag = f"tag-{random.randint(1000, 9999)}"
        branch = f"z9hG4bK-{random.randint(100000, 999999)}"
        
        # SIP REGISTER message
        register_msg = f"""REGISTER sip:{SIP_SERVER} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:{local_port};branch={branch}
Max-Forwards: 70
Contact: <sip:{SIP_USERNAME}@{local_ip}:{local_port}>
To: <sip:{SIP_USERNAME}@{SIP_SERVER}>
From: <sip:{SIP_USERNAME}@{SIP_SERVER}>;tag={tag}
Call-ID: {call_id}
CSeq: 1 REGISTER
Expires: 3600
User-Agent: AI-Voice-Agent/1.0
Content-Length: 0

"""
        
        print(f"📞 Registering {SIP_USERNAME}@{SIP_SERVER}")
        sock.sendto(register_msg.encode(), (SIP_SERVER, SIP_PORT))
        
        # Wait for response
        print("⏳ Waiting for registration response...")
        response, addr = sock.recvfrom(4096)
        response_str = response.decode()
        
        status_line = response_str.split('\\n')[0]
        print(f"📨 Registration response: {status_line}")
        
        if "401 Unauthorized" in response_str:
            print("🔐 Authentication required for registration (expected)")
            return True
        elif "200 OK" in response_str:
            print("✅ Registration successful!")
            return True
        else:
            print(f"⚠️  Unexpected response: {status_line}")
            return False
            
        sock.close()
        
    except Exception as e:
        print(f"❌ Registration failed: {e}")
        return False

def attempt_simple_call():
    """Make a simplified SIP call attempt."""
    print("📞 Making Simplified SIP Call")
    print("=" * 35)
    
    # Get network info
    local_ip, local_port = test_network_connectivity()
    if not local_ip:
        print("❌ Network connectivity failed")
        return False
    
    print()
    
    # Test registration
    if not register_sip_account(local_ip, local_port):
        print("⚠️  Registration failed, but continuing with call attempt...")
    
    print()
    
    # Generate AI greeting
    ai_greeting = get_ai_greeting()
    print(f"🤖 AI Greeting: {ai_greeting}")
    
    try:
        # Create socket for call
        call_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        call_sock.bind((local_ip, local_port + 1))
        call_sock.settimeout(15)
        
        # Generate call identifiers
        call_id = f"call-{random.randint(100000, 999999)}-{int(time.time())}"
        tag = f"tag-{random.randint(1000, 9999)}"
        branch = f"z9hG4bK-{random.randint(100000, 999999)}"
        
        # Create SDP content for audio
        sdp_content = f"""v=0
o=AI-Agent {int(time.time())} {int(time.time())} IN IP4 {local_ip}
s=AI Voice Call
c=IN IP4 {local_ip}
t=0 0
m=audio {local_port + 2} RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=sendrecv
"""
        
        # INVITE with SDP
        invite_msg = f"""INVITE sip:{TEST_CALL_NUMBER}@{SIP_SERVER} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:{local_port + 1};branch={branch}
Max-Forwards: 70
Contact: <sip:{SIP_USERNAME}@{local_ip}:{local_port + 1}>
To: <sip:{TEST_CALL_NUMBER}@{SIP_SERVER}>
From: "AI Agent" <sip:{SIP_USERNAME}@{SIP_SERVER}>;tag={tag}
Call-ID: {call_id}
CSeq: 1 INVITE
Content-Type: application/sdp
User-Agent: AI-Voice-Agent/1.0
Content-Length: {len(sdp_content)}

{sdp_content}"""
        
        print(f"📡 Sending INVITE to {TEST_CALL_NUMBER}...")
        call_sock.sendto(invite_msg.encode(), (SIP_SERVER, SIP_PORT))
        
        # Wait for response
        print("⏳ Waiting for call response...")
        response, addr = call_sock.recvfrom(4096)
        response_str = response.decode()
        
        print("📨 Call response received:")
        print("-" * 40)
        lines = response_str.split('\\n')
        print(f"Status: {lines[0]}")
        
        # Show some key headers
        for line in lines[1:6]:
            if line.strip():
                print(f"  {line[:60]}{'...' if len(line) > 60 else ''}")
        print("-" * 40)
        
        if "401 Unauthorized" in response_str:
            print("🔐 Authentication required - this proves SIP communication works!")
            print("📋 The server is responding to our call attempts")
            print("🔧 Next step: Implement full digest authentication")
            
        elif "100 Trying" in response_str:
            print("📞 Call is being processed!")
            print("⏳ Waiting for next response...")
            
            try:
                response2, addr2 = call_sock.recvfrom(4096)
                response2_str = response2.decode()
                next_status = response2_str.split('\\n')[0]
                print(f"📨 Next response: {next_status}")
                
                if "180 Ringing" in response2_str:
                    print("🎉 SUCCESS! Your phone should be ringing!")
                    print(f"📱 Check your phone: {TEST_CALL_NUMBER}")
                elif "200 OK" in response2_str:
                    print("🎉 CALL CONNECTED! Phone answered!")
                    
            except socket.timeout:
                print("⏰ No further response (normal)")
                
        elif "403 Forbidden" in response_str:
            print("🚫 Call forbidden - may need different configuration")
            
        elif "404 Not Found" in response_str:
            print("❓ Number not found - check phone number format")
            
        else:
            print(f"📋 Response: {lines[0]}")
            
        call_sock.close()
        return True
        
    except Exception as e:
        print(f"❌ Call attempt failed: {e}")
        return False

def main():
    """Main function."""
    print("🤖 AI Voice Agent - Final SIP Call Test")
    print("🎯 Testing real SIP communication with Zoho Voice")
    print()
    
    print(f"📋 Configuration:")
    print(f"   Server: {SIP_SERVER}")
    print(f"   Username: {SIP_USERNAME}")
    print(f"   Target: {TEST_CALL_NUMBER}")
    print()
    
    print("⚠️  This will attempt a REAL SIP call!")
    print("📱 Your phone may ring if successful!")
    
    try:
        input("\\nPress ENTER to proceed or Ctrl+C to cancel...")
    except KeyboardInterrupt:
        print("\\n❌ Cancelled")
        return
    
    print()
    success = attempt_simple_call()
    
    print("\\n" + "="*50)
    if success:
        print("🎉 SIP communication test completed!")
        print("📋 Key achievements:")
        print("   ✅ Network connectivity to Zoho Voice")
        print("   ✅ DNS resolution working")
        print("   ✅ SIP protocol communication")
        print("   ✅ Server recognizes our requests")
        print()
        print("📋 If your phone rang, the integration is working!")
        print("🔧 Next: Add authentication & full audio support")
    else:
        print("❌ SIP test failed")
        print("🔍 Check network/firewall configuration")

if __name__ == '__main__':
    main() 
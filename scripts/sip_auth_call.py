#!/usr/bin/env python3
"""
SIP calling with digest authentication for Zoho Voice.
This implements proper SIP authentication to make real calls.
"""

import os
import socket
import hashlib
import time
import random
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
        return "Hello! This is your AI voice agent calling to test our SIP connection. Have a great day!"
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.0-flash-001',
            contents="Generate a brief, friendly message for an AI voice agent calling to test a SIP connection. Keep it natural and under 20 words."
        )
        return response.text.strip()
    except Exception as e:
        print(f"AI greeting generation failed: {e}")
        return "Hello! This is your AI voice agent calling to test our SIP connection. Have a great day!"

def generate_nonce():
    """Generate a random nonce for SIP authentication."""
    return f"{random.randint(100000, 999999)}{int(time.time())}"

def md5_hash(text):
    """Generate MD5 hash."""
    return hashlib.md5(text.encode()).hexdigest()

def calculate_response(username, realm, password, method, uri, nonce):
    """Calculate digest authentication response."""
    ha1 = md5_hash(f"{username}:{realm}:{password}")
    ha2 = md5_hash(f"{method}:{uri}")
    response = md5_hash(f"{ha1}:{nonce}:{ha2}")
    return response

def parse_www_authenticate(auth_header):
    """Parse WWW-Authenticate header to extract realm and nonce."""
    realm = ""
    nonce = ""
    
    # Extract realm
    if 'realm="' in auth_header:
        start = auth_header.find('realm="') + 7
        end = auth_header.find('"', start)
        realm = auth_header[start:end]
    
    # Extract nonce  
    if 'nonce="' in auth_header:
        start = auth_header.find('nonce="') + 7
        end = auth_header.find('"', start)
        nonce = auth_header[start:end]
    
    return realm, nonce

def make_authenticated_sip_call():
    """Make an authenticated SIP call to Zoho Voice."""
    print("🔐 Making Authenticated SIP Call")
    print("=" * 45)
    
    # Generate AI greeting
    ai_greeting = get_ai_greeting()
    print(f"🤖 AI Greeting: {ai_greeting}")
    
    # Generate unique identifiers
    call_id = f"call-{random.randint(100000, 999999)}-{int(time.time())}"
    tag = f"tag-{random.randint(1000, 9999)}"
    branch = f"z9hG4bK-{random.randint(100000, 999999)}"
    
    try:
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(15)
        
        print(f"📞 Connecting to {SIP_SERVER}:{SIP_PORT}")
        
        # Step 1: Send initial INVITE (will get 401 Unauthorized)
        invite_uri = f"sip:{TEST_CALL_NUMBER}@{SIP_SERVER}"
        from_header = f'"AI Agent" <sip:{SIP_USERNAME}@{SIP_SERVER}>;tag={tag}'
        to_header = f"<sip:{TEST_CALL_NUMBER}@{SIP_SERVER}>"
        
        initial_invite = f"""INVITE {invite_uri} SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5060;branch={branch}
Max-Forwards: 70
Contact: <sip:{SIP_USERNAME}@127.0.0.1:5060>
To: {to_header}
From: {from_header}
Call-ID: {call_id}
CSeq: 1 INVITE
Allow: INVITE, ACK, CANCEL, BYE, NOTIFY, REFER, MESSAGE, OPTIONS, INFO, SUBSCRIBE
Content-Type: application/sdp
User-Agent: AI-Voice-Agent/1.0
Content-Length: 0

"""
        
        print("📡 Sending initial INVITE...")
        sock.sendto(initial_invite.encode(), (SIP_SERVER, SIP_PORT))
        
        # Wait for 401 Unauthorized response
        print("⏳ Waiting for authentication challenge...")
        response, addr = sock.recvfrom(4096)
        response_str = response.decode()
        
        print("📨 SIP Response received:")
        print("-" * 50)
        first_line = response_str.split('\\n')[0]
        print(f"Status: {first_line}")
        
        if "401 Unauthorized" in response_str:
            print("🔐 Authentication challenge received (expected)")
            
            # Extract WWW-Authenticate header
            auth_header = ""
            for line in response_str.split('\\n'):
                if line.startswith('WWW-Authenticate:'):
                    auth_header = line
                    break
            
            if auth_header:
                print(f"🔑 Auth header: {auth_header[:80]}...")
                
                # Parse authentication parameters
                realm, nonce = parse_www_authenticate(auth_header)
                print(f"🏰 Realm: {realm}")
                print(f"🎲 Nonce: {nonce[:20]}...")
                
                if realm and nonce:
                    # Step 2: Send authenticated INVITE
                    print("🔐 Calculating authentication response...")
                    
                    method = "INVITE"
                    uri = invite_uri
                    auth_response = calculate_response(
                        SIP_USERNAME, realm, SIP_PASSWORD, method, uri, nonce
                    )
                    
                    # Create Authorization header
                    auth_header_value = f'Digest username="{SIP_USERNAME}", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{auth_response}"'
                    
                    # Send authenticated INVITE
                    auth_invite = f"""INVITE {invite_uri} SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5060;branch={branch}-auth
Max-Forwards: 70
Contact: <sip:{SIP_USERNAME}@127.0.0.1:5060>
To: {to_header}
From: {from_header}
Call-ID: {call_id}
CSeq: 2 INVITE
Authorization: {auth_header_value}
Allow: INVITE, ACK, CANCEL, BYE, NOTIFY, REFER, MESSAGE, OPTIONS, INFO, SUBSCRIBE
Content-Type: application/sdp
User-Agent: AI-Voice-Agent/1.0
Content-Length: 0

"""
                    
                    print("📡 Sending authenticated INVITE...")
                    sock.sendto(auth_invite.encode(), (SIP_SERVER, SIP_PORT))
                    
                    # Wait for response
                    print("⏳ Waiting for call response...")
                    try:
                        response2, addr2 = sock.recvfrom(4096)
                        response2_str = response2.decode()
                        
                        print("📨 Authenticated response:")
                        print("-" * 50)
                        status_line = response2_str.split('\\n')[0]
                        print(f"Status: {status_line}")
                        
                        if "200 OK" in response2_str:
                            print("🎉 CALL CONNECTED SUCCESSFULLY!")
                            print(f"📞 Your phone ({TEST_CALL_NUMBER}) should be ringing!")
                            print(f"🤖 AI would say: {ai_greeting}")
                            
                            # Send ACK to complete call setup
                            ack_msg = f"""ACK {invite_uri} SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5060;branch={branch}-ack
Max-Forwards: 70
To: {to_header}
From: {from_header}
Call-ID: {call_id}
CSeq: 2 ACK
Content-Length: 0

"""
                            sock.sendto(ack_msg.encode(), (SIP_SERVER, SIP_PORT))
                            print("✅ ACK sent - call established!")
                            
                            # Simulate call duration
                            print("📞 Call in progress...")
                            time.sleep(10)
                            
                            # End the call
                            bye_msg = f"""BYE {invite_uri} SIP/2.0
Via: SIP/2.0/UDP 127.0.0.1:5060;branch={branch}-bye
Max-Forwards: 70
To: {to_header}
From: {from_header}
Call-ID: {call_id}
CSeq: 3 BYE
Content-Length: 0

"""
                            sock.sendto(bye_msg.encode(), (SIP_SERVER, SIP_PORT))
                            print("📞 Call ended")
                            
                        elif "100 Trying" in response2_str:
                            print("📞 Call is being processed...")
                            print("⏳ Waiting for final response...")
                            
                            # Wait for final response
                            try:
                                response3, addr3 = sock.recvfrom(4096)
                                final_response = response3.decode()
                                final_status = final_response.split('\\n')[0]
                                print(f"📨 Final response: {final_status}")
                                
                                if "180 Ringing" in final_response:
                                    print("📱 Phone is ringing! Check your phone!")
                                elif "200 OK" in final_response:
                                    print("🎉 Call answered!")
                                    
                            except socket.timeout:
                                print("⏰ Timeout waiting for final response")
                                
                        else:
                            print(f"📋 Unexpected response: {status_line}")
                            
                    except socket.timeout:
                        print("⏰ Timeout waiting for authenticated response")
                        
                else:
                    print("❌ Could not parse authentication parameters")
            else:
                print("❌ No WWW-Authenticate header found")
                
        elif "100 Trying" in response_str:
            print("📞 Call is being processed without authentication...")
            
        else:
            print(f"📋 Unexpected initial response: {first_line}")
            
        sock.close()
        return True
        
    except Exception as e:
        print(f"❌ Authenticated SIP call failed: {e}")
        return False

def main():
    """Main function."""
    print("🤖 AI Voice Agent - Authenticated SIP Call")
    print("🔐 Using digest authentication with Zoho Voice")
    print()
    
    print(f"📋 Configuration:")
    print(f"   SIP Server: {SIP_SERVER}")
    print(f"   Username: {SIP_USERNAME}")
    print(f"   Target: {TEST_CALL_NUMBER}")
    print()
    
    print("🚨 WARNING: This will attempt to make a REAL phone call!")
    print(f"📱 Your phone ({TEST_CALL_NUMBER}) may ring!")
    print()
    
    try:
        input("Press ENTER to make the call or Ctrl+C to cancel...")
    except KeyboardInterrupt:
        print("\\n❌ Call cancelled")
        return
    
    # Make the authenticated call
    success = make_authenticated_sip_call()
    
    if success:
        print("\\n🎉 Authenticated SIP call test completed!")
        print("📋 If your phone rang, the SIP integration is working!")
    else:
        print("\\n❌ Authenticated SIP call failed")

if __name__ == '__main__':
    main() 
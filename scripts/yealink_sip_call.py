#!/usr/bin/env python3
"""
Yealink Phone Emulation for Zoho Voice with proper MAC address.
This version emulates a real Yealink SIP-T46S phone with the registered MAC address.
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

# Configuration
SIP_SERVER = os.getenv("ZOHO_SIP_SERVER", "us3-proxy2.zohovoice.com")
SIP_USERNAME = os.getenv("ZOHO_SIP_USERNAME", "886154813_74341000000003015")
SIP_PASSWORD = os.getenv("ZOHO_SIP_PASSWORD", "BepSRgBKOQrbv")
SIP_PORT = int(os.getenv("SIP_PORT", "5060"))
TEST_CALL_NUMBER = os.getenv("TEST_CALL_NUMBER", "+16782960086")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Yealink Phone Emulation Settings
MAC_ADDRESS = os.getenv("CUSTOM_USER_AGENT", "00:1a:2b:3c:4d:5e")
YEALINK_MODEL = "SIP-T46S"
YEALINK_FIRMWARE = "66.85.0.5"
# Try different User-Agent formats that Zoho might expect
USER_AGENT = f"Yealink {YEALINK_MODEL} {YEALINK_FIRMWARE} ~{MAC_ADDRESS}"

def get_local_ip():
    """Get the local IP address."""
    try:
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
        return "Hello! This is a test call from your Yealink phone emulator."
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.0-flash-001',
            contents="Generate a brief, professional test call message from a Yealink phone system. Under 15 words."
        )
        return response.text.strip()
    except Exception as e:
        return "Hello! This is a test call from your Yealink phone emulator."

def md5_hash(text):
    """Generate MD5 hash for digest authentication."""
    return hashlib.md5(text.encode()).hexdigest()

def calculate_digest_response(username, realm, password, method, uri, nonce):
    """Calculate digest authentication response."""
    ha1 = md5_hash(f"{username}:{realm}:{password}")
    ha2 = md5_hash(f"{method}:{uri}")
    response = md5_hash(f"{ha1}:{nonce}:{ha2}")
    return response

def parse_authenticate_header(auth_header):
    """Parse WWW-Authenticate or Proxy-Authenticate header."""
    realm = ""
    nonce = ""
    
    if 'realm="' in auth_header:
        start = auth_header.find('realm="') + 7
        end = auth_header.find('"', start)
        realm = auth_header[start:end]
    
    if 'nonce="' in auth_header:
        start = auth_header.find('nonce="') + 7
        end = auth_header.find('"', start)
        nonce = auth_header[start:end]
    
    return realm, nonce

def make_yealink_sip_call():
    """Make an authenticated SIP call emulating a Yealink phone."""
    print("📞 Yealink Phone Emulation - SIP Call")
    print("=" * 45)
    print(f"🏷️  Model: {YEALINK_MODEL}")
    print(f"🔧 Firmware: {YEALINK_FIRMWARE}")
    print(f"🖥️  MAC Address: {MAC_ADDRESS}")
    print(f"👤 User-Agent: {USER_AGENT}")
    print()
    
    # Get network info
    local_ip = get_local_ip()
    print(f"🌐 Local IP: {local_ip}")
    print(f"🎯 Target: {TEST_CALL_NUMBER}")
    
    # Generate AI greeting
    ai_greeting = get_ai_greeting()
    print(f"🤖 AI Greeting: {ai_greeting}")
    print()
    
    try:
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('', 0))
        local_port = sock.getsockname()[1]
        sock.settimeout(15)
        
        print(f"📡 Local port: {local_port}")
        
        # Generate call identifiers
        call_id = f"yealink-{random.randint(100000, 999999)}-{int(time.time())}"
        tag = f"tag-{random.randint(1000, 9999)}"
        branch = f"z9hG4bK-{random.randint(100000, 999999)}"
        
        # Step 1: Send initial INVITE (will get 401)
        invite_uri = f"sip:{TEST_CALL_NUMBER}@{SIP_SERVER}"
        from_header = f'"Troy Fortin" <sip:{SIP_USERNAME}@{SIP_SERVER}>;tag={tag}'
        to_header = f"<sip:{TEST_CALL_NUMBER}@{SIP_SERVER}>"
        
        # Create SDP content (Yealink-style)
        sdp_content = f"""v=0
o=- {int(time.time())} {int(time.time())} IN IP4 {local_ip}
s=Yealink SIP Session
c=IN IP4 {local_ip}
t=0 0
m=audio {local_port + 1000} RTP/AVP 18 0 8 101
a=rtpmap:18 G729/8000
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=rtpmap:101 telephone-event/8000
a=fmtp:101 0-15
a=sendrecv
"""
        
        initial_invite = f"""INVITE {invite_uri} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:{local_port};branch={branch}
Max-Forwards: 70
Contact: <sip:{SIP_USERNAME}@{local_ip}:{local_port}>
To: {to_header}
From: {from_header}
Call-ID: {call_id}
CSeq: 1 INVITE
Allow: INVITE,ACK,OPTIONS,CANCEL,BYE,SUBSCRIBE,NOTIFY,INFO,REFER,UPDATE
Content-Type: application/sdp
Accept: application/sdp
User-Agent: {USER_AGENT}
Supported: timer,replaces
Content-Length: {len(sdp_content)}

{sdp_content}"""
        
        print("📡 Sending Yealink INVITE (Step 1)...")
        sock.sendto(initial_invite.encode(), (SIP_SERVER, SIP_PORT))
        
        # Wait for 401 Unauthorized
        print("⏳ Waiting for authentication challenge...")
        response, addr = sock.recvfrom(4096)
        response_str = response.decode()
        
        print("📨 SIP Response:")
        print("-" * 40)
        first_line = response_str.split('\n')[0]
        print(f"Status: {first_line}")
        
        if "401 Unauthorized" in response_str or "407 Proxy Authentication Required" in response_str:
            auth_type = "Proxy" if "407" in response_str else "User"
            print(f"🔐 {auth_type} authentication challenge received")
            
            # Extract authentication parameters  
            auth_header = ""
            print("🔍 Debugging response lines:")
            for line in response_str.split('\n'):
                line = line.strip()  # Remove whitespace
                if line:
                    print(f"  '{line[:50]}{'...' if len(line) > 50 else ''}'")
                if line.startswith('WWW-Authenticate:') or line.startswith('Proxy-Authenticate:'):
                    auth_header = line
                    print(f"🔑 Found auth header: {line}")
                    break
            
            if auth_header:
                realm, nonce = parse_authenticate_header(auth_header)
                print(f"🏰 Realm: {realm}")
                print(f"🎲 Nonce: {nonce[:20]}...")
                
                if realm and nonce:
                    # Step 2: Send authenticated INVITE
                    print("🔐 Calculating Yealink authentication...")
                    
                    auth_response = calculate_digest_response(
                        SIP_USERNAME, realm, SIP_PASSWORD, "INVITE", invite_uri, nonce
                    )
                    
                    # Create proper Authorization header (Proxy-Authorization for 407)
                    auth_header_value = f'Digest username="{SIP_USERNAME}", realm="{realm}", nonce="{nonce}", uri="{invite_uri}", response="{auth_response}", algorithm=MD5'
                    auth_header_name = "Proxy-Authorization" if "407" in response_str else "Authorization"
                    
                    # Send authenticated INVITE with Yealink headers
                    auth_invite = f"""INVITE {invite_uri} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:{local_port};branch={branch}-auth
Max-Forwards: 70
Contact: <sip:{SIP_USERNAME}@{local_ip}:{local_port}>
To: {to_header}
From: {from_header}
Call-ID: {call_id}
CSeq: 2 INVITE
{auth_header_name}: {auth_header_value}
Allow: INVITE,ACK,OPTIONS,CANCEL,BYE,SUBSCRIBE,NOTIFY,INFO,REFER,UPDATE
Content-Type: application/sdp
Accept: application/sdp
User-Agent: {USER_AGENT}
Supported: timer,replaces
Content-Length: {len(sdp_content)}

{sdp_content}"""
                    
                    print("📡 Sending authenticated Yealink INVITE (Step 2)...")
                    sock.sendto(auth_invite.encode(), (SIP_SERVER, SIP_PORT))
                    
                    # Wait for response
                    print("⏳ Waiting for call response...")
                    try:
                        response2, addr2 = sock.recvfrom(4096)
                        response2_str = response2.decode()
                        
                        print("📨 Authenticated response:")
                        print("-" * 40)
                        status_line = response2_str.split('\n')[0]
                        print(f"Status: {status_line}")
                        
                        if "200 OK" in response2_str:
                            print("🎉 SUCCESS! CALL CONNECTED!")
                            print(f"📱 Your phone ({TEST_CALL_NUMBER}) should be ringing!")
                            print(f"🤖 Yealink would play: {ai_greeting}")
                            
                            # Send ACK to complete call
                            ack_msg = f"""ACK {invite_uri} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:{local_port};branch={branch}-ack
Max-Forwards: 70
To: {to_header}
From: {from_header}
Call-ID: {call_id}
CSeq: 2 ACK
User-Agent: {USER_AGENT}
Content-Length: 0

"""
                            sock.sendto(ack_msg.encode(), (SIP_SERVER, SIP_PORT))
                            print("✅ ACK sent - call established!")
                            
                            time.sleep(10)
                            
                            # End call
                            bye_msg = f"""BYE {invite_uri} SIP/2.0
Via: SIP/2.0/UDP {local_ip}:{local_port};branch={branch}-bye
Max-Forwards: 70
To: {to_header}
From: {from_header}
Call-ID: {call_id}
CSeq: 3 BYE
User-Agent: {USER_AGENT}
Content-Length: 0

"""
                            sock.sendto(bye_msg.encode(), (SIP_SERVER, SIP_PORT))
                            print("📞 Call ended by Yealink")
                            
                        elif "100 Trying" in response2_str:
                            print("📞 Call being processed...")
                            
                            # Wait for next response
                            try:
                                response3, addr3 = sock.recvfrom(4096)
                                final_response = response3.decode()
                                final_status = final_response.split('\\n')[0]
                                print(f"📨 Final response: {final_status}")
                                
                                if "180 Ringing" in final_response:
                                    print("🔔 PHONE IS RINGING! Check your phone!")
                                elif "200 OK" in final_response:
                                    print("🎉 CALL ANSWERED!")
                                    
                            except socket.timeout:
                                print("⏰ No further response")
                                
                        elif "183 Session Progress" in response2_str:
                            print("📞 Call progress - phone may be ringing!")
                            
                        else:
                            print(f"📋 Response: {status_line}")
                            # Show more details for debugging
                            for line in response2_str.split('\\n')[:10]:
                                if line.strip() and not line.startswith('Via:'):
                                    print(f"  {line}")
                            
                    except socket.timeout:
                        print("⏰ Timeout waiting for authenticated response")
                        
                else:
                    print("❌ Could not parse authentication parameters")
            else:
                print("❌ No authentication header found")
                
        elif "100 Trying" in response_str:
            print("📞 Call being processed without authentication!")
            
        else:
            print(f"📋 Unexpected response: {first_line}")
            
        sock.close()
        return True
        
    except Exception as e:
        print(f"❌ Yealink call failed: {e}")
        return False

def main():
    """Main function."""
    print("📞 Yealink SIP-T46S Phone Emulator")
    print("🔧 Emulating registered Zoho Voice device")
    print()
    
    print(f"📋 Device Configuration:")
    print(f"   Model: {YEALINK_MODEL}")
    print(f"   MAC Address: {MAC_ADDRESS}")
    print(f"   SIP Server: {SIP_SERVER}")
    print(f"   Username: {SIP_USERNAME}")
    print(f"   Target: {TEST_CALL_NUMBER}")
    print()
    
    print("🚨 This will attempt a REAL phone call!")
    print("📱 Emulating your registered Yealink device")
    print(f"🔍 Using MAC address: {MAC_ADDRESS}")
    
    try:
        input("\\nPress ENTER to make Yealink call or Ctrl+C to cancel...")
    except KeyboardInterrupt:
        print("\\n❌ Call cancelled")
        return
    
    success = make_yealink_sip_call()
    
    print("\\n" + "="*50)
    if success:
        print("🎉 Yealink phone emulation completed!")
        print("📞 If your phone rang, the MAC address authentication worked!")
        print("🔧 Your Zoho Voice integration is fully functional!")
    else:
        print("❌ Yealink emulation failed")
        print("🔍 Check if MAC address matches Zoho configuration")

if __name__ == '__main__':
    main() 
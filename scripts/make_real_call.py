#!/usr/bin/env python3
"""
Make a real call using Zoho Voice API instead of SIP.
This bypasses the need for PJSIP compilation.
"""

import requests
import os
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

# Zoho Voice API Configuration
# You'll need to get these from your Zoho Voice settings
ZOHO_API_ENDPOINT = "https://voice.zoho.com/api/v1"
ZOHO_ACCESS_TOKEN = os.getenv("ZOHO_ACCESS_TOKEN", "")  # You'll need to get this
ZOHO_PHONE_NUMBER = os.getenv("ZOHO_PHONE_NUMBER", "")  # Your Zoho Voice number

# Test call configuration
TEST_CALL_NUMBER = os.getenv("TEST_CALL_NUMBER", "+16782960086")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def get_ai_greeting():
    """Generate an AI greeting for the call."""
    if not GEMINI_API_KEY:
        return "Hello! This is a test call from your AI voice agent."
    
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.0-flash-001',
            contents="Generate a friendly, professional greeting for an AI voice agent calling someone. Keep it under 30 words."
        )
        return response.text
    except Exception as e:
        print(f"AI greeting failed: {e}")
        return "Hello! This is a test call from your AI voice agent."

def make_zoho_call(to_number, message):
    """Make a call using Zoho Voice API."""
    if not ZOHO_ACCESS_TOKEN:
        print("❌ ZOHO_ACCESS_TOKEN not configured")
        print("📋 To get your Zoho Voice API token:")
        print("   1. Go to Zoho Voice admin panel")
        print("   2. Settings → API → Generate Access Token")
        print("   3. Add ZOHO_ACCESS_TOKEN to your .env file")
        return False
    
    # Zoho Voice API call endpoint
    url = f"{ZOHO_API_ENDPOINT}/calls/outbound"
    
    headers = {
        "Authorization": f"Zoho-oauthtoken {ZOHO_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": ZOHO_PHONE_NUMBER,
        "to": to_number,
        "message": message,
        "call_type": "voice"
    }
    
    try:
        print(f"📞 Making call to {to_number}...")
        print(f"💬 Message: {message}")
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Call initiated successfully!")
            print(f"📋 Call ID: {result.get('call_id', 'N/A')}")
            return True
        else:
            print(f"❌ Call failed: {response.status_code}")
            print(f"📋 Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Call failed with exception: {e}")
        return False

def simulate_sip_call():
    """Simulate what a real SIP call would look like."""
    print("\n🔄 Simulating SIP call (what PJSIP would do):")
    print("📞 Registering with us3-proxy2.zohovoice.com...")
    print("📞 Username: 886154813_74341000000003015")
    print("✅ SIP Registration successful")
    print(f"📞 Dialing {TEST_CALL_NUMBER}...")
    print("🔊 Call connected - would start audio stream")
    print("🎤 AI would convert speech-to-text")
    print("🧠 AI would generate responses")
    print("🔊 AI would convert text-to-speech")
    print("📞 Call completed")

def main():
    """Main function to make a real call."""
    print("🤖 AI Voice Agent - Real Call Test")
    print("="*50)
    
    # Generate AI greeting
    greeting = get_ai_greeting()
    print(f"🧠 AI Generated Greeting: {greeting}")
    
    print(f"\n📱 Target Number: {TEST_CALL_NUMBER}")
    
    # Try Zoho API call first
    print("\n--- Attempting Zoho Voice API Call ---")
    if make_zoho_call(TEST_CALL_NUMBER, greeting):
        print("🎉 Real call made successfully!")
    else:
        print("⚠️  Zoho API call failed - showing SIP simulation instead")
        simulate_sip_call()
    
    print("\n📋 Next Steps for Full SIP Integration:")
    print("   1. Compile PJSIP (see README.md)")
    print("   2. Implement real SIP registration")
    print("   3. Add Speech-to-Text / Text-to-Speech")

if __name__ == '__main__':
    main() 
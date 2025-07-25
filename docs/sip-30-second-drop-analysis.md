# SIP 30-Second Call Drop Analysis

## Problem Summary
All calls drop at approximately 30 seconds (actually ~15-20 seconds after answer) with no BYE message from Zoho.

## Root Causes Identified

### 1. ✅ FIXED: False Session Timer Advertisement
- **Issue**: We advertised `Supported: timer` in INVITE but didn't implement RFC 4028
- **Fix**: Removed the false advertisement from `callie_caller/sip/call.py`

### 2. ✅ FIXED: RTP Endpoint Confusion  
- **Issue**: We were overwriting the SDP endpoint with the packet source address
- **Fix**: Keep SDP endpoint for outbound, track inbound source separately

### 3. ✅ IMPLEMENTED: Continuous RTP Stream
- **Issue**: We only sent RTP when AI was speaking
- **Fix**: Added silence injection to maintain continuous RTP stream

### 4. ❌ REMAINING: NAT/Firewall Issue
- **Symptom**: We're sending RTP packets but Zoho stops sending audio after ~19 seconds
- **Evidence**: 1600+ silence packets sent, but no incoming audio after 19s
- **Likely Cause**: NAT is blocking our outbound RTP packets from reaching Zoho

## Current Status
- Calls still drop at ~19 seconds after answer
- We ARE sending continuous RTP (both AI audio and silence)
- Zoho stops sending us audio, suggesting they're not receiving our packets

## Next Steps

### 1. Implement Proper NAT Traversal
- Use STUN to discover public IP/port
- Implement symmetric RTP (send from same port we advertise)
- Consider ICE candidates

### 2. Verify RTP Packet Format
- Ensure SSRC is consistent
- Verify sequence numbers are correct
- Check timestamp progression

### 3. Add RTCP Support
- Send RTCP SR (Sender Reports) 
- This might be required by Zoho

### 4. SIP-Level Keepalive
- Send periodic OPTIONS or re-INVITE
- Some providers require this in addition to RTP

## Testing Notes
- Legacy SIP implementation (USE_PJSUA2=false)
- Docker container on macOS with --network host
- Zoho Voice as SIP provider
- Symmetric RTP endpoints observed (same IP:port for send/receive) 
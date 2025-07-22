#!/usr/bin/env python3
"""
Configure Router with UPnP for Callie Caller
Automatically sets up port forwarding for SIP/RTP, then shows Cloud Run firewall setup.
"""

import subprocess
import sys
import time
from pathlib import Path

# Add the project to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    import miniupnpc
except ImportError:
    print("❌ miniupnpc not installed. Installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "miniupnpc"], check=True)
    import miniupnpc

def discover_upnp_router():
    """Discover UPnP-enabled router."""
    print("🔍 Discovering UPnP router...")
    
    upnp = miniupnpc.UPnP()
    upnp.discoverdelay = 200
    
    devices = upnp.discover()
    print(f"📡 Found {devices} UPnP device(s)")
    
    if devices == 0:
        print("❌ No UPnP devices found")
        return None
    
    upnp.selectigd()
    
    # Get router info
    external_ip = upnp.externalipaddress()
    print(f"🌐 Router External IP: {external_ip}")
    print(f"🏠 Router Model: {upnp.statusinfo()}")
    
    return upnp

def get_local_ip():
    """Get local machine IP."""
    try:
        # Use the same method as the main app
        import socket
        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        temp_sock.connect(("8.8.8.8", 80))
        local_ip = temp_sock.getsockname()[0]
        temp_sock.close()
        return local_ip
    except Exception:
        return "10.0.0.130"  # Fallback

def configure_port_forwarding(upnp, local_ip):
    """Configure port forwarding for Callie Caller."""
    print(f"🔧 Configuring port forwarding to {local_ip}...")
    
    # Define ports to forward
    ports_config = [
        (5060, "UDP", "Callie-SIP-Signaling"),
        (10000, "UDP", "Callie-RTP-Primary"),
        (10001, "UDP", "Callie-RTP-Backup"),
        (10002, "UDP", "Callie-RTP-Extra1"),
        (10003, "UDP", "Callie-RTP-Extra2"),
        (10004, "UDP", "Callie-RTP-Extra3"),
        (8080, "TCP", "Callie-Web-Interface"),
    ]
    
    success_count = 0
    
    for port, protocol, description in ports_config:
        try:
            # Check if port is already forwarded
            existing = upnp.getspecificportmapping(port, protocol)
            if existing:
                print(f"⚠️  Port {port}/{protocol} already forwarded to {existing[0]}:{existing[1]}")
                # Remove existing mapping
                upnp.deleteportmapping(port, protocol)
                print(f"🗑️  Removed existing mapping for {port}/{protocol}")
            
            # Add new port forwarding
            result = upnp.addportmapping(
                port,           # external port
                protocol,       # protocol
                local_ip,       # internal IP
                port,           # internal port
                description,    # description
                ""              # remote host (empty = any)
            )
            
            if result:
                print(f"✅ {port}/{protocol} → {local_ip}:{port} ({description})")
                success_count += 1
            else:
                print(f"❌ Failed to forward {port}/{protocol}")
                
        except Exception as e:
            print(f"❌ Error configuring {port}/{protocol}: {e}")
    
    print(f"\n🎉 Successfully configured {success_count}/{len(ports_config)} port forwards")
    return success_count > 0

def show_firewall_rules(external_ip):
    """Show Google Cloud firewall rules for Cloud Run."""
    print("\n" + "="*60)
    print("🔥 GOOGLE CLOUD FIREWALL RULES FOR CLOUD RUN")
    print("="*60)
    
    print(f"""
📋 Run these commands to set up Cloud Run firewall rules:

# Create firewall rule for SIP signaling
gcloud compute firewall-rules create callie-sip-signaling \\
    --allow udp:5060 \\
    --source-ranges 0.0.0.0/0 \\
    --description "Callie Caller SIP signaling port" \\
    --target-tags callie-caller

# Create firewall rule for RTP audio ports
gcloud compute firewall-rules create callie-rtp-audio \\
    --allow udp:10000-10004 \\
    --source-ranges 0.0.0.0/0 \\
    --description "Callie Caller RTP audio ports" \\
    --target-tags callie-caller

# Create firewall rule for web interface (optional)
gcloud compute firewall-rules create callie-web-interface \\
    --allow tcp:8080 \\
    --source-ranges 0.0.0.0/0 \\
    --description "Callie Caller web interface" \\
    --target-tags callie-caller

# For Cloud Run specifically, you'll also need:
gcloud run services update callie-caller \\
    --port 8080 \\
    --allow-unauthenticated \\
    --region us-central1

📝 IMPORTANT NOTES:
- Cloud Run doesn't support UDP directly for SIP/RTP
- For production SIP calling, consider using:
  1. Google Compute Engine VM with static IP
  2. Google Kubernetes Engine (GKE) 
  3. Cloud NAT with static external IP
  
🏠 LOCAL TESTING (Router configured):
Your router is now configured for local Docker testing.
External IP: {external_ip}
Ports forwarded: 5060/UDP, 10000-10004/UDP, 8080/TCP

🐳 LOCAL DOCKER DEPLOYMENT:
./setup-static-ports.sh deploy
""")

def show_port_status(upnp):
    """Show current port forwarding status."""
    print("\n📊 CURRENT PORT FORWARDING STATUS:")
    print("="*50)
    
    callie_ports = [5060, 8080, 10000, 10001, 10002, 10003, 10004]
    
    for port in callie_ports:
        for protocol in ["UDP", "TCP"]:
            try:
                mapping = upnp.getspecificportmapping(port, protocol)
                if mapping:
                    print(f"✅ {port:5}/{protocol} → {mapping[0]}:{mapping[1]} ({mapping[2]})")
                else:
                    print(f"⚪ {port:5}/{protocol} → Not configured")
            except:
                print(f"⚪ {port:5}/{protocol} → Not configured")

def main():
    print("🤖 Callie Caller - UPnP Router Configuration")
    print("=" * 50)
    
    # Get local IP
    local_ip = get_local_ip()
    print(f"📍 Local Machine IP: {local_ip}")
    
    # Discover router
    upnp = discover_upnp_router()
    if not upnp:
        print("\n❌ Could not find UPnP router. Please configure ports manually:")
        print("   Ports needed: 5060/UDP, 10000-10004/UDP, 8080/TCP")
        return 1
    
    external_ip = upnp.externalipaddress()
    
    # Show current status
    show_port_status(upnp)
    
    # Ask for confirmation
    print(f"\n⚠️  This will configure port forwarding to {local_ip}")
    response = input("Continue? (y/N): ").strip().lower()
    
    if response != 'y':
        print("❌ Configuration cancelled")
        return 1
    
    # Configure ports
    success = configure_port_forwarding(upnp, local_ip)
    
    if success:
        print("\n✅ Router configuration complete!")
        show_port_status(upnp)
        show_firewall_rules(external_ip)
        
        print("\n🚀 NEXT STEPS:")
        print("1. Test local Docker: ./setup-static-ports.sh deploy")
        print("2. For Cloud Run: Use the firewall commands shown above")
        print("3. Consider using Compute Engine for full SIP/RTP support")
        
        return 0
    else:
        print("❌ Router configuration failed")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
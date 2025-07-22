#!/usr/bin/env python3
"""
Callie Caller - UPnP Router Configuration
Automatically configures router port forwarding for SIP/RTP traffic
"""

import subprocess
import sys
import time
from pathlib import Path

# Add the project to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    import miniupnpc
except ImportError:
    print("❌ miniupnpc not installed. Installing...")
    subprocess.run([sys.executable, "-m", "pip", "install", "miniupnpc"], check=True)
    import miniupnpc

def get_local_ip():
    """Get the local IP address."""
    try:
        result = subprocess.run(['ifconfig'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if 'inet ' in line and '127.0.0.1' not in line and 'inet 169.254' not in line:
                return line.split()[1]
    except:
        pass
    return "192.168.1.100"  # fallback

def discover_upnp_router():
    """Discover UPnP-enabled router."""
    print("🔍 Discovering UPnP router...")
    
    upnp = miniupnpc.UPnP()
    upnp.discoverdelay = 200
    
    devices = upnp.discover()
    if devices == 0:
        print("❌ No UPnP devices found!")
        return None
    
    print(f"✅ Found {devices} UPnP device(s)")
    
    upnp.selectigd()
    print(f"✅ Connected to router: {upnp.lanaddr}")
    return upnp

def configure_ports(upnp, local_ip):
    """Configure required ports for Callie Caller."""
    ports_config = [
        (5060, "UDP", "SIP Signaling"),
        (10000, "UDP", "Primary RTP Audio"),
        (10001, "UDP", "Backup RTP Audio"), 
        (10002, "UDP", "Additional RTP Audio"),
        (10003, "UDP", "Additional RTP Audio"),
        (10004, "UDP", "Additional RTP Audio"),
    ]
    
    print(f"\n🔧 Configuring ports for IP: {local_ip}")
    print("=" * 50)
    
    for port, protocol, description in ports_config:
        try:
            # Remove existing mapping if any
            upnp.deleteportmapping(port, protocol)
            
            # Add new mapping
            result = upnp.addportmapping(
                port,           # external port
                protocol,       # protocol
                local_ip,       # internal IP
                port,           # internal port
                description,    # description
                ""              # remote host (empty = any)
            )
            
            if result:
                print(f"✅ {protocol} {port:5d} -> {local_ip}:{port:5d} | {description}")
            else:
                print(f"❌ Failed to map {protocol} {port}")
                
        except Exception as e:
            print(f"❌ Error mapping {protocol} {port}: {e}")
    
    print("=" * 50)

def show_cloud_run_setup():
    """Show Google Cloud Run firewall setup commands."""
    print("\n☁️  GOOGLE CLOUD RUN SETUP")
    print("=" * 50)
    print("Run these commands to set up Google Cloud firewall:")
    print()
    print("# Create firewall rules for SIP/RTP traffic")
    print("gcloud compute firewall-rules create callie-sip-signaling \\")
    print("  --allow udp:5060 \\")
    print("  --source-ranges 0.0.0.0/0 \\")
    print("  --description 'Callie Caller SIP signaling port' \\")
    print("  --target-tags callie-caller")
    print()
    print("gcloud compute firewall-rules create callie-rtp-audio \\")
    print("  --allow udp:10000-10004 \\")
    print("  --source-ranges 0.0.0.0/0 \\")
    print("  --description 'Callie Caller RTP audio ports' \\")
    print("  --target-tags callie-caller")
    print()
    print("Note: Cloud Run has UDP limitations. Use Compute Engine or GKE for full SIP support.")
    print("=" * 50)

def main():
    print("🌐 CALLIE CALLER - UPnP ROUTER CONFIGURATION")
    print("=" * 50)
    
    # Get local IP
    local_ip = get_local_ip()
    print(f"📍 Local IP detected: {local_ip}")
    
    # Discover and configure router
    upnp = discover_upnp_router()
    if not upnp:
        print("❌ Cannot configure router automatically.")
        print("   Please configure ports manually on your router:")
        print(f"   UDP 5060, 10000-10004 -> {local_ip}")
        return 1
    
    # Configure ports
    configure_ports(upnp, local_ip)
    
    # Show Cloud setup
    show_cloud_run_setup()
    
    print("\n🎉 Router configuration complete!")
    print("   Your router is now configured for Callie Caller.")
    print("   You can now run Docker or deploy to Cloud Run.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 
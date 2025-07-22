import subprocess
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def get_public_ip() -> Optional[str]:
    """
    Retrieves the public IP address of the machine using an external service.
    This is crucial for NAT traversal, as this IP will be advertised in the SDP
    so the remote party knows where to send RTP (audio) packets.
    """
    try:
        # Using 'curl' to an external service is a common way to find the public IP.
        # We use a short timeout to prevent long delays.
        ip = subprocess.check_output(
            ['curl', '-s', '--max-time', '3', 'https://api.ipify.org'],
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        
        # Basic validation of the result
        if ip and '.' in ip:
            logger.info(f"🌍 Public IP discovered: {ip}")
            return ip
        logger.warning("Failed to parse public IP from service response.")
        return None
    except FileNotFoundError:
        logger.warning("curl command not found, cannot determine public IP.")
        return None
    except subprocess.CalledProcessError:
        logger.warning("Calling public IP service failed.")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while getting public IP: {e}")
        return None


class UPnPManager:
    """Manages UPnP port forwarding for NAT traversal."""
    
    def __init__(self):
        self.upnp = None
        self.forwarded_ports = []
        self.enabled = False
        
    def initialize(self) -> bool:
        """Initialize UPnP and discover router."""
        try:
            import miniupnpc
            
            self.upnp = miniupnpc.UPnP()
            self.upnp.discoverdelay = 2000  # 2 seconds
            
            logger.info("🔍 Discovering UPnP devices...")
            device_count = self.upnp.discover()
            
            if device_count > 0:
                logger.info(f"📡 Found {device_count} UPnP device(s)")
                
                # Select the first valid IGD (Internet Gateway Device)
                self.upnp.selectigd()
                
                # Get external IP to verify connection
                external_ip = self.upnp.externalipaddress()
                local_ip = self.upnp.lanaddr
                
                logger.info(f"🌐 UPnP Router found:")
                logger.info(f"   • External IP: {external_ip}")
                logger.info(f"   • Local IP: {local_ip}")
                logger.info(f"   • Router: {getattr(self.upnp, 'statusinfo', 'Unknown')}")
                
                self.enabled = True
                return True
            else:
                logger.warning("⚠️  No UPnP devices found - router may not support UPnP")
                return False
                
        except ImportError:
            logger.error("❌ miniupnpc library not installed. Install with: pip install miniupnpc")
            return False
        except Exception as e:
            logger.error(f"❌ UPnP initialization failed: {e}")
            return False
    
    def forward_port(self, port: int, protocol: str = 'UDP', description: str = 'Callie RTP') -> bool:
        """
        Forward a specific port through UPnP.
        
        Args:
            port: Port number to forward
            protocol: Protocol (UDP/TCP)
            description: Description for the forwarding rule
            
        Returns:
            True if successful
        """
        if not self.enabled or not self.upnp:
            return False
            
        try:
            # Add port mapping
            success = self.upnp.addportmapping(
                port,           # external port
                protocol,       # protocol
                self.upnp.lanaddr,  # internal IP
                port,           # internal port
                description,    # description
                ''              # remote host (empty for all)
            )
            
            if success:
                logger.info(f"✅ UPnP port forwarding: {protocol} {port} → {self.upnp.lanaddr}:{port}")
                self.forwarded_ports.append((port, protocol))
                return True
            else:
                logger.warning(f"⚠️  UPnP port forwarding failed for {protocol} {port}")
                return False
                
        except Exception as e:
            logger.error(f"❌ UPnP port forwarding error: {e}")
            return False
    
    def forward_port_range(self, start_port: int, end_port: int, protocol: str = 'UDP') -> Tuple[int, int]:
        """
        Forward a range of ports through UPnP.
        
        Args:
            start_port: Start of port range
            end_port: End of port range
            protocol: Protocol (UDP/TCP)
            
        Returns:
            Tuple of (successful_forwards, total_attempted)
        """
        if not self.enabled:
            return (0, 0)
            
        successful = 0
        total = end_port - start_port + 1
        
        logger.info(f"🔄 Setting up UPnP port forwarding for {protocol} ports {start_port}-{end_port}")
        
        for port in range(start_port, end_port + 1):
            if self.forward_port(port, protocol, f'Callie RTP {port}'):
                successful += 1
            
        logger.info(f"📊 UPnP forwarding complete: {successful}/{total} ports configured")
        return (successful, total)
    
    def remove_port(self, port: int, protocol: str = 'UDP') -> bool:
        """Remove a port forwarding rule."""
        if not self.enabled or not self.upnp:
            return False
            
        try:
            success = self.upnp.deleteportmapping(port, protocol)
            if success:
                logger.info(f"🗑️  Removed UPnP forwarding for {protocol} {port}")
                self.forwarded_ports = [(p, prot) for p, prot in self.forwarded_ports if not (p == port and prot == protocol)]
            return success
        except Exception as e:
            logger.error(f"❌ Error removing UPnP forwarding: {e}")
            return False
    
    def cleanup(self) -> None:
        """Remove all port forwarding rules created by this session."""
        if not self.enabled or not self.upnp:
            return
            
        logger.info("🧹 Cleaning up UPnP port forwarding rules...")
        
        for port, protocol in self.forwarded_ports[:]:
            try:
                self.upnp.deleteportmapping(port, protocol)
                logger.info(f"🗑️  Removed {protocol} {port}")
            except Exception as e:
                logger.warning(f"⚠️  Failed to remove {protocol} {port}: {e}")
        
        self.forwarded_ports.clear()
        logger.info("✅ UPnP cleanup complete")
    
    def list_existing_mappings(self) -> list:
        """List existing port mappings (for debugging)."""
        if not self.enabled or not self.upnp:
            return []
            
        mappings = []
        try:
            i = 0
            while True:
                mapping = self.upnp.getgenericportmapping(i)
                if mapping is None:
                    break
                mappings.append(mapping)
                i += 1
        except Exception:
            pass  # End of list
            
        return mappings

# Global UPnP manager instance
upnp_manager = UPnPManager() 
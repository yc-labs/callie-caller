"""
Firebase service for managing multi-tenant SIP configurations.
Handles user onboarding, SIP config storage, and retrieval.
"""

import os
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

logger = logging.getLogger(__name__)

@dataclass
class UserSipConfig:
    """User-specific SIP configuration."""
    user_id: str
    display_name: str
    sip_username: str
    sip_password: str
    sip_server: str = "sip.zoho.com"
    sip_port: int = 5060
    account_label: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Set timestamps if not provided."""
        now = datetime.now(timezone.utc)
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now

@dataclass
class UserDeviceConfig:
    """User-specific device emulation settings."""
    user_id: str
    mac_address: str
    model: str = "SIP-T46S"
    firmware: str = "66.85.0.5"
    custom_user_agent: Optional[str] = None
    
    @property
    def user_agent(self) -> str:
        """Generate proper Yealink User-Agent string."""
        if self.custom_user_agent:
            return self.custom_user_agent
        return f"Yealink {self.model} {self.firmware} ~{self.mac_address}"

@dataclass
class UserCallSettings:
    """User-specific call handling settings."""
    user_id: str
    default_greeting: str = "Hello! This is an AI assistant. How can I help you today?"
    max_call_duration: int = 1800  # 30 minutes
    answer_timeout: int = 30
    # RTP port configuration for NAT traversal
    rtp_port_min: int = 10000
    rtp_port_max: int = 10100
    use_fixed_rtp_port: bool = True

@dataclass
class UserConfiguration:
    """Complete user configuration combining all settings."""
    sip: UserSipConfig
    device: UserDeviceConfig
    calls: UserCallSettings
    
    @property
    def user_id(self) -> str:
        """Get the user ID."""
        return self.sip.user_id

class FirebaseConfigService:
    """Service for managing user configurations in Firebase."""
    
    def __init__(self, service_account_path: Optional[str] = None):
        """
        Initialize Firebase service.
        
        Args:
            service_account_path: Path to Firebase service account JSON file.
                                If None, uses GOOGLE_APPLICATION_CREDENTIALS env var.
        """
        self.db: Optional[firestore.Client] = None
        self._initialize_firebase(service_account_path)
    
    def _initialize_firebase(self, service_account_path: Optional[str]) -> None:
        """Initialize Firebase Admin SDK."""
        try:
            # Check if Firebase is already initialized
            try:
                firebase_admin.get_app()
                logger.info("Firebase already initialized")
            except ValueError:
                # Initialize Firebase
                if service_account_path and os.path.exists(service_account_path):
                    cred = credentials.Certificate(service_account_path)
                    firebase_admin.initialize_app(cred)
                    logger.info(f"Firebase initialized with service account: {service_account_path}")
                else:
                    # Use default credentials (GOOGLE_APPLICATION_CREDENTIALS)
                    firebase_admin.initialize_app()
                    logger.info("Firebase initialized with default credentials")
            
            # Get Firestore client
            self.db = firestore.client()
            logger.info("Firestore client initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise
    
    def create_user_config(self, user_config: UserConfiguration) -> bool:
        """
        Create a new user configuration.
        
        Args:
            user_config: Complete user configuration
            
        Returns:
            True if successful, False otherwise
        """
        try:
            user_id = user_config.user_id
            
            # Check if user already exists
            existing = self.get_user_config(user_id)
            if existing:
                logger.warning(f"User {user_id} already exists")
                return False
            
            # Convert to dict with timestamps
            config_dict = {
                'sip': asdict(user_config.sip),
                'device': asdict(user_config.device),
                'calls': asdict(user_config.calls),
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            # Store in Firestore
            self.db.collection('user_configs').document(user_id).set(config_dict)
            
            logger.info(f"Created user configuration for {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create user config for {user_config.user_id}: {e}")
            return False
    
    def get_user_config(self, user_id: str) -> Optional[UserConfiguration]:
        """
        Get user configuration by ID.
        
        Args:
            user_id: User identifier
            
        Returns:
            UserConfiguration if found, None otherwise
        """
        try:
            doc_ref = self.db.collection('user_configs').document(user_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                logger.debug(f"User config not found for {user_id}")
                return None
            
            data = doc.to_dict()
            
            # Reconstruct UserConfiguration
            sip_config = UserSipConfig(**data['sip'])
            device_config = UserDeviceConfig(**data['device'])
            call_config = UserCallSettings(**data['calls'])
            
            return UserConfiguration(
                sip=sip_config,
                device=device_config,
                calls=call_config
            )
            
        except Exception as e:
            logger.error(f"Failed to get user config for {user_id}: {e}")
            return None
    
    def update_user_config(self, user_config: UserConfiguration) -> bool:
        """
        Update existing user configuration.
        
        Args:
            user_config: Updated user configuration
            
        Returns:
            True if successful, False otherwise
        """
        try:
            user_id = user_config.user_id
            
            # Convert to dict with updated timestamp
            config_dict = {
                'sip': asdict(user_config.sip),
                'device': asdict(user_config.device),
                'calls': asdict(user_config.calls),
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            # Update in Firestore
            self.db.collection('user_configs').document(user_id).update(config_dict)
            
            logger.info(f"Updated user configuration for {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update user config for {user_id}: {e}")
            return False
    
    def delete_user_config(self, user_id: str) -> bool:
        """
        Delete user configuration.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.db.collection('user_configs').document(user_id).delete()
            logger.info(f"Deleted user configuration for {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete user config for {user_id}: {e}")
            return False
    
    def list_active_users(self) -> List[str]:
        """
        Get list of active user IDs.
        
        Returns:
            List of active user IDs
        """
        try:
            docs = self.db.collection('user_configs').where(
                filter=FieldFilter("sip.is_active", "==", True)
            ).stream()
            
            return [doc.id for doc in docs]
            
        except Exception as e:
            logger.error(f"Failed to list active users: {e}")
            return []
    
    def get_user_by_sip_username(self, sip_username: str) -> Optional[UserConfiguration]:
        """
        Find user configuration by SIP username.
        
        Args:
            sip_username: SIP username to search for
            
        Returns:
            UserConfiguration if found, None otherwise
        """
        try:
            docs = self.db.collection('user_configs').where(
                filter=FieldFilter("sip.sip_username", "==", sip_username)
            ).limit(1).stream()
            
            for doc in docs:
                data = doc.to_dict()
                sip_config = UserSipConfig(**data['sip'])
                device_config = UserDeviceConfig(**data['device'])
                call_config = UserCallSettings(**data['calls'])
                
                return UserConfiguration(
                    sip=sip_config,
                    device=device_config,
                    calls=call_config
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to find user by SIP username {sip_username}: {e}")
            return None

# Global service instance
_firebase_service: Optional[FirebaseConfigService] = None

def get_firebase_service() -> FirebaseConfigService:
    """Get global Firebase service instance (singleton pattern)."""
    global _firebase_service
    if _firebase_service is None:
        service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
        _firebase_service = FirebaseConfigService(service_account_path)
    return _firebase_service

def create_sample_user_config(
    user_id: str,
    display_name: str,
    sip_username: str,
    sip_password: str,
    mac_address: str
) -> UserConfiguration:
    """
    Create a sample user configuration for testing/onboarding.
    
    Args:
        user_id: Unique user identifier
        display_name: User's display name
        sip_username: SIP username (usually phone number or extension)
        sip_password: SIP password
        mac_address: MAC address for device emulation
        
    Returns:
        UserConfiguration instance
    """
    sip_config = UserSipConfig(
        user_id=user_id,
        display_name=display_name,
        sip_username=sip_username,
        sip_password=sip_password
    )
    
    device_config = UserDeviceConfig(
        user_id=user_id,
        mac_address=mac_address
    )
    
    call_config = UserCallSettings(
        user_id=user_id,
        default_greeting=f"Hello! This is {display_name}'s AI assistant. How can I help you today?"
    )
    
    return UserConfiguration(
        sip=sip_config,
        device=device_config,
        calls=call_config
    ) 
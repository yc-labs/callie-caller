#!/usr/bin/env python3
"""
Migration script to convert single-tenant SIP configuration to multi-tenant Firebase setup.
This script reads your existing legacy environment variables and creates a user in the new system.
"""

import os
import sys
import logging
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from callie_caller.config.firebase_service import (
    get_firebase_service, 
    create_sample_user_config,
    UserConfiguration
)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_legacy_config():
    """Load legacy single-tenant configuration from environment."""
    # Load .env file if it exists
    env_file = project_root / "config.env"
    if env_file.exists():
        load_dotenv(env_file)
        logger.info(f"Loaded configuration from {env_file}")
    else:
        logger.info("No config.env file found, using system environment variables")
    
    # Extract legacy configuration
    config = {
        'sip_server': os.getenv('ZOHO_SIP_SERVER'),
        'sip_username': os.getenv('ZOHO_SIP_USERNAME'),
        'sip_password': os.getenv('ZOHO_SIP_PASSWORD'),
        'sip_port': int(os.getenv('SIP_PORT', '5060')),
        'account_label': os.getenv('ACCOUNT_LABEL'),
        'custom_user_agent': os.getenv('CUSTOM_USER_AGENT'),
        'device_model': os.getenv('DEVICE_MODEL', 'SIP-T46S'),
        'device_firmware': os.getenv('DEVICE_FIRMWARE', '66.85.0.5'),
        'mac_address': os.getenv('CUSTOM_USER_AGENT', '00:15:65:ab:cd:ef'),  # Fallback MAC
        'default_greeting': os.getenv('DEFAULT_GREETING', 'Hello! This is your AI voice assistant.')
    }
    
    # Validate required fields
    required_fields = ['sip_server', 'sip_username', 'sip_password']
    missing_fields = [field for field in required_fields if not config[field]]
    
    if missing_fields:
        logger.error(f"Missing required configuration: {missing_fields}")
        logger.error("Please ensure these environment variables are set:")
        for field in missing_fields:
            env_var = field.upper().replace('SIP_', 'ZOHO_SIP_')
            logger.error(f"  - {env_var}")
        return None
    
    return config

def create_primary_user(config: dict, user_id: str = "primary") -> UserConfiguration:
    """Create primary user configuration from legacy config."""
    
    # Extract display name from account label or username
    display_name = config.get('account_label') or config['sip_username']
    if '@' in display_name:
        display_name = display_name.split('@')[0].replace('.', ' ').title()
    
    # Create user configuration
    user_config = create_sample_user_config(
        user_id=user_id,
        display_name=display_name,
        sip_username=config['sip_username'],
        sip_password=config['sip_password'],
        mac_address=config['mac_address']
    )
    
    # Override with legacy settings
    user_config.sip.sip_server = config['sip_server']
    user_config.sip.sip_port = config['sip_port']
    if config.get('account_label'):
        user_config.sip.account_label = config['account_label']
    
    user_config.device.model = config['device_model']
    user_config.device.firmware = config['device_firmware']
    if config.get('custom_user_agent'):
        user_config.device.custom_user_agent = config['custom_user_agent']
    
    user_config.calls.default_greeting = config['default_greeting']
    
    return user_config

def test_firebase_connection():
    """Test Firebase connection."""
    try:
        firebase_service = get_firebase_service()
        if not firebase_service.db:
            logger.error("Firebase connection failed - Firestore client not initialized")
            return False
        
        # Test basic Firebase operation
        test_users = firebase_service.list_active_users()
        logger.info(f"Firebase connection successful - found {len(test_users)} existing users")
        return True
        
    except Exception as e:
        logger.error(f"Firebase connection failed: {e}")
        logger.error("Please ensure Firebase credentials are configured:")
        logger.error("  1. Set FIREBASE_SERVICE_ACCOUNT_PATH environment variable")
        logger.error("  2. Or set GOOGLE_APPLICATION_CREDENTIALS environment variable")
        return False

def migrate_to_multitenant():
    """Main migration function."""
    logger.info("🚀 Starting migration from single-tenant to multi-tenant configuration")
    
    # Step 1: Test Firebase connection
    logger.info("📡 Testing Firebase connection...")
    if not test_firebase_connection():
        return False
    
    # Step 2: Load legacy configuration
    logger.info("📋 Loading legacy single-tenant configuration...")
    legacy_config = load_legacy_config()
    if not legacy_config:
        return False
    
    logger.info(f"✅ Found legacy configuration for: {legacy_config['sip_username']}")
    
    # Step 3: Create primary user
    logger.info("👤 Creating primary user from legacy configuration...")
    user_config = create_primary_user(legacy_config, user_id="primary")
    
    # Step 4: Check if user already exists
    firebase_service = get_firebase_service()
    existing_user = firebase_service.get_user_config("primary")
    
    if existing_user:
        logger.warning("⚠️  Primary user already exists in Firebase")
        print(f"Existing user: {existing_user.sip.display_name} ({existing_user.sip.sip_username})")
        
        response = input("Do you want to update the existing user? (y/N): ").strip().lower()
        if response == 'y':
            success = firebase_service.update_user_config(user_config)
            if success:
                logger.info("✅ Updated existing primary user configuration")
            else:
                logger.error("❌ Failed to update existing user")
                return False
        else:
            logger.info("⏭️  Skipping user creation - using existing configuration")
    else:
        # Create new user
        success = firebase_service.create_user_config(user_config)
        if success:
            logger.info("✅ Created primary user in Firebase")
        else:
            logger.error("❌ Failed to create primary user")
            return False
    
    # Step 5: Display migration summary
    logger.info("\n🎉 Migration completed successfully!")
    print(f"""
📊 Migration Summary:
  • User ID: primary
  • Display Name: {user_config.sip.display_name}
  • SIP Username: {user_config.sip.sip_username}
  • SIP Server: {user_config.sip.sip_server}
  • Device Model: {user_config.device.model}
  • MAC Address: {user_config.device.mac_address}
  • Default Greeting: {user_config.calls.default_greeting}

🚀 Next Steps:
  1. Start Callie Caller: python main.py
  2. Connect primary user: curl -X POST http://localhost:8080/users/primary/sip/connect
  3. Make a test call: curl -X POST http://localhost:8080/users/primary/call -d '{{"number":"+1234567890"}}'
  4. View admin status: curl http://localhost:8080/admin/status

💡 Legacy environment variables are still supported for backwards compatibility,
   but you can now manage users through the API!
""")
    
    return True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate single-tenant configuration to multi-tenant Firebase setup")
    parser.add_argument('--user-id', default='primary', help='User ID for the migrated configuration (default: primary)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without making changes')
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
        legacy_config = load_legacy_config()
        if legacy_config:
            user_config = create_primary_user(legacy_config, args.user_id)
            print(f"""
Would create user with:
  • User ID: {user_config.user_id}
  • Display Name: {user_config.sip.display_name}
  • SIP Username: {user_config.sip.sip_username}
  • SIP Server: {user_config.sip.sip_server}
  • Device: {user_config.device.model} ({user_config.device.mac_address})
""")
    else:
        success = migrate_to_multitenant()
        sys.exit(0 if success else 1) 
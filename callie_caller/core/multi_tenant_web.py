"""
Multi-tenant web endpoints for user onboarding and SIP configuration management.
Handles user registration, SIP configuration management, and multi-tenant call routing.
"""

import logging
import random
import time
from typing import Optional, Dict, Any, List
from flask import Flask, request, jsonify

from callie_caller.config.firebase_service import (
    get_firebase_service, 
    UserConfiguration, 
    create_sample_user_config
)
from callie_caller.sip.multi_tenant_client import MultiTenantSipClient
from callie_caller.ai.conversation import ConversationManager

logger = logging.getLogger(__name__)

class MultiTenantWebManager:
    """
    Manages multi-tenant web endpoints and user-specific SIP clients.
    """
    
    def __init__(self):
        """Initialize multi-tenant web manager."""
        self.firebase_service = get_firebase_service()
        self.conversation_manager = ConversationManager()
        
        # Active SIP clients per user
        self.user_sip_clients: Dict[str, MultiTenantSipClient] = {}
        
        # Active calls tracking
        self.active_calls: Dict[str, Dict[str, Any]] = {}  # call_id -> call_info
        
        logger.info("Multi-tenant web manager initialized")
    
    def setup_routes(self, app: Flask) -> None:
        """Setup multi-tenant routes on the Flask app."""
        
        @app.route('/users', methods=['POST'])
        def create_user():
            """Create a new user with SIP configuration."""
            try:
                data = request.get_json()
                
                # Required fields
                required_fields = ['user_id', 'display_name', 'sip_username', 'sip_password']
                missing_fields = [field for field in required_fields if not data.get(field)]
                if missing_fields:
                    return jsonify({'error': f'Missing required fields: {missing_fields}'}), 400
                
                user_id = data['user_id']
                display_name = data['display_name']
                sip_username = data['sip_username']
                sip_password = data['sip_password']
                
                # Optional fields
                mac_address = data.get('mac_address', self._generate_mac_address())
                sip_server = data.get('sip_server', 'sip.zoho.com')
                account_label = data.get('account_label')
                greeting = data.get('greeting')
                
                # Create user configuration
                user_config = create_sample_user_config(
                    user_id=user_id,
                    display_name=display_name,
                    sip_username=sip_username,
                    sip_password=sip_password,
                    mac_address=mac_address
                )
                
                # Override optional settings
                if sip_server != 'sip.zoho.com':
                    user_config.sip.sip_server = sip_server
                if account_label:
                    user_config.sip.account_label = account_label
                if greeting:
                    user_config.calls.default_greeting = greeting
                
                # Save to Firebase
                success = self.firebase_service.create_user_config(user_config)
                
                if success:
                    logger.info(f"Created user configuration for {user_id}")
                    return jsonify({
                        'success': True,
                        'user_id': user_id,
                        'sip_username': sip_username,
                        'mac_address': mac_address,
                        'status': 'created'
                    })
                else:
                    return jsonify({'error': 'Failed to create user configuration'}), 500
                    
            except Exception as e:
                logger.error(f"Error creating user: {e}")
                return jsonify({'error': str(e)}), 500
        
        @app.route('/users/<user_id>', methods=['GET'])
        def get_user(user_id: str):
            """Get user configuration."""
            try:
                user_config = self.firebase_service.get_user_config(user_id)
                
                if not user_config:
                    return jsonify({'error': 'User not found'}), 404
                
                # Get SIP client status
                sip_client = self.user_sip_clients.get(user_id)
                sip_status = {
                    'connected': bool(sip_client and sip_client.running),
                    'registered': bool(sip_client and sip_client.registered),
                    'active_calls': len([call for call in self.active_calls.values() if call.get('user_id') == user_id])
                }
                
                return jsonify({
                    'user_id': user_config.user_id,
                    'display_name': user_config.sip.display_name,
                    'sip_username': user_config.sip.sip_username,
                    'sip_server': user_config.sip.sip_server,
                    'account_label': user_config.sip.account_label,
                    'is_active': user_config.sip.is_active,
                    'mac_address': user_config.device.mac_address,
                    'device_model': user_config.device.model,
                    'default_greeting': user_config.calls.default_greeting,
                    'sip_status': sip_status,
                    'created_at': user_config.sip.created_at.isoformat() if user_config.sip.created_at else None,
                    'updated_at': user_config.sip.updated_at.isoformat() if user_config.sip.updated_at else None
                })
                
            except Exception as e:
                logger.error(f"Error getting user {user_id}: {e}")
                return jsonify({'error': str(e)}), 500
        
        @app.route('/users/<user_id>', methods=['PUT'])
        def update_user(user_id: str):
            """Update user configuration."""
            try:
                # Get existing user config
                user_config = self.firebase_service.get_user_config(user_id)
                if not user_config:
                    return jsonify({'error': 'User not found'}), 404
                
                data = request.get_json()
                
                # Update fields if provided
                if 'display_name' in data:
                    user_config.sip.display_name = data['display_name']
                if 'sip_password' in data:
                    user_config.sip.sip_password = data['sip_password']
                if 'account_label' in data:
                    user_config.sip.account_label = data['account_label']
                if 'greeting' in data:
                    user_config.calls.default_greeting = data['greeting']
                if 'is_active' in data:
                    user_config.sip.is_active = data['is_active']
                
                # Update timestamps
                from datetime import datetime, timezone
                user_config.sip.updated_at = datetime.now(timezone.utc)
                
                # Save changes
                success = self.firebase_service.update_user_config(user_config)
                
                if success:
                    # If SIP client is active, restart it with new config
                    if user_id in self.user_sip_clients:
                        self._restart_user_sip_client(user_id, user_config)
                    
                    logger.info(f"Updated user configuration for {user_id}")
                    return jsonify({
                        'success': True,
                        'user_id': user_id,
                        'status': 'updated'
                    })
                else:
                    return jsonify({'error': 'Failed to update user configuration'}), 500
                    
            except Exception as e:
                logger.error(f"Error updating user {user_id}: {e}")
                return jsonify({'error': str(e)}), 500
        
        @app.route('/users', methods=['GET'])
        def list_users():
            """List all users with their status."""
            try:
                user_ids = self.firebase_service.list_active_users()
                users = []
                
                for user_id in user_ids:
                    user_config = self.firebase_service.get_user_config(user_id)
                    if user_config:
                        sip_client = self.user_sip_clients.get(user_id)
                        users.append({
                            'user_id': user_config.user_id,
                            'display_name': user_config.sip.display_name,
                            'sip_username': user_config.sip.sip_username,
                            'is_active': user_config.sip.is_active,
                            'sip_connected': bool(sip_client and sip_client.running),
                            'sip_registered': bool(sip_client and sip_client.registered),
                            'created_at': user_config.sip.created_at.isoformat() if user_config.sip.created_at else None
                        })
                
                return jsonify({
                    'users': users,
                    'total_count': len(users),
                    'active_sip_clients': len(self.user_sip_clients)
                })
                
            except Exception as e:
                logger.error(f"Error listing users: {e}")
                return jsonify({'error': str(e)}), 500
        
        @app.route('/users/<user_id>/sip/connect', methods=['POST'])
        def connect_user_sip(user_id: str):
            """Connect and register user's SIP client."""
            try:
                # Get user config
                user_config = self.firebase_service.get_user_config(user_id)
                if not user_config:
                    return jsonify({'error': 'User not found'}), 404
                
                if not user_config.sip.is_active:
                    return jsonify({'error': 'User is not active'}), 400
                
                # Check if already connected
                if user_id in self.user_sip_clients:
                    sip_client = self.user_sip_clients[user_id]
                    if sip_client.running:
                        return jsonify({
                            'success': True,
                            'user_id': user_id,
                            'status': 'already_connected',
                            'registered': sip_client.registered
                        })
                
                # Create and start SIP client
                sip_client = MultiTenantSipClient(
                    user_config=user_config,
                    on_incoming_call=lambda call: self._handle_incoming_call(user_id, call)
                )
                
                # Start and register
                if sip_client.start(dict(request.headers)):
                    registration_success = sip_client.register()
                    self.user_sip_clients[user_id] = sip_client
                    
                    logger.info(f"SIP client connected for user {user_id}, registration: {registration_success}")
                    
                    return jsonify({
                        'success': True,
                        'user_id': user_id,
                        'status': 'connected',
                        'registered': registration_success,
                        'local_endpoint': f"{sip_client.local_ip}:{sip_client.local_port}",
                        'public_ip': sip_client.public_ip
                    })
                else:
                    return jsonify({'error': 'Failed to start SIP client'}), 500
                    
            except Exception as e:
                logger.error(f"Error connecting SIP for user {user_id}: {e}")
                return jsonify({'error': str(e)}), 500
        
        @app.route('/users/<user_id>/call', methods=['POST'])
        def make_user_call(user_id: str):
            """Make a call using specific user's SIP configuration."""
            try:
                data = request.get_json()
                target_number = data.get('number')
                message = data.get('message')
                
                if not target_number:
                    return jsonify({'error': 'Phone number required'}), 400
                
                # Get user's SIP client
                sip_client = self.user_sip_clients.get(user_id)
                if not sip_client or not sip_client.running:
                    return jsonify({'error': 'User SIP client not connected'}), 400
                
                if not sip_client.registered:
                    return jsonify({'error': 'User SIP client not registered'}), 400
                
                # Make the call
                call_id = f"call-{user_id}-{int(time.time())}"
                success = sip_client.make_call(target_number, message)
                
                if success:
                    # Track the call
                    self.active_calls[call_id] = {
                        'user_id': user_id,
                        'target_number': target_number,
                        'message': message,
                        'start_time': time.time(),
                        'status': 'initiated'
                    }
                    
                    logger.info(f"Call initiated for user {user_id} to {target_number}")
                    
                    return jsonify({
                        'success': True,
                        'call_id': call_id,
                        'user_id': user_id,
                        'target_number': target_number,
                        'status': 'initiated'
                    })
                else:
                    return jsonify({'error': 'Failed to initiate call'}), 500
                    
            except Exception as e:
                logger.error(f"Error making call for user {user_id}: {e}")
                return jsonify({'error': str(e)}), 500
        
        @app.route('/admin/status', methods=['GET'])
        def admin_status():
            """Get multi-tenant system status."""
            try:
                # Get all users
                user_ids = self.firebase_service.list_active_users()
                
                # Count SIP clients by status
                connected_clients = 0
                registered_clients = 0
                
                for user_id in user_ids:
                    sip_client = self.user_sip_clients.get(user_id)
                    if sip_client:
                        if sip_client.running:
                            connected_clients += 1
                        if sip_client.registered:
                            registered_clients += 1
                
                return jsonify({
                    'multi_tenant_enabled': True,
                    'total_users': len(user_ids),
                    'connected_sip_clients': connected_clients,
                    'registered_sip_clients': registered_clients,
                    'active_calls': len(self.active_calls),
                    'firebase_connected': bool(self.firebase_service.db),
                    'active_user_clients': list(self.user_sip_clients.keys()),
                    'system_status': 'healthy'
                })
                
            except Exception as e:
                logger.error(f"Error getting admin status: {e}")
                return jsonify({'error': str(e)}), 500
    
    def _generate_mac_address(self) -> str:
        """Generate a random MAC address for device emulation."""
        # Generate a MAC address with Yealink OUI prefix
        mac = "00:15:65"  # Yealink OUI
        for _ in range(3):
            mac += f":{random.randint(0, 255):02x}"
        return mac
    
    def _handle_incoming_call(self, user_id: str, call) -> None:
        """Handle incoming call for a specific user."""
        try:
            logger.info(f"Incoming call for user {user_id}: {call.call_id}")
            
            # Track the call
            call_id = call.call_id
            self.active_calls[call_id] = {
                'user_id': user_id,
                'call_id': call_id,
                'direction': 'incoming',
                'start_time': time.time(),
                'status': 'ringing'
            }
            
            # Handle the call (would typically answer and start AI conversation)
            # For now, just log it
            logger.info(f"Incoming call handled for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error handling incoming call for user {user_id}: {e}")
    
    def _restart_user_sip_client(self, user_id: str, user_config: UserConfiguration) -> None:
        """Restart a user's SIP client with updated configuration."""
        try:
            # Stop existing client
            if user_id in self.user_sip_clients:
                self.user_sip_clients[user_id].stop()
                del self.user_sip_clients[user_id]
            
            # Start new client with updated config
            sip_client = MultiTenantSipClient(
                user_config=user_config,
                on_incoming_call=lambda call: self._handle_incoming_call(user_id, call)
            )
            
            if sip_client.start():
                sip_client.register()
                self.user_sip_clients[user_id] = sip_client
                logger.info(f"Restarted SIP client for user {user_id} with updated configuration")
            
        except Exception as e:
            logger.error(f"Error restarting SIP client for user {user_id}: {e}")

# Global manager instance
_multi_tenant_manager: Optional[MultiTenantWebManager] = None

def get_multi_tenant_manager() -> MultiTenantWebManager:
    """Get global multi-tenant manager instance."""
    global _multi_tenant_manager
    if _multi_tenant_manager is None:
        _multi_tenant_manager = MultiTenantWebManager()
    return _multi_tenant_manager 
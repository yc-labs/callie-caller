# Multi-Tenant SIP Configuration Guide

## Overview

Callie Caller v1.2.0 introduces **multi-tenant SIP configuration** with Firebase backend. Instead of hardcoding a single SIP configuration, you can now manage multiple users, each with their own SIP credentials, device settings, and AI preferences.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Firebase      │    │  Callie Caller  │    │   Zoho Voice    │
│   Firestore     │◄──►│  Application    │◄──►│  SIP Service    │
│                 │    │                 │    │                 │
│ • User Configs  │    │ • Multi-Tenant  │    │ • Multiple SIP  │
│ • SIP Creds     │    │   SIP Clients   │    │   Accounts      │
│ • Device Info   │    │ • Web API       │    │ • User Exts     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Features

- **🔑 User Management**: Create, update, and delete user configurations
- **📞 Per-User SIP**: Each user has their own SIP credentials and registration
- **🤖 Custom AI**: Per-user greetings and AI behavior
- **📱 Device Emulation**: Unique MAC addresses per user
- **🔄 Hot-Reload**: Update user configs without restart
- **📊 Admin Dashboard**: Monitor all users and SIP clients
- **🔒 Secure Storage**: Encrypted credentials in Firebase

## Setup Guide

### 1. Firebase Setup

1. Create a Firebase project at https://console.firebase.google.com
2. Enable Firestore Database
3. Generate a service account key:
   - Go to Project Settings > Service Accounts
   - Click "Generate new private key"
   - Save the JSON file securely

### 2. Environment Configuration

```bash
# Add to your .env file
FIREBASE_SERVICE_ACCOUNT_PATH=/path/to/firebase-service-account.json

# Or use Application Default Credentials
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/firebase-service-account.json
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt  # Firebase Admin SDK is now included
```

## API Usage

### Create a User

```bash
curl -X POST http://localhost:8080/users \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice",
    "display_name": "Alice Johnson", 
    "sip_username": "alice@company.com",
    "sip_password": "secure_password",
    "greeting": "Hi! This is Alice'\''s AI assistant."
  }'
```

### Connect User's SIP Client

```bash
curl -X POST http://localhost:8080/users/alice/sip/connect
```

### Make a Call as a User

```bash
curl -X POST http://localhost:8080/users/alice/call \
  -H "Content-Type: application/json" \
  -d '{
    "number": "+1234567890",
    "message": "Hello from Alice'\''s AI assistant!"
  }'
```

### List All Users

```bash
curl http://localhost:8080/users
```

### Get Admin Status

```bash
curl http://localhost:8080/admin/status
```

## Firebase Schema

### User Configuration Document

```json
{
  "user_configs": {
    "alice": {
      "sip": {
        "user_id": "alice",
        "display_name": "Alice Johnson",
        "sip_username": "alice@company.com", 
        "sip_password": "secure_password",
        "sip_server": "sip.zoho.com",
        "sip_port": 5060,
        "account_label": "Alice",
        "is_active": true,
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:30:00Z"
      },
      "device": {
        "user_id": "alice",
        "mac_address": "00:15:65:12:34:56",
        "model": "SIP-T46S",
        "firmware": "66.85.0.5",
        "custom_user_agent": null
      },
      "calls": {
        "user_id": "alice",
        "default_greeting": "Hi! This is Alice's AI assistant.",
        "max_call_duration": 1800,
        "answer_timeout": 30,
        "rtp_port_min": 10000,
        "rtp_port_max": 10100,
        "use_fixed_rtp_port": true
      }
    }
  }
}
```

## Use Cases

### 1. Customer Service Team

```bash
# Create agents with different SIP extensions
curl -X POST http://localhost:8080/users -d '{
  "user_id": "agent001",
  "display_name": "Customer Service Agent 1",
  "sip_username": "ext1001",
  "sip_password": "pass1001",
  "greeting": "Thank you for calling customer service. How can I help?"
}'

curl -X POST http://localhost:8080/users -d '{
  "user_id": "agent002", 
  "display_name": "Customer Service Agent 2",
  "sip_username": "ext1002",
  "sip_password": "pass1002",
  "greeting": "Hi! You've reached technical support. What can I assist with?"
}'
```

### 2. Multi-Company Setup

```bash
# Company A
curl -X POST http://localhost:8080/users -d '{
  "user_id": "company_a_sales",
  "display_name": "Company A Sales",
  "sip_username": "sales@companya.com",
  "sip_password": "sales_pass",
  "sip_server": "sip-companya.zoho.com",
  "greeting": "Thank you for calling Company A sales department."
}'

# Company B  
curl -X POST http://localhost:8080/users -d '{
  "user_id": "company_b_support",
  "display_name": "Company B Support", 
  "sip_username": "support@companyb.com",
  "sip_password": "support_pass",
  "sip_server": "sip-companyb.zoho.com",
  "greeting": "Welcome to Company B technical support."
}'
```

### 3. Personal Assistant Network

```bash
# Family members with personal AI assistants
curl -X POST http://localhost:8080/users -d '{
  "user_id": "dad",
  "display_name": "Dad",
  "sip_username": "dad_home_line",
  "sip_password": "family_pass",
  "greeting": "Hi! You'\''ve reached Dad'\''s AI assistant. He'\''s probably in the garage."
}'
```

## Management Operations

### Update User Settings

```bash
curl -X PUT http://localhost:8080/users/alice \
  -H "Content-Type: application/json" \
  -d '{
    "greeting": "Updated greeting message!",
    "sip_password": "new_secure_password"
  }'
```

### Disconnect User's SIP

```bash
curl -X POST http://localhost:8080/users/alice/sip/disconnect
```

### Deactivate User

```bash
curl -X PUT http://localhost:8080/users/alice \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

### Delete User

```bash
curl -X DELETE http://localhost:8080/users/alice
```

## Monitoring

### System Status

```json
{
  "multi_tenant_enabled": true,
  "total_users": 5,
  "connected_sip_clients": 3,
  "registered_sip_clients": 3,
  "active_calls": 1,
  "firebase_connected": true,
  "active_user_clients": ["alice", "bob", "charlie"],
  "system_status": "healthy"
}
```

### User Status

```json
{
  "user_id": "alice",
  "display_name": "Alice Johnson",
  "sip_username": "alice@company.com",
  "is_active": true,
  "sip_status": {
    "connected": true,
    "registered": true,
    "active_calls": 0
  },
  "created_at": "2024-01-15T10:30:00Z"
}
```

## Security Considerations

1. **🔐 Firebase Security Rules**: Configure Firestore rules to restrict access
2. **🔑 Service Account**: Keep Firebase service account key secure
3. **🚫 No Plaintext**: SIP passwords are stored encrypted in Firestore
4. **🌐 Network**: Use HTTPS for all API endpoints
5. **🔒 Authentication**: Add API authentication for production use

## Troubleshooting

### Common Issues

**Firebase Connection Failed**
```bash
# Check service account path
echo $FIREBASE_SERVICE_ACCOUNT_PATH

# Verify JSON file
cat $FIREBASE_SERVICE_ACCOUNT_PATH | jq .
```

**SIP Registration Failed**
```bash
# Check user config
curl http://localhost:8080/users/alice

# View logs
docker-compose logs -f callie-caller
```

**User Not Found**
```bash
# List all users
curl http://localhost:8080/users

# Check Firebase directly
# Use Firebase Console to verify data
```

## Migration from Single-Tenant

The system is **backwards compatible**. Existing single-tenant configurations continue to work. To migrate:

1. Set up Firebase as described above
2. Create user configurations for existing SIP accounts
3. Update your calling scripts to use user-specific endpoints
4. Optionally remove legacy environment variables

## Next Steps

- **Web Dashboard**: Build a React/Vue.js admin interface
- **User Authentication**: Add OAuth/JWT for API security  
- **Call Analytics**: Track per-user call metrics
- **Auto-Scaling**: Dynamic SIP client management
- **Advanced Routing**: Route calls based on user availability

---

**Need Help?** Check the logs, API responses, and Firebase Console for debugging information. 
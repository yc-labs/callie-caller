# Callie Caller - Scripts Documentation

This directory contains all the automation scripts for setting up, deploying, and managing the Callie Caller system.

## 📁 Directory Structure

```
scripts/
├── README.md                           # This documentation
├── networking/
│   └── configure-router-upnp.py       # Automatic router configuration
├── docker/
│   └── setup-static-ports.sh          # Docker deployment with static ports
└── deployment/
    └── build-and-deploy.sh             # Google Cloud deployment pipeline
```

## 🚀 Quick Start

### 1. Router Configuration (One-time setup)

Configure your router automatically using UPnP:

```bash
python scripts/networking/configure-router-upnp.py
```

This will:
- ✅ Discover your UPnP-enabled router
- ✅ Configure ports: UDP 5060 (SIP), 10000-10004 (RTP)
- ✅ Show Google Cloud firewall setup commands

### 2. Local Docker Deployment

Deploy locally with Docker using static ports:

```bash
# Setup (first time)
scripts/docker/setup-static-ports.sh setup

# Deploy
scripts/docker/setup-static-ports.sh deploy

# Check status
scripts/docker/setup-static-ports.sh status

# View logs
scripts/docker/setup-static-ports.sh logs
```

### 3. Google Cloud Deployment

Deploy to Google Cloud with full automation:

```bash
# Complete deployment (version bump + build + push + deploy)
scripts/deployment/build-and-deploy.sh full

# Web-only mode (no SIP functionality)
scripts/deployment/build-and-deploy.sh full --web-only
```

## 📋 Detailed Script Documentation

### 🌐 Router Configuration (`scripts/networking/configure-router-upnp.py`)

**Purpose:** Automatically configure router port forwarding for SIP/RTP traffic.

**Features:**
- Auto-discovers UPnP-enabled routers
- Configures required UDP ports: 5060, 10000-10004
- Shows Google Cloud firewall setup commands
- Provides fallback manual configuration instructions

**Usage:**
```bash
python scripts/networking/configure-router-upnp.py
```

**Requirements:**
- `miniupnpc` Python package (auto-installed)
- UPnP-enabled router

**Output:**
- Configured router port forwards
- Google Cloud firewall commands
- Manual configuration instructions (if UPnP fails)

---

### 🐳 Docker Deployment (`scripts/docker/setup-static-ports.sh`)

**Purpose:** Complete Docker deployment automation with static port configuration.

**Features:**
- Automatic secrets fetching from Google Cloud Secret Manager
- Static port configuration (no dynamic UPnP in containers)
- Health checks and status monitoring
- Comprehensive logging and error handling

**Commands:**

```bash
# Setup environment and show router config
scripts/docker/setup-static-ports.sh setup

# Deploy with Docker Compose
scripts/docker/setup-static-ports.sh deploy

# Check deployment status
scripts/docker/setup-static-ports.sh status

# View real-time logs
scripts/docker/setup-static-ports.sh logs

# Stop deployment
scripts/docker/setup-static-ports.sh stop

# Clean up (remove containers and images)
scripts/docker/setup-static-ports.sh clean
```

**Files Created:**
- `docker-secrets.env` - Environment variables with secrets
- Uses `docker-compose-static-ports.yml` for deployment

**Requirements:**
- Docker and Docker Compose
- Google Cloud CLI (for automatic secrets)
- Configured router (run networking script first)

---

### ☁️ Google Cloud Deployment (`scripts/deployment/build-and-deploy.sh`)

**Purpose:** Complete Google Cloud deployment pipeline with versioning, building, and deployment.

**Features:**
- Automatic version bumping (major/minor/patch)
- Docker image building with multi-platform support
- Artifact Registry pushing
- Cloud Run deployment
- Firewall rule creation
- Git tagging and commits

**Commands:**

```bash
# Complete deployment pipeline
scripts/deployment/build-and-deploy.sh full

# Individual steps
scripts/deployment/build-and-deploy.sh version --minor
scripts/deployment/build-and-deploy.sh build
scripts/deployment/build-and-deploy.sh push
scripts/deployment/build-and-deploy.sh firewall
scripts/deployment/build-and-deploy.sh deploy
```

**Options:**

```bash
# Project configuration
--project yc-partners              # Google Cloud Project ID
--region us-central1               # Google Cloud Region
--repository callie-caller         # Artifact Registry repository
--service callie-caller            # Cloud Run service name

# Versioning
--major                           # Bump major version (1.0.0 → 2.0.0)
--minor                           # Bump minor version (1.0.0 → 1.1.0)
--patch                           # Bump patch version (1.0.0 → 1.0.1)
--version 1.2.3                   # Use specific version

# Deployment options
--web-only                        # Deploy web-only mode (no SIP)
--memory 1Gi                      # Cloud Run memory limit
--cpu 1                           # Cloud Run CPU allocation
--instances 5                     # Max Cloud Run instances
```

**Examples:**

```bash
# Full deployment with minor version bump
scripts/deployment/build-and-deploy.sh full --minor

# Build and push specific version
scripts/deployment/build-and-deploy.sh push --version 1.2.0

# Deploy web-only mode to different project
scripts/deployment/build-and-deploy.sh full --web-only --project my-project

# Just create firewall rules
scripts/deployment/build-and-deploy.sh firewall
```

**Requirements:**
- Docker
- Google Cloud CLI (authenticated)
- Git
- Required secrets in Google Cloud Secret Manager

## 🔧 Configuration

### Environment Variables

The scripts use these environment variables (automatically configured):

```bash
# API Credentials
GEMINI_API_KEY=your_gemini_api_key
ZOHO_SIP_USERNAME=your_zoho_username
ZOHO_SIP_PASSWORD=your_zoho_password

# SIP Configuration
ZOHO_SIP_SERVER=us3-proxy2.zohovoice.com
SIP_PORT=5060

# RTP Configuration
RTP_PORT=10000
RTP_PORT_RANGE_START=10000
RTP_PORT_RANGE_END=10004

# Container Settings
USE_UPNP=false                    # Disabled in containers
CONTAINER_MODE=true
SERVER_PORT=8080
LOG_LEVEL=INFO
```

### Google Cloud Secrets

Required secrets in Google Cloud Secret Manager:

1. `gemini-api-key` - Your Google Gemini API key
2. `zoho-sip-username` - Your Zoho Voice SIP username
3. `zoho-sip-password` - Your Zoho Voice SIP password

Create secrets:
```bash
gcloud secrets create gemini-api-key --data-file=-
gcloud secrets create zoho-sip-username --data-file=-
gcloud secrets create zoho-sip-password --data-file=-
```

### Network Ports

Required port forwards on your router:

| Protocol | External Port | Internal Port | Description |
|----------|---------------|---------------|-------------|
| UDP | 5060 | 5060 | SIP Signaling |
| UDP | 10000 | 10000 | Primary RTP Audio |
| UDP | 10001 | 10001 | Backup RTP Audio |
| UDP | 10002 | 10002 | Additional RTP |
| UDP | 10003 | 10003 | Additional RTP |
| UDP | 10004 | 10004 | Additional RTP |

## 🚨 Troubleshooting

### Router Configuration Issues

**Problem:** UPnP discovery fails
```bash
❌ No UPnP devices found!
```

**Solution:**
1. Enable UPnP on your router
2. Check firewall settings
3. Use manual port forwarding with the provided configuration

### Docker Deployment Issues

**Problem:** Service health check fails
```bash
❌ Service health check failed!
```

**Solutions:**
1. Check logs: `scripts/docker/setup-static-ports.sh logs`
2. Verify environment variables in `docker-secrets.env`
3. Ensure router is configured for static ports
4. Check port availability: `lsof -i :8080`

### Google Cloud Deployment Issues

**Problem:** Authentication error
```bash
❌ Google Cloud not authenticated
```

**Solution:**
```bash
gcloud auth login
gcloud config set project yc-partners
```

**Problem:** Secrets not found
```bash
❌ Secret [gemini-api-key] not found
```

**Solution:**
```bash
# Create missing secrets
echo "your_api_key" | gcloud secrets create gemini-api-key --data-file=-
```

## 📈 Monitoring and Logs

### Local Docker
```bash
# Service status
scripts/docker/setup-static-ports.sh status

# Real-time logs
scripts/docker/setup-static-ports.sh logs

# Health check
curl http://localhost:8080/health
```

### Google Cloud Run
```bash
# Service logs
gcloud logging read "resource.type=cloud_run_revision" --limit=50

# Service status
gcloud run services describe callie-caller --region=us-central1

# Health check
curl https://your-service-url/health
```

## 🎯 Best Practices

1. **Run scripts in order:**
   1. Router configuration (one-time)
   2. Docker deployment (testing)
   3. Cloud deployment (production)

2. **Test locally first:**
   - Always test with Docker before deploying to Cloud
   - Verify audio quality and call functionality

3. **Version management:**
   - Use semantic versioning (major.minor.patch)
   - Create git tags for releases
   - Document changes in commit messages

4. **Security:**
   - Keep secrets in Google Cloud Secret Manager
   - Don't commit credentials to git
   - Regularly rotate API keys

5. **Monitoring:**
   - Check health endpoints regularly
   - Monitor logs for errors
   - Set up alerts for service failures

## 🔗 Related Documentation

- [Project README](../README.md) - Main project documentation
- [Docker Compose Files](../docker-compose*.yml) - Container configurations
- [Google Cloud Documentation](https://cloud.google.com/run/docs) - Cloud Run details

---

**Need help?** Check the troubleshooting section above or review the script output for detailed error messages and suggestions. 
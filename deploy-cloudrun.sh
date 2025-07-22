#!/bin/bash

# Callie Caller - Cloud Run Deployment Script
# This script handles deployment to Google Cloud Run without UPnP

set -e

PROJECT_ID="yc-partners"
REGION="us-central1"
SERVICE_NAME="callie-caller"
REPOSITORY="callie-caller"
IMAGE_NAME="callie-caller"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if gcloud is authenticated
check_auth() {
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        error "Not authenticated with gcloud. Run 'gcloud auth login'"
        exit 1
    fi
    success "Authenticated with gcloud"
}

# Enable required APIs
enable_apis() {
    log "Enabling required Google Cloud APIs..."
    gcloud services enable \
        cloudbuild.googleapis.com \
        run.googleapis.com \
        artifactregistry.googleapis.com \
        secretmanager.googleapis.com \
        --project=$PROJECT_ID
    success "APIs enabled"
}

# Create Artifact Registry repository if it doesn't exist
setup_registry() {
    log "Setting up Artifact Registry..."
    if ! gcloud artifacts repositories describe $REPOSITORY \
        --location=$REGION \
        --project=$PROJECT_ID &>/dev/null; then
        
        log "Creating Artifact Registry repository..."
        gcloud artifacts repositories create $REPOSITORY \
            --repository-format=docker \
            --location=$REGION \
            --description="Callie Caller AI Voice Agent" \
            --project=$PROJECT_ID
        success "Artifact Registry repository created"
    else
        success "Artifact Registry repository already exists"
    fi
}

# Configure Docker authentication
configure_docker() {
    log "Configuring Docker authentication..."
    gcloud auth configure-docker $REGION-docker.pkg.dev --quiet
    success "Docker authentication configured"
}

# Build and push Docker image
build_and_push() {
    VERSION=${1:-latest}
    IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:$VERSION"
    
    log "Building Docker image..."
    docker build \
        --build-arg VERSION=$VERSION \
        --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
        --build-arg VCS_REF=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown") \
        --tag $IMAGE_URI \
        .
    
    log "Pushing Docker image to Artifact Registry..."
    docker push $IMAGE_URI
    
    success "Image pushed: $IMAGE_URI"
    echo $IMAGE_URI
}

# Deploy to Cloud Run
deploy() {
    VERSION=${1:-latest}
    IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:$VERSION"
    
    log "Deploying to Cloud Run..."
    
    # Create a temporary service configuration
    cat > /tmp/cloudrun-service.yaml << EOF
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: $SERVICE_NAME
  annotations:
    run.googleapis.com/ingress: all
    run.googleapis.com/execution-environment: gen2
spec:
  template:
    metadata:
      annotations:
        run.googleapis.com/cpu-boost: true
        autoscaling.knative.dev/maxScale: "10"
        autoscaling.knative.dev/minScale: "1"
    spec:
      containerConcurrency: 1000
      timeoutSeconds: 3600
      containers:
      - image: $IMAGE_URI
        ports:
        - name: http1
          containerPort: 8080
        env:
        # SIP Configuration
        - name: ZOHO_SIP_SERVER
          value: "us3-proxy2.zohovoice.com"
        - name: ZOHO_SIP_USERNAME
          valueFrom:
            secretKeyRef:
              key: latest
              name: zoho-sip-username
        - name: ZOHO_SIP_PASSWORD
          valueFrom:
            secretKeyRef:
              key: latest
              name: zoho-sip-password
        - name: ZOHO_SIP_BACKUP_SERVER
          value: "us4-proxy2.zohovoice.com"
        - name: ACCOUNT_LABEL
          value: "Troy Fortin"
        - name: CUSTOM_USER_AGENT
          value: "00:1a:2b:3c:4d:5e"
        
        # AI Configuration
        - name: GEMINI_API_KEY
          valueFrom:
            secretKeyRef:
              key: latest
              name: gemini-api-key
        
        # Cloud Run Specific - NO UPnP
        - name: USE_UPNP
          value: "false"
        - name: CONTAINER_MODE
          value: "true"
        - name: CLOUD_RUN_MODE
          value: "true"
        - name: LOG_LEVEL
          value: "INFO"
        - name: PYTHONUNBUFFERED
          value: "1"
        
        # Port Configuration
        - name: FLASK_PORT
          value: "8080"
        - name: SERVER_PORT
          value: "8080"
        - name: SIP_PORT
          value: "5060"
        
        # Test Configuration
        - name: TEST_CALL_NUMBER
          value: "+16782960086"
        
        resources:
          limits:
            cpu: "2"
            memory: "2Gi"
          requests:
            cpu: "1"
            memory: "512Mi"
        
        # Health checks
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 30
          timeoutSeconds: 10
        
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 10
          timeoutSeconds: 5
EOF

    # Deploy the service
    gcloud run services replace /tmp/cloudrun-service.yaml \
        --region=$REGION \
        --project=$PROJECT_ID
    
    # Clean up temp file
    rm /tmp/cloudrun-service.yaml
    
    # Get the service URL
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(status.url)")
    
    success "Deployed to Cloud Run!"
    echo "Service URL: $SERVICE_URL"
    echo "Health Check: $SERVICE_URL/health"
    echo ""
    warning "Important for SIP without UPnP:"
    echo "- Cloud Run provides automatic public IP"
    echo "- No UPnP configuration needed"
    echo "- SIP traffic routes through Zoho's infrastructure"
    echo "- Test calls should work immediately"
}

# Test the deployment
test_deployment() {
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(status.url)" 2>/dev/null)
    
    if [ -z "$SERVICE_URL" ]; then
        error "Service not found. Deploy first."
        exit 1
    fi
    
    log "Testing health endpoint..."
    if curl -s "$SERVICE_URL/health" | grep -q "healthy"; then
        success "Health check passed"
    else
        error "Health check failed"
        exit 1
    fi
    
    log "Making test call..."
    echo "You can test a call by visiting: $SERVICE_URL"
    echo "Or via API: curl -X POST $SERVICE_URL/call -d '{\"number\":\"+14044626406\",\"message\":\"Cloud Run test\"}'"
}

# Main execution
case "${1:-deploy}" in
    "setup")
        log "Setting up Cloud Run environment..."
        check_auth
        enable_apis
        setup_registry
        configure_docker
        success "Setup complete!"
        ;;
    "build")
        VERSION=${2:-latest}
        log "Building and pushing image..."
        check_auth
        setup_registry
        configure_docker
        build_and_push $VERSION
        ;;
    "deploy")
        VERSION=${2:-latest}
        log "Full deployment (build + deploy)..."
        check_auth
        enable_apis
        setup_registry
        configure_docker
        build_and_push $VERSION
        deploy $VERSION
        ;;
    "deploy-only")
        VERSION=${2:-latest}
        log "Deploying existing image..."
        check_auth
        deploy $VERSION
        ;;
    "test")
        log "Testing deployment..."
        test_deployment
        ;;
    "logs")
        log "Showing Cloud Run logs..."
        gcloud logs read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME" \
            --project=$PROJECT_ID \
            --limit=50
        ;;
    *)
        echo "Usage: $0 {setup|build|deploy|deploy-only|test|logs} [version]"
        echo ""
        echo "Commands:"
        echo "  setup      - Set up Google Cloud environment"
        echo "  build      - Build and push Docker image"
        echo "  deploy     - Full deployment (build + deploy)"
        echo "  deploy-only- Deploy existing image"
        echo "  test       - Test the deployment"
        echo "  logs       - Show recent logs"
        echo ""
        echo "Examples:"
        echo "  $0 setup"
        echo "  $0 deploy v1.0.0"
        echo "  $0 test"
        exit 1
        ;;
esac 
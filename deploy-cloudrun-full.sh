#!/bin/bash

# Callie Caller - Cloud Run FULL SIP Deployment Script
# This script deploys the FULL SIP version with audio capabilities

set -e

PROJECT_ID="yc-partners"
REGION="us-central1"
SERVICE_NAME="callie-caller-full"
REPOSITORY="callie-caller"
IMAGE_NAME="callie-caller-full"

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

# Build and push the FULL SIP Docker image
build_and_push_full() {
    VERSION=${1:-latest}
    IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:$VERSION"
    
    log "Building FULL SIP Docker image..."
    docker build \
        --file Dockerfile.cloudrun-full \
        --build-arg VERSION=$VERSION \
        --build-arg BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ') \
        --build-arg VCS_REF=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown") \
        --tag $IMAGE_URI \
        .
    
    log "Pushing FULL SIP Docker image to Artifact Registry..."
    docker push $IMAGE_URI
    
    success "Full SIP Image pushed: $IMAGE_URI"
    echo $IMAGE_URI
}

# Deploy FULL SIP version to Cloud Run
deploy_full() {
    VERSION=${1:-latest}
    IMAGE_URI="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$IMAGE_NAME:$VERSION"
    
    log "Deploying FULL SIP version to Cloud Run..."
    
    # Create a temporary service configuration for FULL SIP
    cat > /tmp/cloudrun-full-service.yaml << EOF
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
        autoscaling.knative.dev/maxScale: "5"
        autoscaling.knative.dev/minScale: "1"
    spec:
      containerConcurrency: 10
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
        
        # Cloud Run Specific - FULL SIP MODE
        - name: USE_UPNP
          value: "false"
        - name: CONTAINER_MODE
          value: "true"
        - name: CLOUD_RUN_MODE
          value: "true"
        - name: LOG_LEVEL
          value: "DEBUG"
        - name: PYTHONUNBUFFERED
          value: "1"
        
        # Audio Debugging
        - name: DEBUG_AUDIO
          value: "true"
        - name: ENABLE_TEST_AUDIO
          value: "true"
        
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
            memory: "1Gi"
        
        # Health checks
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 60
          periodSeconds: 30
          timeoutSeconds: 10
        
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
EOF

    # Deploy the FULL SIP service
    gcloud run services replace /tmp/cloudrun-full-service.yaml \
        --region=$REGION \
        --project=$PROJECT_ID
    
    # Clean up temp file
    rm /tmp/cloudrun-full-service.yaml
    
    # Get the service URL
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(status.url)")
    
    success "FULL SIP version deployed to Cloud Run!"
    echo "Service URL: $SERVICE_URL"
    echo "Health Check: $SERVICE_URL/health"
    echo ""
    success "FULL SIP FEATURES ENABLED:"
    echo "✅ Real SIP calling with Zoho Voice"
    echo "✅ AI audio conversation with Gemini Live"
    echo "✅ Audio debugging and logging"
    echo "✅ Test audio injection capabilities"
    echo ""
    echo "🎯 Test call endpoint: POST $SERVICE_URL/call"
    echo '   {"number": "+16782960086", "message": "Testing audio from Cloud Run"}'
}

# Test the FULL SIP deployment
test_full_deployment() {
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
        --region=$REGION \
        --project=$PROJECT_ID \
        --format="value(status.url)" 2>/dev/null)
    
    if [ -z "$SERVICE_URL" ]; then
        error "FULL SIP service not found. Deploy first."
        exit 1
    fi
    
    log "Testing FULL SIP health endpoint..."
    HEALTH_RESPONSE=$(curl -s "$SERVICE_URL/health")
    echo "Health Response: $HEALTH_RESPONSE"
    
    if echo "$HEALTH_RESPONSE" | grep -q '"sip_available":true'; then
        success "✅ SIP capabilities are AVAILABLE!"
    else
        warning "⚠️ SIP capabilities may not be ready yet"
    fi
    
    log "🎯 Making test call to +16782960086..."
    CALL_RESPONSE=$(curl -s -X POST "$SERVICE_URL/call" \
        -H "Content-Type: application/json" \
        -d '{"number": "+16782960086", "message": "Hello! This is Callie with full SIP audio capabilities. Can you hear me?"}')
    
    echo "Call Response: $CALL_RESPONSE"
    
    if echo "$CALL_RESPONSE" | grep -q '"success":true'; then
        success "🎉 Call initiated successfully! Check your phone (+16782960086)"
    else
        warning "⚠️ Call may have issues. Check logs for details."
    fi
}

# Main execution
case "${1:-deploy}" in
    "build")
        VERSION=${2:-cloudrun-full}
        log "Building FULL SIP version..."
        build_and_push_full $VERSION
        ;;
    "deploy")
        VERSION=${2:-cloudrun-full}
        log "Full SIP deployment (build + deploy)..."
        build_and_push_full $VERSION
        deploy_full $VERSION
        ;;
    "deploy-only")
        VERSION=${2:-cloudrun-full}
        log "Deploying existing FULL SIP image..."
        deploy_full $VERSION
        ;;
    "test")
        log "Testing FULL SIP deployment..."
        test_full_deployment
        ;;
    "call")
        SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
            --region=$REGION \
            --project=$PROJECT_ID \
            --format="value(status.url)" 2>/dev/null)
        
        if [ -z "$SERVICE_URL" ]; then
            error "Service not found. Deploy first."
            exit 1
        fi
        
        NUMBER=${2:-+16782960086}
        MESSAGE=${3:-"Hello! This is Callie testing full SIP audio capabilities from Cloud Run!"}
        
        log "Making test call to $NUMBER..."
        curl -X POST "$SERVICE_URL/call" \
            -H "Content-Type: application/json" \
            -d "{\"number\": \"$NUMBER\", \"message\": \"$MESSAGE\"}"
        echo ""
        ;;
    "logs")
        log "Showing FULL SIP Cloud Run logs..."
        gcloud logs read "resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME" \
            --project=$PROJECT_ID \
            --limit=100
        ;;
    *)
        echo "Usage: $0 {build|deploy|deploy-only|test|call|logs} [version] [message]"
        echo ""
        echo "Commands:"
        echo "  build      - Build and push FULL SIP Docker image"
        echo "  deploy     - Full deployment (build + deploy)"
        echo "  deploy-only- Deploy existing image"
        echo "  test       - Test the FULL SIP deployment"
        echo "  call       - Make a test call"
        echo "  logs       - Show recent logs"
        echo ""
        echo "Examples:"
        echo "  $0 deploy"
        echo "  $0 test"
        echo "  $0 call +16782960086 'Testing audio'"
        exit 1
        ;;
esac 
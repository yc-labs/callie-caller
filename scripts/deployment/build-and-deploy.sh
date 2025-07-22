#!/bin/bash

# Callie Caller - Build and Deploy to Google Cloud
# Handles versioning, building, pushing to Artifact Registry, and deploying

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
DEFAULT_PROJECT_ID="yc-partners"
DEFAULT_REGION="us-central1"
DEFAULT_REPOSITORY="callie-caller"
DEFAULT_SERVICE_NAME="callie-caller"

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

show_usage() {
    echo "Callie Caller - Build and Deploy to Google Cloud"
    echo ""
    echo "Usage: $0 [OPTIONS] COMMAND"
    echo ""
    echo "Commands:"
    echo "  build      Build Docker image only"
    echo "  push       Build and push to Artifact Registry"
    echo "  deploy     Build, push, and deploy to Cloud Run"
    echo "  version    Bump version and create git tag"
    echo "  firewall   Create required firewall rules"
    echo "  full       Complete deployment (version + build + push + firewall + deploy)"
    echo ""
    echo "Options:"
    echo "  --project ID       Google Cloud Project ID (default: $DEFAULT_PROJECT_ID)"
    echo "  --region REGION    Google Cloud Region (default: $DEFAULT_REGION)"
    echo "  --repository REPO  Artifact Registry repository (default: $DEFAULT_REPOSITORY)"
    echo "  --service NAME     Cloud Run service name (default: $DEFAULT_SERVICE_NAME)"
    echo "  --version VERSION  Specific version to use (default: auto-generate)"
    echo "  --major           Bump major version"
    echo "  --minor           Bump minor version (default)"
    echo "  --patch           Bump patch version"
    echo "  --web-only        Deploy web-only mode (no SIP functionality)"
    echo "  --memory SIZE     Cloud Run memory limit (default: 1Gi)"
    echo "  --cpu COUNT       Cloud Run CPU allocation (default: 1)"
    echo "  --instances NUM   Max Cloud Run instances (default: 5)"
    echo ""
    echo "Examples:"
    echo "  $0 full                              # Complete deployment with auto-version"
    echo "  $0 build --version 1.2.0            # Build specific version"
    echo "  $0 deploy --web-only                 # Deploy web-only mode"
    echo "  $0 version --major                   # Bump major version only"
}

parse_arguments() {
    # Set defaults
    PROJECT_ID="$DEFAULT_PROJECT_ID"
    REGION="$DEFAULT_REGION"
    REPOSITORY="$DEFAULT_REPOSITORY"
    SERVICE_NAME="$DEFAULT_SERVICE_NAME"
    VERSION=""
    VERSION_BUMP="minor"
    WEB_ONLY=false
    MEMORY="1Gi"
    CPU="1"
    MAX_INSTANCES="5"
    COMMAND=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --project)
                PROJECT_ID="$2"
                shift 2
                ;;
            --region)
                REGION="$2"
                shift 2
                ;;
            --repository)
                REPOSITORY="$2"
                shift 2
                ;;
            --service)
                SERVICE_NAME="$2"
                shift 2
                ;;
            --version)
                VERSION="$2"
                shift 2
                ;;
            --major)
                VERSION_BUMP="major"
                shift
                ;;
            --minor)
                VERSION_BUMP="minor"
                shift
                ;;
            --patch)
                VERSION_BUMP="patch"
                shift
                ;;
            --web-only)
                WEB_ONLY=true
                shift
                ;;
            --memory)
                MEMORY="$2"
                shift 2
                ;;
            --cpu)
                CPU="$2"
                shift 2
                ;;
            --instances)
                MAX_INSTANCES="$2"
                shift 2
                ;;
            build|push|deploy|version|firewall|full)
                COMMAND="$1"
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    if [ -z "$COMMAND" ]; then
        log_error "No command specified"
        show_usage
        exit 1
    fi
}

check_dependencies() {
    local missing_deps=()
    
    if ! command -v docker >/dev/null; then
        missing_deps+=("docker")
    fi
    
    if ! command -v gcloud >/dev/null; then
        missing_deps+=("gcloud")
    fi
    
    if ! command -v git >/dev/null; then
        missing_deps+=("git")
    fi
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_error "Missing required dependencies: ${missing_deps[*]}"
        exit 1
    fi
    
    # Check gcloud auth
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
        log_error "Google Cloud not authenticated. Run: gcloud auth login"
        exit 1
    fi
    
    log_success "All dependencies verified"
}

get_current_version() {
    if [ -f "$PROJECT_ROOT/callie_caller/_version.py" ]; then
        python3 -c "exec(open('$PROJECT_ROOT/callie_caller/_version.py').read()); print(__version__)"
    else
        echo "1.0.0"
    fi
}

bump_version() {
    cd "$PROJECT_ROOT"
    
    log_info "Bumping $VERSION_BUMP version..."
    
    if [ -f "scripts/version.py" ]; then
        NEW_VERSION=$(python3 scripts/version.py --release "$VERSION_BUMP" --dry-run)
        python3 scripts/version.py --release "$VERSION_BUMP"
    else
        log_warning "Version script not found, using manual versioning"
        CURRENT_VERSION=$(get_current_version)
        # Simple version bumping logic
        IFS='.' read -r major minor patch <<< "$CURRENT_VERSION"
        case "$VERSION_BUMP" in
            major) NEW_VERSION="$((major + 1)).0.0" ;;
            minor) NEW_VERSION="$major.$((minor + 1)).0" ;;
            patch) NEW_VERSION="$major.$minor.$((patch + 1))" ;;
        esac
        echo "__version__ = \"$NEW_VERSION\"" > callie_caller/_version.py
    fi
    
    # Commit version bump
    git add callie_caller/_version.py
    git commit -m "chore: Bump version to $NEW_VERSION" || true
    
    # Create git tag
    git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION" || true
    
    log_success "Version bumped to $NEW_VERSION"
    VERSION="$NEW_VERSION"
}

build_image() {
    cd "$PROJECT_ROOT"
    
    if [ -z "$VERSION" ]; then
        VERSION=$(get_current_version)
    fi
    
    local dockerfile="Dockerfile"
    local image_name="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/callie-caller"
    
    if [ "$WEB_ONLY" = true ]; then
        dockerfile="Dockerfile.cloudrun"
        image_name="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/callie-caller-web"
        log_info "Building web-only image..."
    else
        log_info "Building full SIP-enabled image..."
    fi
    
    log_info "Building Docker image: $image_name:$VERSION"
    
    docker build \
        --platform linux/amd64 \
        -f "$dockerfile" \
        -t "$image_name:$VERSION" \
        -t "$image_name:latest" \
        --build-arg VERSION="$VERSION" \
        --build-arg BUILD_DATE="$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --build-arg VCS_REF="$(git rev-parse HEAD)" \
        .
    
    log_success "Image built successfully: $image_name:$VERSION"
}

push_image() {
    log_info "Configuring Docker for Artifact Registry..."
    gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet
    
    local image_name="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/callie-caller"
    if [ "$WEB_ONLY" = true ]; then
        image_name="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/callie-caller-web"
    fi
    
    log_info "Pushing image to Artifact Registry..."
    docker push "$image_name:$VERSION"
    docker push "$image_name:latest"
    
    log_success "Image pushed successfully: $image_name:$VERSION"
}

create_firewall_rules() {
    log_info "Creating firewall rules for SIP/RTP traffic..."
    
    # SIP signaling port
    if ! gcloud compute firewall-rules describe callie-sip-signaling --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud compute firewall-rules create callie-sip-signaling \
            --allow udp:5060 \
            --source-ranges 0.0.0.0/0 \
            --description "Callie Caller SIP signaling port" \
            --target-tags callie-caller \
            --project="$PROJECT_ID"
        log_success "Created SIP firewall rule"
    else
        log_info "SIP firewall rule already exists"
    fi
    
    # RTP audio ports
    if ! gcloud compute firewall-rules describe callie-rtp-audio --project="$PROJECT_ID" >/dev/null 2>&1; then
        gcloud compute firewall-rules create callie-rtp-audio \
            --allow udp:10000-10004 \
            --source-ranges 0.0.0.0/0 \
            --description "Callie Caller RTP audio ports" \
            --target-tags callie-caller \
            --project="$PROJECT_ID"
        log_success "Created RTP firewall rule"
    else
        log_info "RTP firewall rule already exists"
    fi
}

deploy_to_cloud_run() {
    local image_name="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/callie-caller"
    local service_name="$SERVICE_NAME"
    
    if [ "$WEB_ONLY" = true ]; then
        image_name="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/callie-caller-web"
        service_name="$SERVICE_NAME-web"
    fi
    
    log_info "Deploying to Cloud Run: $service_name"
    
    local env_vars="USE_UPNP=false,CONTAINER_MODE=true,CLOUD_RUN_MODE=true"
    if [ "$WEB_ONLY" = true ]; then
        env_vars="$env_vars,WEB_ONLY_MODE=true"
    fi
    
    gcloud run deploy "$service_name" \
        --image "$image_name:$VERSION" \
        --region "$REGION" \
        --platform managed \
        --allow-unauthenticated \
        --port 8080 \
        --memory "$MEMORY" \
        --cpu "$CPU" \
        --max-instances "$MAX_INSTANCES" \
        --timeout 300 \
        --set-env-vars="$env_vars" \
        --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,ZOHO_SIP_USERNAME=zoho-sip-username:latest,ZOHO_SIP_PASSWORD=zoho-sip-password:latest" \
        --project="$PROJECT_ID"
    
    # Get service URL
    SERVICE_URL=$(gcloud run services describe "$service_name" --region="$REGION" --project="$PROJECT_ID" --format="value(status.url)")
    
    log_success "Deployment complete!"
    log_info "Service URL: $SERVICE_URL"
    log_info "Health check: $SERVICE_URL/health"
    
    if [ "$WEB_ONLY" != true ]; then
        log_info "Full SIP functionality deployed to Cloud Run."
        log_warning "Note: Inbound RTP requires external load balancer or ingress for UDP."
        log_info "For inbound calls, consider:"
        log_info "  • Google Compute Engine with static IP and port forwarding"
        log_info "  • Load Balancer with UDP support for inbound RTP"
        log_info "  • Your local Docker setup handles inbound calls perfectly"
    fi
}

main() {
    parse_arguments "$@"
    
    log_info "Callie Caller Deployment Pipeline"
    log_info "Project: $PROJECT_ID | Region: $REGION | Command: $COMMAND"
    
    check_dependencies
    
    cd "$PROJECT_ROOT"
    
    case "$COMMAND" in
        version)
            bump_version
            ;;
            
        build)
            build_image
            ;;
            
        push)
            build_image
            push_image
            ;;
            
        firewall)
            create_firewall_rules
            ;;
            
        deploy)
            if [ -z "$VERSION" ]; then
                VERSION=$(get_current_version)
            fi
            deploy_to_cloud_run
            ;;
            
        full)
            bump_version
            build_image
            push_image
            if [ "$WEB_ONLY" != true ]; then
                create_firewall_rules
            fi
            deploy_to_cloud_run
            
            # Try to push git changes
            log_info "Pushing git changes..."
            git push origin main --tags 2>/dev/null || log_warning "Could not push git changes"
            ;;
            
        *)
            log_error "Unknown command: $COMMAND"
            show_usage
            exit 1
            ;;
    esac
    
    log_success "Pipeline completed successfully! 🎉"
}

# Run main function
main "$@" 
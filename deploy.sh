#!/bin/bash

# Callie Caller - Deployment Script
# Handles complete deployment process including GAR setup

set -euo pipefail

# Configuration
PROJECT_NAME="callie-caller"
DEFAULT_REGION="us-central1"
DEFAULT_REPOSITORY="callie-caller"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

usage() {
    cat << EOF
Usage: $0 [OPTIONS] COMMAND

Deploy Callie Caller to production environments

COMMANDS:
    setup       Set up Google Artifact Registry repository
    build       Build and push Docker image
    deploy      Deploy to production
    status      Check deployment status
    logs        Show application logs
    stop        Stop running deployment
    cleanup     Clean up old images and containers

OPTIONS:
    -p, --project PROJECT_ID    Google Cloud Project ID (required)
    -r, --region REGION         Artifact Registry region (default: ${DEFAULT_REGION})
    -R, --repository REPO       Artifact Registry repository (default: ${DEFAULT_REPOSITORY})
    -v, --version VERSION       Version to deploy (default: latest)
    -e, --env-file FILE         Environment file path (default: .env)
    --dry-run                   Show what would be done without executing
    -h, --help                  Show this help message

EXAMPLES:
    # Set up GAR repository
    $0 --project my-gcp-project setup

    # Build and deploy version 1.0.1
    $0 --project my-project --version 1.0.1 build deploy

    # Deploy latest version
    $0 --project my-project deploy

    # Check deployment status
    $0 status

    # View logs
    $0 logs

ENVIRONMENT VARIABLES:
    GCP_PROJECT_ID             Google Cloud Project ID
    GAR_REGION                 Artifact Registry region
    GAR_REPOSITORY             Artifact Registry repository name

EOF
}

# Parse command line arguments
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GAR_REGION:-$DEFAULT_REGION}"
REPOSITORY="${GAR_REPOSITORY:-$DEFAULT_REPOSITORY}"
VERSION="latest"
ENV_FILE=".env"
DRY_RUN=false
COMMAND=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--project)
            PROJECT_ID="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -R|--repository)
            REPOSITORY="$2"
            shift 2
            ;;
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -e|--env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        setup|build|deploy|status|logs|stop|cleanup)
            COMMAND="$1"
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate command
if [[ -z "$COMMAND" ]]; then
    log_error "Command is required"
    usage
    exit 1
fi

# Validate project ID for commands that need it
if [[ "$COMMAND" =~ ^(setup|build|deploy)$ ]] && [[ -z "$PROJECT_ID" ]]; then
    log_error "Google Cloud Project ID is required for $COMMAND command"
    exit 1
fi

# GAR configuration
GAR_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}"
GAR_IMAGE="${GAR_BASE}/${PROJECT_NAME}:${VERSION}"

# Execute dry run
if [[ "$DRY_RUN" == true ]]; then
    log_warning "DRY RUN MODE - Commands will be displayed but not executed"
    DRY_RUN_PREFIX="echo [DRY RUN]"
else
    DRY_RUN_PREFIX=""
fi

# Command implementations
setup_gar() {
    log_info "Setting up Google Artifact Registry"
    log_info "Project: $PROJECT_ID"
    log_info "Region: $REGION"
    log_info "Repository: $REPOSITORY"
    
    # Check if gcloud is installed
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI is required"
        exit 1
    fi
    
    # Set project
    log_info "Setting active project to $PROJECT_ID"
    $DRY_RUN_PREFIX gcloud config set project "$PROJECT_ID"
    
    # Enable Artifact Registry API
    log_info "Enabling Artifact Registry API"
    $DRY_RUN_PREFIX gcloud services enable artifactregistry.googleapis.com
    
    # Create repository if it doesn't exist
    log_info "Creating Artifact Registry repository: $REPOSITORY"
    $DRY_RUN_PREFIX gcloud artifacts repositories create "$REPOSITORY" \
        --repository-format=docker \
        --location="$REGION" \
        --description="Callie Caller AI Voice Agent container images" \
        || log_warning "Repository might already exist"
    
    # Configure Docker authentication
    log_info "Configuring Docker authentication"
    $DRY_RUN_PREFIX gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
    
    log_success "Google Artifact Registry setup completed"
    log_info "Repository URL: ${GAR_BASE}"
}

build_image() {
    log_info "Building and pushing Docker image"
    log_info "Version: $VERSION"
    log_info "Target: $GAR_IMAGE"
    
    # Build and push using our build script
    BUILD_ARGS=(
        --project "$PROJECT_ID"
        --region "$REGION"
        --repository "$REPOSITORY"
        --push
    )
    
    if [[ "$VERSION" != "latest" ]]; then
        BUILD_ARGS+=(--version "$VERSION")
    fi
    
    if [[ "$VERSION" == "latest" ]] || [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        BUILD_ARGS+=(--latest)
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log_info "Would run: ./build.sh ${BUILD_ARGS[*]}"
    else
        ./build.sh "${BUILD_ARGS[@]}"
    fi
}

deploy_application() {
    log_info "Deploying Callie Caller to production"
    log_info "Image: $GAR_IMAGE"
    log_info "Environment file: $ENV_FILE"
    
    # Check if environment file exists
    if [[ ! -f "$ENV_FILE" ]]; then
        log_error "Environment file not found: $ENV_FILE"
        log_info "Please create the environment file with your configuration:"
        log_info "  cp config.env.template $ENV_FILE"
        log_info "  # Edit $ENV_FILE with your credentials"
        exit 1
    fi
    
    # Export GAR image for docker-compose
    export GAR_IMAGE="$GAR_IMAGE"
    
    # Load environment variables
    if [[ "$DRY_RUN" == false ]]; then
        set -a
        source "$ENV_FILE"
        set +a
    fi
    
    # Deploy using docker-compose
    log_info "Starting deployment with docker-compose"
    
    if [[ "$DRY_RUN" == true ]]; then
        log_info "Would run: docker-compose -f docker-compose.prod.yml pull"
        log_info "Would run: docker-compose -f docker-compose.prod.yml up -d"
    else
        # Pull latest image
        docker-compose -f docker-compose.prod.yml pull
        
        # Deploy
        docker-compose -f docker-compose.prod.yml up -d
        
        # Wait for health check
        log_info "Waiting for application to become healthy..."
        sleep 10
        
        # Check health
        if check_health; then
            log_success "Deployment completed successfully!"
            show_deployment_info
        else
            log_error "Deployment health check failed"
            show_logs
            exit 1
        fi
    fi
}

check_health() {
    # Check if container is running
    if ! docker-compose -f docker-compose.prod.yml ps callie-caller | grep -q "Up"; then
        return 1
    fi
    
    # Check health endpoint
    if command -v curl &> /dev/null; then
        if curl -f -s http://localhost:8080/health > /dev/null; then
            return 0
        fi
    fi
    
    return 1
}

show_status() {
    log_info "Deployment Status"
    echo
    
    # Show container status
    log_info "Container Status:"
    docker-compose -f docker-compose.prod.yml ps
    echo
    
    # Show health status
    log_info "Health Check:"
    if check_health; then
        log_success "✅ Application is healthy"
    else
        log_error "❌ Application is not healthy"
    fi
    echo
    
    # Show resource usage
    log_info "Resource Usage:"
    docker stats callie-caller-prod --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
}

show_logs() {
    log_info "Application Logs (last 50 lines)"
    docker-compose -f docker-compose.prod.yml logs --tail=50 callie-caller
}

stop_deployment() {
    log_info "Stopping Callie Caller deployment"
    
    if [[ "$DRY_RUN" == true ]]; then
        log_info "Would run: docker-compose -f docker-compose.prod.yml down"
    else
        docker-compose -f docker-compose.prod.yml down
        log_success "Deployment stopped"
    fi
}

cleanup_deployment() {
    log_info "Cleaning up old images and containers"
    
    if [[ "$DRY_RUN" == true ]]; then
        log_info "Would run: docker system prune -f"
        log_info "Would remove old callie-caller images"
    else
        # Remove old containers
        docker container prune -f
        
        # Remove old images (keep last 3 versions)
        docker images "${GAR_BASE}/${PROJECT_NAME}" --format "{{.ID}} {{.Tag}}" | \
        grep -v latest | sort -rV | tail -n +4 | cut -d' ' -f1 | \
        xargs -r docker rmi
        
        log_success "Cleanup completed"
    fi
}

show_deployment_info() {
    echo
    log_success "🎉 Callie Caller is deployed and running!"
    echo
    log_info "📋 Deployment Information:"
    echo "   • Image: $GAR_IMAGE"
    echo "   • Web Interface: http://localhost:8080"
    echo "   • Health Check: http://localhost:8080/health"
    echo "   • Container: callie-caller-prod"
    echo
    log_info "📊 Management Commands:"
    echo "   • Status: $0 status"
    echo "   • Logs: $0 logs"
    echo "   • Stop: $0 stop"
    echo "   • Cleanup: $0 cleanup"
}

# Execute command
case "$COMMAND" in
    setup)
        setup_gar
        ;;
    build)
        build_image
        ;;
    deploy)
        deploy_application
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    stop)
        stop_deployment
        ;;
    cleanup)
        cleanup_deployment
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac 
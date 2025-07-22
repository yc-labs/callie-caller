#!/bin/bash

# Callie Caller - Build and Deploy Script
# Builds Docker images and pushes to Google Artifact Registry

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
Usage: $0 [OPTIONS]

Build and deploy Callie Caller Docker images to Google Artifact Registry

OPTIONS:
    -v, --version VERSION       Version to build (default: auto-detected from git)
    -p, --project PROJECT_ID    Google Cloud Project ID (required)
    -r, --region REGION         Artifact Registry region (default: ${DEFAULT_REGION})
    -R, --repository REPO       Artifact Registry repository (default: ${DEFAULT_REPOSITORY})
    -t, --tag TAG              Additional tag for image (default: version only)
    --push                     Push to Artifact Registry after building
    --latest                   Also tag as 'latest'
    --no-cache                 Build without Docker cache
    --platform PLATFORM       Target platform (e.g., linux/amd64,linux/arm64)
    -h, --help                 Show this help message

EXAMPLES:
    # Build version 1.0.1 and push to GAR
    $0 --version 1.0.1 --project my-gcp-project --push

    # Build current git version for multiple platforms
    $0 --project my-project --platform linux/amd64,linux/arm64 --push --latest

    # Build development version locally
    $0 --version dev-$(date +%Y%m%d) --tag development

ENVIRONMENT VARIABLES:
    GCP_PROJECT_ID             Google Cloud Project ID
    GAR_REGION                 Artifact Registry region
    GAR_REPOSITORY             Artifact Registry repository name
    DOCKER_BUILDKIT            Enable Docker BuildKit (recommended)

EOF
}

# Parse command line arguments
VERSION=""
PROJECT_ID="${GCP_PROJECT_ID:-}"
REGION="${GAR_REGION:-$DEFAULT_REGION}"
REPOSITORY="${GAR_REPOSITORY:-$DEFAULT_REPOSITORY}"
ADDITIONAL_TAG=""
PUSH=false
TAG_LATEST=false
NO_CACHE=false
PLATFORM=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
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
        -t|--tag)
            ADDITIONAL_TAG="$2"
            shift 2
            ;;
        --push)
            PUSH=true
            shift
            ;;
        --latest)
            TAG_LATEST=true
            shift
            ;;
        --no-cache)
            NO_CACHE=true
            shift
            ;;
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$PROJECT_ID" ]]; then
    log_error "Google Cloud Project ID is required. Use --project or set GCP_PROJECT_ID environment variable."
    exit 1
fi

# Auto-detect version if not provided
if [[ -z "$VERSION" ]]; then
    if command -v git &> /dev/null && git rev-parse --git-dir > /dev/null 2>&1; then
        # Get version from git tag or commit
        if git describe --tags --exact-match 2>/dev/null; then
            VERSION=$(git describe --tags --exact-match)
        else
            # Use commit hash for development builds
            SHORT_COMMIT=$(git rev-parse --short HEAD)
            VERSION="dev-${SHORT_COMMIT}"
        fi
        log_info "Auto-detected version: $VERSION"
    else
        log_error "Version not specified and git not available. Use --version flag."
        exit 1
    fi
fi

# Build metadata
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
VCS_REF=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
BUILD_NUMBER="${BUILD_NUMBER:-$(date +%Y%m%d%H%M)}"

# Image names
LOCAL_IMAGE="${PROJECT_NAME}:${VERSION}"
GAR_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}"
GAR_IMAGE="${GAR_BASE}/${PROJECT_NAME}:${VERSION}"

log_info "Building Callie Caller Docker image"
log_info "Version: $VERSION"
log_info "Project: $PROJECT_ID"
log_info "Registry: $GAR_BASE"

# Check if gcloud is installed and authenticated for push operations
if [[ "$PUSH" == true ]]; then
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI is required for pushing to Artifact Registry"
        exit 1
    fi
    
    # Configure Docker to use gcloud as credential helper
    log_info "Configuring Docker authentication for Artifact Registry"
    gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
fi

# Prepare build arguments
BUILD_ARGS=(
    --build-arg "VERSION=$VERSION"
    --build-arg "BUILD_DATE=$BUILD_DATE"
    --build-arg "VCS_REF=$VCS_REF"
    --build-arg "BUILD_NUMBER=$BUILD_NUMBER"
)

# Add platform if specified
if [[ -n "$PLATFORM" ]]; then
    BUILD_ARGS+=(--platform "$PLATFORM")
fi

# Add no-cache if specified
if [[ "$NO_CACHE" == true ]]; then
    BUILD_ARGS+=(--no-cache)
fi

# Build the image
log_info "Building Docker image: $LOCAL_IMAGE"
docker build "${BUILD_ARGS[@]}" -t "$LOCAL_IMAGE" .

if [[ $? -eq 0 ]]; then
    log_success "Successfully built $LOCAL_IMAGE"
else
    log_error "Failed to build Docker image"
    exit 1
fi

# Tag for Artifact Registry
if [[ "$PUSH" == true ]]; then
    log_info "Tagging image for Artifact Registry: $GAR_IMAGE"
    docker tag "$LOCAL_IMAGE" "$GAR_IMAGE"
    
    # Additional tag if specified
    if [[ -n "$ADDITIONAL_TAG" ]]; then
        ADDITIONAL_GAR_IMAGE="${GAR_BASE}/${PROJECT_NAME}:${ADDITIONAL_TAG}"
        log_info "Adding additional tag: $ADDITIONAL_GAR_IMAGE"
        docker tag "$LOCAL_IMAGE" "$ADDITIONAL_GAR_IMAGE"
    fi
    
    # Latest tag if specified
    if [[ "$TAG_LATEST" == true ]]; then
        LATEST_GAR_IMAGE="${GAR_BASE}/${PROJECT_NAME}:latest"
        log_info "Adding latest tag: $LATEST_GAR_IMAGE"
        docker tag "$LOCAL_IMAGE" "$LATEST_GAR_IMAGE"
    fi
fi

# Push to Artifact Registry
if [[ "$PUSH" == true ]]; then
    log_info "Pushing images to Google Artifact Registry"
    
    # Push main version
    log_info "Pushing $GAR_IMAGE"
    docker push "$GAR_IMAGE"
    
    # Push additional tag
    if [[ -n "$ADDITIONAL_TAG" ]]; then
        log_info "Pushing $ADDITIONAL_GAR_IMAGE"
        docker push "$ADDITIONAL_GAR_IMAGE"
    fi
    
    # Push latest tag
    if [[ "$TAG_LATEST" == true ]]; then
        log_info "Pushing $LATEST_GAR_IMAGE"
        docker push "$LATEST_GAR_IMAGE"
    fi
    
    log_success "Successfully pushed images to Artifact Registry"
    
    # Display deployment commands
    echo
    log_info "Deployment commands:"
    echo "  docker pull $GAR_IMAGE"
    echo "  docker run -d --name callie-caller -p 8080:8080 $GAR_IMAGE"
    echo
    log_info "Or use docker-compose with:"
    echo "  export GAR_IMAGE=$GAR_IMAGE"
    echo "  docker-compose -f docker-compose.prod.yml up -d"
else
    log_success "Build completed. Local image: $LOCAL_IMAGE"
    echo
    log_info "To push to Artifact Registry, run:"
    echo "  $0 --version $VERSION --project $PROJECT_ID --push"
fi

log_success "Build process completed!" 
#!/bin/bash
set -e

# --- Configuration ---
PROJECT_ID="yc-partners"
ZONE="us-central1-a"
VM_NAME="callie-caller-vm"
MACHINE_TYPE="e2-small"
NETWORK_TAG="callie-caller"
STARTUP_SCRIPT="startup-script.sh"

# Docker/GAR Configuration
GAR_REGION="us-central1"
GAR_REPOSITORY="callie-caller"
IMAGE_NAME="callie-caller-prod"
IMAGE_TAG=${VERSION:-"latest"}
IMAGE_URI="${GAR_REGION}-docker.pkg.dev/${PROJECT_ID}/${GAR_REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"

# Colors for output
BLUE='\033[0;34m'
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

# --- Deployment Functions ---

# Create or update the VM and run setup script
provision_vm() {
    log "Checking for existing VM: $VM_NAME..."
    if ! gcloud compute instances describe $VM_NAME --zone=$ZONE &>/dev/null; then
        log "Creating new VM: $VM_NAME..."
        gcloud compute instances create $VM_NAME \
            --project=$PROJECT_ID \
            --zone=$ZONE \
            --machine-type=$MACHINE_TYPE \
            --network-interface=network-tier=PREMIUM \
            --tags=$NETWORK_TAG \
            --image-family="debian-12" \
            --image-project="debian-cloud" \
            --boot-disk-size=20GB \
            --scopes=cloud-platform
        success "VM '$VM_NAME' created."
        log "Waiting 60 seconds for VM to initialize before setup..."
        sleep 60
    fi
    # Ensure firewall rules exist for the default network
    log "Ensuring firewall rules are configured..."
    if ! gcloud compute firewall-rules describe callie-web-default &>/dev/null; then
        log "Creating firewall rule for web traffic..."
        gcloud compute firewall-rules create callie-web-default \
            --network=default \
            --allow=tcp:8080,tcp:80,tcp:443 \
            --source-ranges=0.0.0.0/0 \
            --target-tags=callie-caller \
            --description="Allow web traffic to Callie on default network"
    fi
    
    if ! gcloud compute firewall-rules describe callie-sip-default &>/dev/null; then
        log "Creating firewall rule for SIP traffic..."
        gcloud compute firewall-rules create callie-sip-default \
            --network=default \
            --allow=udp:5060,tcp:5060 \
            --source-ranges=0.0.0.0/0 \
            --target-tags=callie-caller \
            --description="Allow SIP signaling to Callie on default network"
    fi
    
    if ! gcloud compute firewall-rules describe callie-rtp-default &>/dev/null; then
        log "Creating firewall rule for RTP traffic..."
        gcloud compute firewall-rules create callie-rtp-default \
            --network=default \
            --allow=udp:10000-10100 \
            --source-ranges=0.0.0.0/0 \
            --target-tags=callie-caller \
            --description="Allow RTP audio traffic to Callie on default network"
    fi
    
    # Always upload and run the latest setup script
    log "Running setup script on $VM_NAME..."
    gcloud compute scp $STARTUP_SCRIPT $VM_NAME:~/ --zone=$ZONE
    gcloud compute ssh $VM_NAME --zone=$ZONE --command="sudo bash ~/startup-script.sh"
    success "VM setup script executed."
}

# Build and push the Docker image
build_and_push_image() {
    log "Building and pushing Docker image: $IMAGE_URI"
    gcloud auth configure-docker ${GAR_REGION}-docker.pkg.dev -q
    docker buildx build \
        --platform linux/amd64 \
        --tag $IMAGE_URI \
        --file Dockerfile.prod \
        --push \
        .
    success "Image pushed to Artifact Registry."
}

# Deploy the container to the VM
deploy_container() {
    log "Deploying container to $VM_NAME..."
    gcloud compute ssh $VM_NAME --zone=$ZONE --command="
        sudo /usr/bin/docker pull $IMAGE_URI && \
        sudo /usr/bin/docker stop callie-caller-container 2>/dev/null || true && \
        sudo /usr/bin/docker rm callie-caller-container 2>/dev/null || true && \
        sudo /usr/bin/docker run -d --restart=always \
            --name callie-caller-container \
            --network=host \
            --env-file /home/callie/callie-caller/.env \
            $IMAGE_URI
    "
    success "Container deployed and started on $VM_NAME."
}

# Full deployment process
full_deploy() {
    provision_vm
    build_and_push_image
    deploy_container
    IP_ADDRESS=$(gcloud compute instances describe $VM_NAME --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)')
    success "Deployment complete! Application is running at http://${IP_ADDRESS}:8080"
}

# --- Command Line Interface ---
case "$1" in
    "deploy")
        full_deploy
        ;;
    "build")
        build_and_push_image
        ;;
    "run")
        deploy_container
        ;;
    "logs")
        log "Tailing container logs... (Press Ctrl+C to exit)"
        gcloud compute ssh $VM_NAME --zone=$ZONE --command="sudo docker logs -f callie-caller-container"
        ;;
    "ssh")
        log "Connecting to VM..."
        gcloud compute ssh $VM_NAME --zone=$ZONE
        ;;
    "provision")
        provision_vm
        ;;
    *)
        echo "Usage: $0 {deploy|build|run|logs|ssh|provision}"
        exit 1
        ;;
esac 
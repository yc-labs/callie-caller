#!/bin/bash

# Callie Caller - Static Port Setup and Docker Deployment
# Complete automation for Docker deployment with static ports

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REQUIRED_PORTS=(5060 10000 10001 10002 10003 10004)
DOCKER_COMPOSE_FILE="docker-compose-static-ports.yml"
ENV_FILE="docker-secrets.env"

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

get_local_ip() {
    # Get the primary local IP address
    if command -v ifconfig >/dev/null; then
        ifconfig | grep "inet " | grep -v 127.0.0.1 | grep -v "inet 169.254" | awk '{print $2}' | head -n1
    elif command -v ip >/dev/null; then
        ip route get 8.8.8.8 | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}'
    else
        echo "192.168.1.100"  # fallback
    fi
}

check_docker() {
    if ! command -v docker >/dev/null; then
        log_error "Docker is not installed!"
        exit 1
    fi
    
    if ! command -v docker-compose >/dev/null; then
        log_error "Docker Compose is not installed!"
        exit 1
    fi
    
    log_success "Docker environment verified"
}

check_port_availability() {
    local unavailable_ports=()
    
    for port in "${REQUIRED_PORTS[@]}"; do
        if lsof -i :"$port" >/dev/null 2>&1; then
            unavailable_ports+=("$port")
        fi
    done
    
    if [ ${#unavailable_ports[@]} -gt 0 ]; then
        log_warning "The following ports are in use: ${unavailable_ports[*]}"
        log_info "This may affect SIP/RTP functionality"
    else
        log_success "All required ports are available"
    fi
}

create_secrets_env() {
    cd "$PROJECT_ROOT"
    
    log_info "Creating secrets environment file..."
    
    if command -v gcloud >/dev/null && gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
        log_info "Fetching credentials from Google Cloud Secret Manager..."
        
        cat > "$ENV_FILE" << EOF
# Callie Caller Environment - Generated $(date)
# Fetched from Google Cloud Secret Manager

# API Credentials
GEMINI_API_KEY=$(gcloud secrets versions access latest --secret="gemini-api-key" 2>/dev/null || echo "YOUR_GEMINI_API_KEY")
ZOHO_SIP_USERNAME=$(gcloud secrets versions access latest --secret="zoho-sip-username" 2>/dev/null || echo "YOUR_ZOHO_USERNAME")
ZOHO_SIP_PASSWORD=$(gcloud secrets versions access latest --secret="zoho-sip-password" 2>/dev/null || echo "YOUR_ZOHO_PASSWORD")

# SIP Configuration
ZOHO_SIP_SERVER=us3-proxy2.zohovoice.com
SIP_PORT=5060

# RTP Configuration - Static Ports
RTP_PORT=10000
RTP_PORT_RANGE_START=10000
RTP_PORT_RANGE_END=10004

# Container Configuration
USE_UPNP=false
CONTAINER_MODE=true
SERVER_PORT=8080
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1

# Test Configuration
TEST_CALL_NUMBER=+16782960086
EOF
        
        log_success "Secrets environment file created: $ENV_FILE"
    else
        log_warning "Google Cloud CLI not authenticated. Creating template..."
        
        cat > "$ENV_FILE" << EOF
# Callie Caller Environment - Template
# Replace placeholder values with actual credentials

# API Credentials (REQUIRED - Replace these!)
GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
ZOHO_SIP_USERNAME=YOUR_ZOHO_USERNAME_HERE
ZOHO_SIP_PASSWORD=YOUR_ZOHO_PASSWORD_HERE

# SIP Configuration
ZOHO_SIP_SERVER=us3-proxy2.zohovoice.com
SIP_PORT=5060

# RTP Configuration - Static Ports
RTP_PORT=10000
RTP_PORT_RANGE_START=10000
RTP_PORT_RANGE_END=10004

# Container Configuration
USE_UPNP=false
CONTAINER_MODE=true
SERVER_PORT=8080
LOG_LEVEL=INFO
PYTHONUNBUFFERED=1

# Test Configuration
TEST_CALL_NUMBER=+16782960086
EOF
        
        log_warning "Please edit $ENV_FILE and add your actual credentials!"
    fi
}

show_router_configuration() {
    local local_ip
    local_ip=$(get_local_ip)
    
    echo ""
    log_info "ROUTER CONFIGURATION REQUIRED"
    echo "=================================="
    echo "Configure these EXACT port forwards on your router:"
    echo ""
    echo "Protocol | External Port | Internal IP   | Internal Port | Description"
    echo "---------|---------------|---------------|---------------|------------------"
    echo "UDP      | 5060          | $local_ip | 5060          | SIP Signaling"
    echo "UDP      | 10000         | $local_ip | 10000         | Primary RTP Audio"
    echo "UDP      | 10001         | $local_ip | 10001         | Backup RTP Audio"
    echo "UDP      | 10002         | $local_ip | 10002         | Additional RTP"
    echo "UDP      | 10003         | $local_ip | 10003         | Additional RTP"
    echo "UDP      | 10004         | $local_ip | 10004         | Additional RTP"
    echo ""
    log_info "💡 TIP: Run 'python scripts/networking/configure-router-upnp.py' to configure automatically!"
    echo ""
}

deploy_docker() {
    cd "$PROJECT_ROOT"
    
    log_info "Deploying Callie Caller with static ports..."
    
    # Stop any existing deployment
    if docker-compose -f "$DOCKER_COMPOSE_FILE" ps -q >/dev/null 2>&1; then
        log_info "Stopping existing deployment..."
        docker-compose -f "$DOCKER_COMPOSE_FILE" down
    fi
    
    # Build and start
    log_info "Building and starting containers..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" up --build -d
    
    # Wait for health check
    log_info "Waiting for service to be healthy..."
    sleep 10
    
    # Check health
    if curl -s http://localhost:8080/health >/dev/null 2>&1; then
        log_success "Callie Caller is running and healthy!"
        
        # Show status
        echo ""
        log_info "Service Status:"
        curl -s http://localhost:8080/health | python3 -m json.tool 2>/dev/null || echo "Health check endpoint responding"
        
        echo ""
        log_info "Available endpoints:"
        echo "  • Health: http://localhost:8080/health"
        echo "  • Make Call: POST http://localhost:8080/call"
        echo "  • Logs: docker-compose -f $DOCKER_COMPOSE_FILE logs -f"
        
    else
        log_error "Service health check failed!"
        log_info "Check logs: docker-compose -f $DOCKER_COMPOSE_FILE logs"
        return 1
    fi
}

show_usage() {
    echo "Callie Caller - Static Port Setup and Docker Deployment"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  setup      Create environment file and show router config"
    echo "  deploy     Deploy to Docker with static ports"
    echo "  status     Show deployment status"
    echo "  logs       Show container logs"
    echo "  stop       Stop deployment"
    echo "  clean      Stop and remove all containers/images"
    echo ""
    echo "Examples:"
    echo "  $0 setup    # First time setup"
    echo "  $0 deploy   # Deploy to Docker"
    echo "  $0 logs     # View logs"
}

main() {
    local command="${1:-help}"
    
    case "$command" in
        setup)
            log_info "Setting up Callie Caller..."
            check_docker
            check_port_availability
            create_secrets_env
            show_router_configuration
            log_success "Setup complete! Run '$0 deploy' to start."
            ;;
            
        deploy)
            log_info "Deploying Callie Caller..."
            check_docker
            
            if [ ! -f "$PROJECT_ROOT/$ENV_FILE" ]; then
                log_warning "Environment file not found. Running setup first..."
                create_secrets_env
            fi
            
            deploy_docker
            ;;
            
        status)
            cd "$PROJECT_ROOT"
            docker-compose -f "$DOCKER_COMPOSE_FILE" ps
            echo ""
            if curl -s http://localhost:8080/health >/dev/null 2>&1; then
                log_success "Service is healthy"
                curl -s http://localhost:8080/health | python3 -m json.tool 2>/dev/null
            else
                log_warning "Service not responding"
            fi
            ;;
            
        logs)
            cd "$PROJECT_ROOT"
            docker-compose -f "$DOCKER_COMPOSE_FILE" logs -f
            ;;
            
        stop)
            cd "$PROJECT_ROOT"
            log_info "Stopping deployment..."
            docker-compose -f "$DOCKER_COMPOSE_FILE" down
            log_success "Deployment stopped"
            ;;
            
        clean)
            cd "$PROJECT_ROOT"
            log_info "Cleaning up all containers and images..."
            docker-compose -f "$DOCKER_COMPOSE_FILE" down --rmi all --volumes --remove-orphans
            log_success "Cleanup complete"
            ;;
            
        help|--help|-h)
            show_usage
            ;;
            
        *)
            log_error "Unknown command: $command"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@" 
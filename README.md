# 📞 Callie Caller

An AI voice agent that powers phone conversations via SIP, enabling real-time dialogue between callers and AI using Google's Gemini Multimodal Live API.

## 🎉 New: PJSUA2 Implementation

**We've refactored the SIP stack to use PJSUA2, solving the 30-second call drop issue!**

### Key Benefits:
- ✅ **No more 30-second call drops** - Automatic session timer handling (RFC 4028)
- 🔧 **Robust SIP implementation** - Built on the industry-standard PJSIP library
- 🌐 **Better NAT traversal** - Built-in STUN/ICE support
- 📈 **Production-ready** - Used by millions of VoIP applications worldwide

See [docs/pjsua2-refactoring.md](docs/pjsua2-refactoring.md) for details.

## Core Features

- **Real-time Voice Conversations**: Natural, real-time AI-powered phone conversations.
- **SIP Integration**: Compatible with standard SIP providers (e.g., Zoho Voice).
- **Docker-on-VM Deployment**: The best of both worlds: a simple, reliable single-VM network architecture with a clean, portable, and consistent containerized application.
- **Automated Deployment**: A single script to provision the VM, build the Docker image, push it to a registry, and run it on the VM.
- **Centralized Logging**: All container logs can be viewed via the `deploy-vm.sh` script.

## Architecture

The architecture is a simple and powerful Docker-on-VM model:

1.  **Compute Engine VM**: A single VM (e.g., `e2-small`) with a static public IP address serves as the host. Docker is installed on this VM.
2.  **Google Artifact Registry**: The production Docker image is stored and versioned in Google Artifact Registry.
3.  **Docker Container**: The application runs inside a Docker container on the VM. The container uses **host networking**, which allows the SIP and RTP ports to be exposed directly without complex port mapping.
4.  **Firewall Rules**: Google Cloud firewall rules allow inbound UDP traffic for SIP (port 5060) and RTP (ports 10000-10100) directly to the VM.
5.  **`.env` File**: Secrets are fetched from Google Secret Manager during the initial VM provisioning and stored in an `.env` file, which is then used by the Docker container.

This model is robust, secure, and easy to manage.

## Deployment Guide

This project is designed to be deployed to a Google Compute Engine VM as a Docker container. The `deploy-vm.sh` script automates the entire process.

### Prerequisites

1.  **Google Cloud Project**: A GCP project with billing enabled.
2.  **gcloud CLI**: The Google Cloud CLI installed and authenticated (`gcloud auth login`).
3.  **Docker**: Docker must be running on your local machine to build the image.
4.  **APIs Enabled**: Ensure the Compute Engine API, Secret Manager API, and Artifact Registry API are enabled.
5.  **Secrets Configured**: You must have the following secrets stored in Google Cloud Secret Manager:
    *   `zoho-sip-username`
    *   `zoho-sip-password`
    *   `gemini-api-key`

### One-Step Deployment

The `deploy-vm.sh` script is idempotent and handles everything from VM creation to running the container.

```bash
# From the root of the repository
./deploy-vm.sh deploy
```

This command will:
1.  Create a new `e2-small` VM named `callie-caller-vm` if it doesn't already exist and run a setup script to install Docker.
2.  Build the production Docker image from `Dockerfile.prod`.
3.  Push the image to Google Artifact Registry.
4.  SSH into the VM, pull the latest image, and run it as a container with a restart policy.

### Managing the Deployment

The `deploy-vm.sh` script provides several commands to manage your deployment:

-   **Deploy a New Version**: To build and push a new image and then run it on the VM:
    ```bash
    ./deploy-vm.sh deploy
    ```
-   **Build & Push Only**:
    ```bash
    ./deploy-vm.sh build
    ```
-   **Run Latest Image on VM**:
    ```bash
    ./deploy-vm.sh run
    ```
-   **View Container Logs**:
    ```bash
    ./deploy-vm.sh logs
    ```
-   **SSH into the VM**:
    ```bash
    ./deploy-vm.sh ssh
    ```

## Local Development (with Docker)

For local development, a simplified `docker-compose.yml` is provided.

### Prerequisites

-   Docker and Docker Compose
-   A `.env` file created from `config.env.template` with your local credentials.

### Running Locally

```bash
# Build and run the container
docker-compose up --build -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

The local Docker setup uses **host networking** to simplify SIP/RTP communication and mounts your local code directory into the container, allowing for live code changes without rebuilding.

## Core Scripts

-   `deploy-vm.sh`: The main script for managing the Google Cloud VM deployment.
-   `startup-script.sh`: The provisioning script that runs on the VM to install Docker.
-   `main.py`: The single entry point for the application.
-   `Dockerfile.prod`: The Dockerfile used for building the production image.
-   `docker-compose.yml`: The configuration for local development. 
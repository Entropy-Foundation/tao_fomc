#!/bin/bash

# Remote deployment script for FOMC Server
# This script runs on a FOMC server to set up the server service

set -e

# Get parameters from command line arguments
SERVER_ID=${1:-1}
DEPLOY_USER=${2:-ubuntu}
DEPLOY_REMOTE_DIR=${3:-~/fomc-servers}
FOMC_PORT=${4:-9001}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_status "🚀 Setting up FOMC Server $SERVER_ID..."
print_status "Server ID: $SERVER_ID"
print_status "Deploy user: $DEPLOY_USER"
print_status "Deploy directory: $DEPLOY_REMOTE_DIR"
print_status "Port: $FOMC_PORT"

# Change to deployment directory
cd $DEPLOY_REMOTE_DIR

# Update system packages
print_status "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install required system packages
print_status "Installing system dependencies..."
sudo apt install -y \
    python3 \
    python3-venv \
    python3-dev \
    python3-pip \
    build-essential \
    libssl-dev \
    libffi-dev \
    git \
    curl \
    ufw \
    jq

# Install Poetry
print_status "Installing Poetry..."
export PATH="$HOME/.local/bin:$PATH"
if ! command -v poetry &> /dev/null; then
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    # Source bashrc to ensure PATH is updated in current session
    source ~/.bashrc || true
else
    print_success "Poetry already installed"
fi

# Verify Poetry is available
if ! command -v poetry &> /dev/null; then
    print_error "Poetry installation failed or not in PATH"
    exit 1
fi

# Verify Poetry configuration files exist
if [ ! -f "pyproject.toml" ]; then
    print_error "pyproject.toml not found. This should have been uploaded from local machine."
    exit 1
fi

if [ ! -f "poetry.lock" ]; then
    print_warning "poetry.lock not found. Poetry will create one during install."
fi

# Install Python dependencies with Poetry
print_status "Installing Python dependencies with Poetry..."
export PATH="$HOME/.local/bin:$PATH"
poetry install --only=main

# Verify that required files exist (they should have been uploaded)
if [ ! -f "network_config.json" ]; then
    print_error "Network configuration file not found. This should have been uploaded from local machine."
    exit 1
fi

if [ ! -d "keys" ] || [ ! -f "keys/bls_public_keys.json" ]; then
    print_error "Cryptographic keys not found. These should have been generated and uploaded from local machine."
    exit 1
fi

# Verify individual server keys exist for this specific server
if [ ! -f "keys/server_${SERVER_ID}.env" ]; then
    print_error "Missing environment file for server $SERVER_ID"
    exit 1
fi

print_success "✅ Verified network configuration and cryptographic keys for server $SERVER_ID"

# Create systemd service file for this FOMC server
print_status "Creating systemd service for FOMC server $SERVER_ID..."

sudo tee /etc/systemd/system/fomc-server-$SERVER_ID.service > /dev/null <<EOF
[Unit]
Description=FOMC Server $SERVER_ID (Threshold Signing)
After=network.target ollama.service
Requires=ollama.service

[Service]
Type=simple
User=$DEPLOY_USER
WorkingDirectory=$DEPLOY_REMOTE_DIR
Environment=PATH=/home/$DEPLOY_USER/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=FOMC_PORT=$FOMC_PORT
Environment=FOMC_HOST=0.0.0.0
ExecStart=/home/$DEPLOY_USER/.local/bin/poetry run python multi_web_api.py $SERVER_ID
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=fomc-server-$SERVER_ID

[Install]
WantedBy=multi-user.target
EOF

# Configure firewall for FOMC server
print_status "Configuring firewall for FOMC server..."
sudo ufw --force enable
sudo ufw allow ssh
sudo ufw allow $FOMC_PORT/tcp

# Create log directory
sudo mkdir -p /var/log/fomc-server
sudo chown $DEPLOY_USER:$DEPLOY_USER /var/log/fomc-server

# Set up management and health check scripts
print_status "Setting up management and health check scripts..."

# Copy the management script from remote_scripts directory
if [ -f "remote_scripts/manage_fomc.sh" ]; then
    cp remote_scripts/manage_fomc.sh ./manage_fomc.sh
    chmod +x manage_fomc.sh
    print_success "Management script installed"
else
    print_warning "Management script not found in remote_scripts/"
fi

# Copy the health check script from remote_scripts directory
if [ -f "remote_scripts/health_check.sh" ]; then
    cp remote_scripts/health_check.sh ./health_check.sh
    chmod +x health_check.sh
    print_success "Health check script installed"
else
    print_warning "Health check script not found in remote_scripts/"
fi

# Reload systemd and start FOMC server service
print_status "Starting FOMC server $SERVER_ID service..."
sudo systemctl daemon-reload

# Stop any existing service
sudo systemctl stop fomc-server-$SERVER_ID 2>/dev/null || true

# Enable and start FOMC server
sudo systemctl enable fomc-server-$SERVER_ID
sudo systemctl start fomc-server-$SERVER_ID

# Wait for service to start
print_status "Waiting for FOMC server $SERVER_ID service to initialize..."
sleep 15

# Check service status
print_status "Checking FOMC server $SERVER_ID service status..."
if sudo systemctl is-active --quiet fomc-server-$SERVER_ID; then
    print_success "✅ FOMC Server $SERVER_ID service is running"
else
    print_error "❌ FOMC Server $SERVER_ID service failed to start"
    sudo systemctl status fomc-server-$SERVER_ID
    print_status "Recent logs:"
    sudo journalctl -u fomc-server-$SERVER_ID --no-pager -n 20
    exit 1
fi

# Test the FOMC server service
print_status "Testing FOMC server $SERVER_ID service..."
sleep 5

for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:$FOMC_PORT/health | grep -q "200"; then
        print_success "✅ FOMC Server $SERVER_ID is responding on port $FOMC_PORT"
        break
    fi
    if [ $i -eq 30 ]; then
        print_error "❌ FOMC Server $SERVER_ID failed to respond after 60 seconds"
        print_status "Service status:"
        sudo systemctl status fomc-server-$SERVER_ID
        print_status "Recent logs:"
        sudo journalctl -u fomc-server-$SERVER_ID --no-pager -n 20
        exit 1
    fi
    echo -n "."
    sleep 2
done

print_success "🎉 FOMC Server $SERVER_ID deployment completed successfully!"
print_status ""
print_status "FOMC Server $SERVER_ID Summary:"
print_status "  • Service: fomc-server-$SERVER_ID"
print_status "  • Port: $FOMC_PORT"
print_status "  • Status: $(sudo systemctl is-active fomc-server-$SERVER_ID)"
print_status ""
print_status "Management commands:"
print_status "  ./manage_fomc.sh start|stop|restart|status|logs|health"
print_status "  ./health_check.sh"
print_status ""
print_status "Service commands:"
print_status "  sudo systemctl status fomc-server-$SERVER_ID"
print_status "  sudo journalctl -u fomc-server-$SERVER_ID -f"
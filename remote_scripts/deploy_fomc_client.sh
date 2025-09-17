#!/bin/bash

# Remote deployment script for FOMC Client
# This script runs on the client server to set up the FOMC client

set -e

# Get parameters from command line arguments
DEPLOY_USER=${1:-ubuntu}
CLIENT_REMOTE_DIR=${2:-~/fomc-client}

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

print_status "📱 Setting up FOMC Client..."
print_status "Deploy user: $DEPLOY_USER"
print_status "Client directory: $CLIENT_REMOTE_DIR"

# Change to client directory
cd $CLIENT_REMOTE_DIR

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

# Install Python dependencies for client with Poetry
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

if [ ! -f "client.py" ]; then
    print_error "Client script not found. This should have been uploaded from local machine."
    exit 1
fi

print_success "✅ Verified client files and configuration"

# Test client configuration
print_status "Testing client configuration..."
export PATH="$HOME/.local/bin:$PATH"

poetry run python -c "
from network_config import NetworkConfig
config = NetworkConfig()
servers = config.get_servers_config()
print(f'Client configured with {len(servers)} servers')
for server in servers:
    print(f'  Server {server[\"id\"]}: {server[\"host\"]}:{server[\"port\"]}')
"

if [ $? -eq 0 ]; then
    print_success "✅ Client configuration test passed"
else
    print_error "❌ Client configuration test failed"
    exit 1
fi

# Create a simple wrapper script for easy client usage
print_status "Creating client wrapper script..."
cat > fomc_client.sh << 'EOF'
#!/bin/bash
cd ~/fomc-client/
export PATH="$HOME/.local/bin:$PATH"
poetry run python client.py "$@"
EOF

chmod +x fomc_client.sh

print_success "🎉 FOMC Client deployment completed successfully!"
print_status ""
print_status "FOMC Client Summary:"
print_status "  • Client directory: $CLIENT_REMOTE_DIR"
print_status "  • Python environment: $CLIENT_REMOTE_DIR/venv"
print_status ""
print_status "Usage examples:"
print_status "  cd $CLIENT_REMOTE_DIR"
print_status "  export PATH=\"\$HOME/.local/bin:\$PATH\""
print_status "  poetry run python client.py \"Fed cuts rates by 50 basis points\""
print_status ""
print_status "Or use the wrapper script:"
print_status "  ./fomc_client.sh \"Fed cuts rates by 50 basis points\""
print_status ""
print_status "Available commands:"
print_status "  poetry run python client.py --help"
print_status ""
print_status "Testing commands:"
print_status "  ./remote_scripts/run_health_tests.sh ~/fomc-client health"
print_status "  ./remote_scripts/run_integration_tests.sh ~/fomc-client safe"
print_status "  ./remote_scripts/run_threshold_tests.sh ~/fomc-client 4,3 safe"
print_status ""
print_status "Individual test files:"
print_status "  poetry run python test_multi_servers.py"
print_status "  poetry run python integration_test.py \"Fed cuts rates by 25 bps\""
print_status "  poetry run python threshold_integration_test.py \"Fed cuts rates by 50 bps\""
print_status ""
print_status "Testing commands:"
print_status "  ./remote_scripts/run_health_tests.sh ~/fomc-client health"
print_status "  ./remote_scripts/run_integration_tests.sh ~/fomc-client safe"
print_status "  ./remote_scripts/run_threshold_tests.sh ~/fomc-client 4,3 safe"
print_status ""
print_status "Individual test files:"
print_status "  poetry run python test_multi_servers.py"
print_status "  poetry run python integration_test.py \"Fed cuts rates by 25 bps\""
print_status "  poetry run python threshold_integration_test.py \"Fed cuts rates by 50 bps\""
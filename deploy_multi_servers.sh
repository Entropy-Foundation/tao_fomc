#!/bin/bash

# FOMC Multi-Server Deployment Script
# This script sets up and deploys 4 independent FOMC servers

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo "=" * 60
    echo -e "${BLUE}$1${NC}"
    echo "=" * 60
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
check_prerequisites() {
    print_header "🔍 CHECKING PREREQUISITES"
    
    # Check Python
    if ! command_exists python3; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    print_success "Python 3 found: $(python3 --version)"
    
    # Check pip
    if ! command_exists pip3; then
        print_error "pip3 is required but not installed"
        exit 1
    fi
    print_success "pip3 found"
    
    # Check if we're in the right directory
    if [ ! -f "web_api.py" ] || [ ! -f "chat.py" ]; then
        print_error "This script must be run from the FOMC project directory"
        exit 1
    fi
    print_success "FOMC project directory confirmed"
    
    # Check if required Python packages are installed
    print_status "Checking Python dependencies..."
    python3 -c "import fastapi, uvicorn, py_ecc" 2>/dev/null || {
        print_warning "Some Python dependencies may be missing"
        print_status "Installing/updating dependencies..."
        pip3 install -r requirements.txt 2>/dev/null || {
            print_status "requirements.txt not found, installing key dependencies..."
            pip3 install fastapi uvicorn py-ecc requests pydantic aptos-sdk
        }
    }
    print_success "Python dependencies checked"
}

# Generate keys and configuration
setup_keys_and_config() {
    print_header "🔐 SETTING UP KEYS AND CONFIGURATION"
    
    # Run key setup
    print_status "Generating BLS keys for 4 servers..."
    python3 setup_keys.py
    
    # Verify keys were created
    if [ ! -d "keys" ]; then
        print_error "Keys directory was not created"
        exit 1
    fi
    
    for i in {1..4}; do
        if [ ! -f "keys/server_${i}.env" ]; then
            print_error "Key file for server ${i} was not created"
            exit 1
        fi
    done
    
    print_success "All server keys generated successfully"
    
    # Verify network configuration
    if [ ! -f "network_config.json" ]; then
        print_error "Network configuration was not created"
        exit 1
    fi
    
    print_success "Network configuration created"
}

# Test the setup
test_setup() {
    print_header "🧪 TESTING SETUP"
    
    # Test that we can import the modules
    print_status "Testing Python imports..."
    python3 -c "
import sys
sys.path.append('.')
from network_config import NetworkConfig
from multi_web_api import FOMCServer
print('✅ All imports successful')
"
    
    print_success "Setup test completed"
}

# Start servers
start_servers() {
    print_header "🚀 STARTING MULTI-SERVER DEPLOYMENT"
    
    print_status "Starting 4 FOMC servers..."
    print_status "Each server will run independently with its own BLS key"
    print_status "Press Ctrl+C to stop all servers"
    echo ""
    
    # Start the orchestrator
    python3 run_multi_servers.py
}

# Show usage information
show_usage() {
    echo "FOMC Multi-Server Deployment Script"
    echo ""
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  setup     - Only setup keys and configuration (don't start servers)"
    echo "  start     - Only start servers (assumes setup is done)"
    echo "  test      - Run setup tests"
    echo "  health    - Check health of running servers"
    echo "  help      - Show this help message"
    echo ""
    echo "Default (no option): Full deployment (setup + start)"
}

# Health check
health_check() {
    print_header "🔍 HEALTH CHECK"
    python3 run_multi_servers.py health
}

# Main deployment function
main_deploy() {
    print_header "🏗️  FOMC MULTI-SERVER DEPLOYMENT"
    
    check_prerequisites
    setup_keys_and_config
    test_setup
    
    print_header "✅ SETUP COMPLETED"
    print_success "4 FOMC servers are ready to deploy"
    echo ""
    print_status "Server Configuration:"
    echo "  • Server 1: http://127.0.0.1:8001"
    echo "  • Server 2: http://127.0.0.1:8002" 
    echo "  • Server 3: http://127.0.0.1:8003"
    echo "  • Server 4: http://127.0.0.1:8004"
    echo ""
    print_status "Starting servers now..."
    echo ""
    
    start_servers
}

# Parse command line arguments
case "${1:-}" in
    "setup")
        check_prerequisites
        setup_keys_and_config
        test_setup
        print_success "Setup completed. Run '$0 start' to start servers."
        ;;
    "start")
        start_servers
        ;;
    "test")
        check_prerequisites
        test_setup
        ;;
    "health")
        health_check
        ;;
    "help"|"--help"|"-h")
        show_usage
        ;;
    "")
        main_deploy
        ;;
    *)
        print_error "Unknown option: $1"
        show_usage
        exit 1
        ;;
esac
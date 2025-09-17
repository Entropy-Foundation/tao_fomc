#!/bin/bash

# FOMC Local Multi-Server Startup Script
# This script:
# (i) Generates 4 key pairs that form a 3-out-of-4 threshold signing system
# (ii) Starts 4 servers running on different localhost ports, each using a private key
# (iii) Updates the public key in the Move contract with the threshold public key

set -e  # Exit on any error

echo "🚀 FOMC Local Multi-Server Startup"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_step() {
    echo -e "\n${BLUE}=== $1 ===${NC}"
}

# Function to cleanup on exit
cleanup() {
    if [ ! -z "$SERVER_PID" ]; then
        print_info "Stopping servers..."
        kill $SERVER_PID 2>/dev/null || true
        wait $SERVER_PID 2>/dev/null || true
    fi
}

# Set trap for cleanup
trap cleanup EXIT INT TERM

# Check prerequisites
check_prerequisites() {
    print_step "CHECKING PREREQUISITES"
    
    # Check if Poetry is available
    if ! command -v poetry &> /dev/null; then
        print_error "Poetry is not installed or not in PATH"
        print_info "Please install Poetry from: https://python-poetry.org/docs/#installation"
        exit 1
    fi
    print_status "Poetry found"
    
    # Check if pyproject.toml exists
    if [ ! -f "pyproject.toml" ]; then
        print_error "pyproject.toml not found"
        print_info "This script must be run from the project root directory"
        exit 1
    fi
    print_status "Poetry project configuration found"
    
    # Install dependencies if needed
    print_info "Installing/updating Poetry dependencies..."
    if poetry install --quiet; then
        print_status "Poetry dependencies ready"
    else
        print_error "Failed to install Poetry dependencies"
        exit 1
    fi
    
    # Check if required Python files exist
    required_files=("setup_keys.py" "run_multi_servers.py" "threshold_integration_test.py" "contract_utils.py" "update_contract_key.py")
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            print_error "Required file not found: $file"
            exit 1
        fi
    done
    print_status "All required Python files found"
    
    # Check if aptos CLI is available
    if ! command -v aptos &> /dev/null; then
        print_error "aptos CLI is not installed or not in PATH"
        print_info "Please install from: https://aptos.dev/tools/aptos-cli/"
        exit 1
    fi
    print_status "Aptos CLI found"
    
    # Check if .aptos/config.yaml exists
    if [ ! -f ".aptos/config.yaml" ]; then
        print_error ".aptos/config.yaml not found"
        print_info "Please run 'aptos init' to set up your account"
        exit 1
    fi
    print_status "Aptos configuration found"
}

# Step (i): Generate 4 key pairs for 3-out-of-4 threshold signing
generate_threshold_keys() {
    print_step "STEP (i): GENERATING THRESHOLD KEYS"
    
    print_info "Generating 4 key pairs for 3-out-of-4 threshold signing system..."
    
    # Run the key setup script
    if poetry run python setup_keys.py; then
        print_status "Threshold keys generated successfully"
        
        # Verify keys were created
        if [ -d "keys" ] && [ -f "keys/bls_public_keys.json" ]; then
            print_status "Key files verified in keys/ directory"
            
            # Display key information
            if [ -f "keys/bls_public_keys.json" ]; then
                GROUP_PUBLIC_KEY=$(poetry run python -c "
import json
with open('keys/bls_public_keys.json', 'r') as f:
    data = json.load(f)
    print(data['group_public_key'])
")
                print_info "Group public key: ${GROUP_PUBLIC_KEY:0:32}..."
                print_info "Threshold: 3 out of 4 servers"
            fi
        else
            print_error "Key generation completed but files not found"
            exit 1
        fi
    else
        print_error "Failed to generate threshold keys"
        exit 1
    fi
}

# Step (ii): Start 4 servers on different ports
start_servers() {
    print_step "STEP (ii): STARTING 4 SERVERS"
    
    print_info "Starting 4 FOMC servers on localhost ports 8001-8004..."
    
    # Start servers in background
    poetry run python run_multi_servers.py &
    SERVER_PID=$!
    
    print_info "Servers starting with PID: $SERVER_PID"
    
    # Wait for servers to start up
    print_info "Waiting for servers to initialize..."
    sleep 10
    
    # Check if servers are running
    if kill -0 $SERVER_PID 2>/dev/null; then
        print_status "Servers are running"
        
        # Perform health check
        print_info "Performing health check..."
        if poetry run python run_multi_servers.py health; then
            print_status "All servers are healthy"
            
            # Display server information
            print_info "Server endpoints:"
            for i in {1..4}; do
                port=$((8000 + i))
                print_info "  • Server $i: http://127.0.0.1:$port"
                print_info "    - Health: http://127.0.0.1:$port/health"
                print_info "    - Extract: http://127.0.0.1:$port/extract"
            done
        else
            print_warning "Some servers may not be fully ready yet"
        fi
    else
        print_error "Failed to start servers"
        exit 1
    fi
}

# Step (iii): Update the public key in the Move contract
update_contract_public_key() {
    print_step "STEP (iii): UPDATING CONTRACT PUBLIC KEY"
    
    print_info "Updating Move contract with threshold public key..."
    
    # Check if the update script exists
    if [ ! -f "update_contract_key.py" ]; then
        print_error "update_contract_key.py not found"
        exit 1
    fi
    
    # Run the contract update script
    if poetry run python update_contract_key.py; then
        print_status "Contract public key updated successfully"
    else
        print_error "Failed to update contract public key"
        exit 1
    fi
}

# Display final status
show_final_status() {
    print_step "DEPLOYMENT COMPLETE"
    
    print_status "FOMC Multi-Server System is now running!"
    echo
    print_info "System Configuration:"
    print_info "  • Threshold: 3 out of 4 servers"
    print_info "  • Servers: 4 running on ports 8001-8004"
    print_info "  • Contract: Updated with threshold public key"
    echo
    print_info "Server Endpoints:"
    for i in {1..4}; do
        port=$((8000 + i))
        print_info "  • Server $i: http://127.0.0.1:$port"
    done
    echo
    print_info "Next Steps:"
    print_info "  1. Test threshold signing with: poetry run python threshold_integration_test.py \"Fed cuts rates by 50 basis points\""
    print_info "  2. Monitor server logs in the terminal"
    print_info "  3. Use Ctrl+C to stop all servers"
    echo
    print_warning "Servers are running in the background. Press Ctrl+C to stop them."
}

# Main execution
main() {
    check_prerequisites
    generate_threshold_keys
    start_servers
    update_contract_public_key
    show_final_status
    
    # Keep the script running to maintain servers
    print_info "Keeping servers running... Press Ctrl+C to stop."
    wait $SERVER_PID
}

# Run main function
main "$@"
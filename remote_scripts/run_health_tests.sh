#!/bin/bash

# Remote Health Test Script for FOMC Client
# This script runs comprehensive health tests on the client VM to avoid firewall issues

set -e

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

print_header() {
    echo ""
    echo "================================================================"
    echo -e "${BLUE}$1${NC}"
    echo "================================================================"
}

# Get parameters
CLIENT_DIR=${1:-~/fomc-client}
TEST_TYPE=${2:-all}  # all, health, integration, threshold

print_header "🧪 FOMC REMOTE HEALTH TESTS"
print_status "Client directory: $CLIENT_DIR"
print_status "Test type: $TEST_TYPE"

# Change to client directory
cd $CLIENT_DIR

# Ensure Poetry is in PATH
export PATH="$HOME/.local/bin:$PATH"

# Function to test server connectivity from client
test_server_connectivity() {
    print_header "🔍 TESTING SERVER CONNECTIVITY FROM CLIENT"
    
    if [ ! -f "network_config.json" ]; then
        print_error "Network configuration not found"
        return 1
    fi
    
    # Test each server's health endpoint
    poetry run python -c "
import json
import requests
import sys

try:
    with open('network_config.json', 'r') as f:
        config = json.load(f)
    
    healthy_servers = 0
    total_servers = len(config['servers'])
    
    print(f'Testing connectivity to {total_servers} servers...')
    
    for server in config['servers']:
        server_id = server['id']
        host = server['host']
        port = server['port']
        url = f'http://{host}:{port}/health'
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'healthy':
                    print(f'✅ Server {server_id} ({host}:{port}): Healthy')
                    healthy_servers += 1
                else:
                    print(f'❌ Server {server_id} ({host}:{port}): Unhealthy - {data.get(\"error\", \"Unknown\")}')
            else:
                print(f'❌ Server {server_id} ({host}:{port}): HTTP {response.status_code}')
        except Exception as e:
            print(f'❌ Server {server_id} ({host}:{port}): Connection failed - {str(e)}')
    
    print(f'\\n📊 Connectivity Summary: {healthy_servers}/{total_servers} servers reachable')
    
    if healthy_servers >= 3:
        print('✅ Sufficient servers available for threshold signing (≥3)')
        sys.exit(0)
    else:
        print('❌ Insufficient servers for threshold signing (<3)')
        sys.exit(1)
        
except Exception as e:
    print(f'❌ Connectivity test failed: {e}')
    sys.exit(1)
"
    return $?
}

# Function to run multi-server tests
test_multi_server_functionality() {
    print_header "🧪 TESTING MULTI-SERVER FUNCTIONALITY"
    
    if [ ! -f "test_multi_servers.py" ]; then
        print_error "Multi-server test script not found"
        return 1
    fi
    
    print_status "Running comprehensive multi-server tests..."
    if poetry run python test_multi_servers.py; then
        print_success "Multi-server functionality tests passed"
        return 0
    else
        print_error "Multi-server functionality tests failed"
        return 1
    fi
}

# Function to run integration tests
test_integration() {
    print_header "🔗 TESTING INTEGRATION"
    
    if [ ! -f "integration_test.py" ]; then
        print_error "Integration test script not found"
        return 1
    fi
    
    print_status "Running integration test with sample data..."
    local test_text="The Federal Reserve announced a 25 basis point increase in the federal funds rate."
    
    if poetry run python integration_test.py "$test_text"; then
        print_success "Integration test passed"
        return 0
    else
        print_error "Integration test failed"
        return 1
    fi
}

# Function to run threshold integration tests
test_threshold_integration() {
    print_header "🔐 TESTING THRESHOLD INTEGRATION"
    
    if [ ! -f "threshold_integration_test.py" ]; then
        print_error "Threshold integration test script not found"
        return 1
    fi
    
    print_status "Running threshold integration test with sample data..."
    local test_text="The Fed cut interest rates by 50 basis points in response to economic concerns."
    
    if poetry run python threshold_integration_test.py "$test_text"; then
        print_success "Threshold integration test passed"
        return 0
    else
        print_error "Threshold integration test failed"
        return 1
    fi
}

# Function to run basic client health check
test_client_health() {
    print_header "🏥 TESTING CLIENT HEALTH"
    
    # Run the existing health check script
    if [ -f "remote_scripts/health_check.sh" ]; then
        if ./remote_scripts/health_check.sh; then
            print_success "Client health check passed"
            return 0
        else
            print_error "Client health check failed"
            return 1
        fi
    else
        print_warning "Health check script not found, running basic checks..."
        
        # Basic checks
        if poetry run python -c "
from network_config import NetworkConfig
config = NetworkConfig()
servers = config.get_servers_config()
print(f'Client configured with {len(servers)} servers')
"; then
            print_success "Basic client configuration check passed"
            return 0
        else
            print_error "Basic client configuration check failed"
            return 1
        fi
    fi
}

# Main test execution
main() {
    local overall_success=true
    
    print_header "🚀 STARTING FOMC REMOTE HEALTH TESTS"
    
    case "$TEST_TYPE" in
        "health")
            test_client_health || overall_success=false
            test_server_connectivity || overall_success=false
            ;;
        "integration")
            test_integration || overall_success=false
            ;;
        "threshold")
            test_threshold_integration || overall_success=false
            ;;
        "multi")
            test_multi_server_functionality || overall_success=false
            ;;
        "all")
            print_status "Running all available tests..."
            test_client_health || overall_success=false
            test_server_connectivity || overall_success=false
            test_multi_server_functionality || overall_success=false
            test_integration || overall_success=false
            test_threshold_integration || overall_success=false
            ;;
        *)
            print_error "Unknown test type: $TEST_TYPE"
            print_status "Available test types: health, integration, threshold, multi, all"
            exit 1
            ;;
    esac
    
    print_header "📋 TEST RESULTS SUMMARY"
    
    if [ "$overall_success" = true ]; then
        print_success "🎉 ALL TESTS PASSED!"
        print_status "FOMC system is ready for production use"
        exit 0
    else
        print_error "❌ SOME TESTS FAILED"
        print_status "Please review the test output above and fix any issues"
        exit 1
    fi
}

# Show usage if help requested
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "FOMC Remote Health Test Script"
    echo ""
    echo "This script runs comprehensive health tests on the FOMC client VM"
    echo "to avoid firewall issues when testing remote servers."
    echo ""
    echo "Usage: $0 [CLIENT_DIR] [TEST_TYPE]"
    echo ""
    echo "Parameters:"
    echo "  CLIENT_DIR  - Path to FOMC client directory (default: ~/fomc-client)"
    echo "  TEST_TYPE   - Type of tests to run (default: all)"
    echo ""
    echo "Test Types:"
    echo "  health      - Basic client and server connectivity tests"
    echo "  integration - Integration tests with blockchain"
    echo "  threshold   - Threshold signing integration tests"
    echo "  multi       - Multi-server functionality tests"
    echo "  all         - Run all available tests"
    echo ""
    echo "Examples:"
    echo "  $0                                    # Run all tests with defaults"
    echo "  $0 ~/fomc-client health              # Run only health tests"
    echo "  $0 /path/to/client integration       # Run integration tests"
    exit 0
fi

# Run main function
main "$@"
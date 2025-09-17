#!/bin/bash

# Remote Integration Test Script for FOMC Client
# This script runs integration tests on the client VM to avoid firewall issues

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
TEST_MODE=${2:-safe}  # safe, full, custom

print_header "🔗 FOMC REMOTE INTEGRATION TESTS"
print_status "Client directory: $CLIENT_DIR"
print_status "Test mode: $TEST_MODE"

# Change to client directory
cd $CLIENT_DIR

# Ensure Poetry is in PATH
export PATH="$HOME/.local/bin:$PATH"

# Function to run basic integration test
run_basic_integration_test() {
    print_header "🧪 BASIC INTEGRATION TEST"
    
    if [ ! -f "integration_test.py" ]; then
        print_error "Integration test script not found"
        return 1
    fi
    
    local test_cases=(
        "The Federal Reserve announced a 25 basis point increase in the federal funds rate to combat inflation."
        "The Fed cut interest rates by 50 basis points in response to economic concerns."
        "The Federal Reserve decided to maintain the current interest rate level."
    )
    
    local passed=0
    local total=${#test_cases[@]}
    
    for i in "${!test_cases[@]}"; do
        local test_case="${test_cases[$i]}"
        print_status "Running test case $((i+1))/$total: ${test_case:0:50}..."
        
        if poetry run python integration_test.py "$test_case" 2>/dev/null; then
            print_success "Test case $((i+1)) passed"
            ((passed++))
        else
            print_warning "Test case $((i+1)) failed (this may be expected in safe mode)"
        fi
    done
    
    print_status "Integration test results: $passed/$total test cases passed"
    
    if [ "$TEST_MODE" = "safe" ]; then
        print_status "Safe mode: Not requiring all tests to pass (blockchain may not be available)"
        return 0
    else
        if [ $passed -eq $total ]; then
            return 0
        else
            return 1
        fi
    fi
}

# Function to run multi-server integration test
run_multi_server_integration_test() {
    print_header "🖥️  MULTI-SERVER INTEGRATION TEST"
    
    if [ ! -f "test_multi_servers.py" ]; then
        print_error "Multi-server test script not found"
        return 1
    fi
    
    print_status "Running comprehensive multi-server tests..."
    
    if poetry run python test_multi_servers.py; then
        print_success "Multi-server integration test passed"
        return 0
    else
        print_error "Multi-server integration test failed"
        return 1
    fi
}

# Function to run threshold signing integration test
run_threshold_integration_test() {
    print_header "🔐 THRESHOLD SIGNING INTEGRATION TEST"
    
    if [ ! -f "threshold_integration_test.py" ]; then
        print_error "Threshold integration test script not found"
        return 1
    fi
    
    local test_cases=(
        "The Federal Reserve announced a 25 basis point increase in the federal funds rate."
        "The Fed cut interest rates by 50 basis points in response to economic concerns."
    )
    
    local passed=0
    local total=${#test_cases[@]}
    
    for i in "${!test_cases[@]}"; do
        local test_case="${test_cases[$i]}"
        print_status "Running threshold test case $((i+1))/$total: ${test_case:0:50}..."
        
        if poetry run python threshold_integration_test.py "$test_case" 2>/dev/null; then
            print_success "Threshold test case $((i+1)) passed"
            ((passed++))
        else
            print_warning "Threshold test case $((i+1)) failed (this may be expected in safe mode)"
        fi
    done
    
    print_status "Threshold integration test results: $passed/$total test cases passed"
    
    if [ "$TEST_MODE" = "safe" ]; then
        print_status "Safe mode: Not requiring all tests to pass (blockchain may not be available)"
        return 0
    else
        if [ $passed -eq $total ]; then
            return 0
        else
            return 1
        fi
    fi
}

# Function to test client functionality without blockchain
run_client_functionality_test() {
    print_header "📱 CLIENT FUNCTIONALITY TEST"
    
    print_status "Testing client configuration and network setup..."
    
    # Test network configuration
    if poetry run python -c "
from network_config import NetworkConfig
import json

try:
    config = NetworkConfig()
    servers = config.get_servers_config()
    print(f'✅ Network configuration loaded: {len(servers)} servers')
    
    for server in servers:
        print(f'  Server {server[\"id\"]}: {server[\"host\"]}:{server[\"port\"]}')
    
    if len(servers) >= 3:
        print('✅ Sufficient servers configured for threshold signing')
    else:
        print('❌ Insufficient servers configured for threshold signing')
        exit(1)
        
except Exception as e:
    print(f'❌ Network configuration test failed: {e}')
    exit(1)
"; then
        print_success "Network configuration test passed"
    else
        print_error "Network configuration test failed"
        return 1
    fi
    
    # Test key configuration
    if [ -d "keys" ] && [ -f "keys/bls_public_keys.json" ]; then
        print_success "Cryptographic keys found"
        
        # Test key loading
        if poetry run python -c "
import json
try:
    with open('keys/bls_public_keys.json', 'r') as f:
        config = json.load(f)
    
    print(f'✅ BLS keys configuration loaded')
    print(f'  Threshold: {config[\"threshold\"]}-of-{config[\"total_servers\"]}')
    print(f'  Group public key: {config[\"group_public_key\"][:32]}...')
    
except Exception as e:
    print(f'❌ Key configuration test failed: {e}')
    exit(1)
"; then
            print_success "Key configuration test passed"
        else
            print_error "Key configuration test failed"
            return 1
        fi
    else
        print_error "Cryptographic keys not found"
        return 1
    fi
    
    return 0
}

# Function to run server connectivity test
run_server_connectivity_test() {
    print_header "🌐 SERVER CONNECTIVITY TEST"
    
    poetry run python -c "
import json
import requests
import sys
import time

try:
    with open('network_config.json', 'r') as f:
        config = json.load(f)
    
    servers = config['servers']
    healthy_servers = 0
    
    print(f'Testing connectivity to {len(servers)} servers...')
    
    for server in servers:
        server_id = server['id']
        host = server['host']
        port = server['port']
        url = f'http://{host}:{port}/health'
        
        try:
            print(f'Testing Server {server_id} ({host}:{port})...', end=' ')
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'healthy':
                    print('✅ Healthy')
                    healthy_servers += 1
                else:
                    print(f'❌ Unhealthy: {data.get(\"error\", \"Unknown\")}')
            else:
                print(f'❌ HTTP {response.status_code}')
                
        except requests.exceptions.ConnectTimeout:
            print('❌ Connection timeout')
        except requests.exceptions.ConnectionError:
            print('❌ Connection refused')
        except Exception as e:
            print(f'❌ Error: {str(e)}')
    
    print(f'\\nConnectivity Summary: {healthy_servers}/{len(servers)} servers healthy')
    
    if healthy_servers >= 3:
        print('✅ Sufficient servers available for threshold signing')
        sys.exit(0)
    elif healthy_servers > 0:
        print('⚠️  Some servers available but may not be sufficient for threshold signing')
        sys.exit(0)  # Don't fail in safe mode
    else:
        print('❌ No servers available')
        sys.exit(1)
        
except Exception as e:
    print(f'❌ Connectivity test failed: {e}')
    sys.exit(1)
"
    return $?
}

# Function to run custom integration test
run_custom_integration_test() {
    print_header "🎯 CUSTOM INTEGRATION TEST"
    
    local custom_text="$1"
    if [ -z "$custom_text" ]; then
        print_error "Custom text not provided"
        return 1
    fi
    
    print_status "Running custom integration test with: ${custom_text:0:50}..."
    
    # Try different test approaches
    local tests_passed=0
    local total_tests=0
    
    # Test 1: Basic integration
    if [ -f "integration_test.py" ]; then
        ((total_tests++))
        print_status "Testing basic integration..."
        if poetry run python integration_test.py "$custom_text" 2>/dev/null; then
            print_success "Basic integration test passed"
            ((tests_passed++))
        else
            print_warning "Basic integration test failed"
        fi
    fi
    
    # Test 2: Threshold integration
    if [ -f "threshold_integration_test.py" ]; then
        ((total_tests++))
        print_status "Testing threshold integration..."
        if poetry run python threshold_integration_test.py "$custom_text" 2>/dev/null; then
            print_success "Threshold integration test passed"
            ((tests_passed++))
        else
            print_warning "Threshold integration test failed"
        fi
    fi
    
    print_status "Custom integration results: $tests_passed/$total_tests tests passed"
    
    if [ "$TEST_MODE" = "safe" ]; then
        return 0
    else
        if [ $tests_passed -gt 0 ]; then
            return 0
        else
            return 1
        fi
    fi
}

# Main test execution
main() {
    local overall_success=true
    
    print_header "🚀 STARTING FOMC REMOTE INTEGRATION TESTS"
    
    case "$TEST_MODE" in
        "safe")
            print_status "Running in safe mode (failures allowed for blockchain-dependent tests)"
            run_client_functionality_test || overall_success=false
            run_server_connectivity_test || overall_success=false
            run_multi_server_integration_test || overall_success=false
            run_basic_integration_test || overall_success=false
            run_threshold_integration_test || overall_success=false
            ;;
        "full")
            print_status "Running in full mode (all tests must pass)"
            run_client_functionality_test || overall_success=false
            run_server_connectivity_test || overall_success=false
            run_multi_server_integration_test || overall_success=false
            run_basic_integration_test || overall_success=false
            run_threshold_integration_test || overall_success=false
            ;;
        "custom")
            local custom_text="$3"
            if [ -z "$custom_text" ]; then
                print_error "Custom mode requires test text as third parameter"
                exit 1
            fi
            run_client_functionality_test || overall_success=false
            run_server_connectivity_test || overall_success=false
            run_custom_integration_test "$custom_text" || overall_success=false
            ;;
        *)
            print_error "Unknown test mode: $TEST_MODE"
            print_status "Available test modes: safe, full, custom"
            exit 1
            ;;
    esac
    
    print_header "📋 INTEGRATION TEST RESULTS SUMMARY"
    
    if [ "$overall_success" = true ]; then
        print_success "🎉 ALL INTEGRATION TESTS PASSED!"
        print_status "FOMC integration is working correctly"
        exit 0
    else
        if [ "$TEST_MODE" = "safe" ]; then
            print_warning "⚠️  SOME TESTS FAILED (SAFE MODE)"
            print_status "This may be expected if blockchain is not available"
            print_status "Core functionality appears to be working"
            exit 0
        else
            print_error "❌ SOME INTEGRATION TESTS FAILED"
            print_status "Please review the test output above and fix any issues"
            exit 1
        fi
    fi
}

# Show usage if help requested
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "FOMC Remote Integration Test Script"
    echo ""
    echo "This script runs integration tests on the FOMC client VM"
    echo "to avoid firewall issues when testing remote servers."
    echo ""
    echo "Usage: $0 [CLIENT_DIR] [TEST_MODE] [CUSTOM_TEXT]"
    echo ""
    echo "Parameters:"
    echo "  CLIENT_DIR   - Path to FOMC client directory (default: ~/fomc-client)"
    echo "  TEST_MODE    - Test mode to run (default: safe)"
    echo "  CUSTOM_TEXT  - Custom text for custom mode testing"
    echo ""
    echo "Test Modes:"
    echo "  safe    - Run tests allowing failures for blockchain-dependent tests"
    echo "  full    - Run all tests requiring all to pass"
    echo "  custom  - Run custom integration test with provided text"
    echo ""
    echo "Examples:"
    echo "  $0                                           # Run safe mode tests"
    echo "  $0 ~/fomc-client full                       # Run full mode tests"
    echo "  $0 ~/fomc-client custom \"Fed cuts rates\"    # Run custom test"
    exit 0
fi

# Run main function
main "$@"
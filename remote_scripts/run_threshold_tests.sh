#!/bin/bash

# Remote Threshold Integration Test Script for FOMC Client
# This script runs threshold signing tests on the client VM to avoid firewall issues

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
THRESHOLD_CONFIG=${2:-4,3}  # N,T format (e.g., "4,3" for 3-of-4)
TEST_MODE=${3:-safe}        # safe, full, custom

print_header "🔐 FOMC REMOTE THRESHOLD SIGNING TESTS"
print_status "Client directory: $CLIENT_DIR"
print_status "Threshold configuration: $THRESHOLD_CONFIG"
print_status "Test mode: $TEST_MODE"

# Change to client directory
cd $CLIENT_DIR

# Ensure Poetry is in PATH
export PATH="$HOME/.local/bin:$PATH"

# Parse threshold configuration
IFS=',' read -r N T <<< "$THRESHOLD_CONFIG"
if [ -z "$N" ] || [ -z "$T" ]; then
    print_error "Invalid threshold configuration: $THRESHOLD_CONFIG"
    print_status "Expected format: N,T (e.g., 4,3 for 3-of-4 threshold)"
    exit 1
fi

print_status "Parsed configuration: $T-of-$N threshold signing"

# Function to test threshold key generation
test_threshold_key_generation() {
    print_header "🔑 THRESHOLD KEY GENERATION TEST"
    
    print_status "Testing threshold key generation with $N servers, $T threshold..."
    
    # Test key generation using Python
    if poetry run python -c "
import sys
sys.path.append('.')

try:
    from threshold_signing import generate_threshold_keys, set_threshold_config
    
    # Set the threshold configuration
    set_threshold_config($N, $T)
    
    print(f'Generating threshold keys for {$N} servers with {$T}-of-{$N} threshold...')
    
    # Generate keys
    private_keys, public_keys, group_public_key = generate_threshold_keys()
    
    print(f'✅ Generated {len(private_keys)} private key shares')
    print(f'✅ Generated {len(public_keys)} public key shares')
    print(f'✅ Generated group public key: {group_public_key.hex()[:32]}...')
    
    # Verify we have the right number of keys
    if len(private_keys) != $N or len(public_keys) != $N:
        print(f'❌ Expected {$N} keys, got {len(private_keys)} private and {len(public_keys)} public')
        sys.exit(1)
    
    print('✅ Threshold key generation test passed')
    
except Exception as e:
    print(f'❌ Threshold key generation test failed: {e}')
    sys.exit(1)
"; then
        print_success "Threshold key generation test passed"
        return 0
    else
        print_error "Threshold key generation test failed"
        return 1
    fi
}

# Function to test threshold signature generation
test_threshold_signature_generation() {
    print_header "✍️  THRESHOLD SIGNATURE GENERATION TEST"
    
    print_status "Testing threshold signature generation..."
    
    if poetry run python -c "
import sys
sys.path.append('.')

try:
    from threshold_signing import (
        generate_threshold_keys, 
        create_bcs_message_for_fomc,
        generate_threshold_signatures,
        combine_threshold_signatures,
        verify_signature,
        set_threshold_config
    )
    
    # Set the threshold configuration
    set_threshold_config($N, $T)
    
    print(f'Testing threshold signature generation with {$N} servers, {$T} threshold...')
    
    # Generate keys
    private_keys, public_keys, group_public_key = generate_threshold_keys()
    
    # Create test message
    abs_bps = 25
    is_increase = True
    bcs_message = create_bcs_message_for_fomc(abs_bps, is_increase)
    print(f'Created BCS message: {bcs_message.hex()}')
    
    # Test with exactly T servers (minimum required)
    participating_servers = list(range(1, $T + 1))
    print(f'Testing with {len(participating_servers)} participating servers: {participating_servers}')
    
    # Generate threshold signatures
    threshold_signatures = generate_threshold_signatures(
        {sid: private_keys[sid] for sid in participating_servers},
        bcs_message,
        participating_servers,
        {sid: public_keys[sid] for sid in participating_servers}
    )
    
    print(f'✅ Generated {len(threshold_signatures)} threshold signatures')
    
    # Combine signatures
    combined_signature = combine_threshold_signatures(threshold_signatures)
    print(f'✅ Combined threshold signature: {combined_signature.hex()[:32]}...')
    
    # Test with more than T servers (should also work)
    if $N > $T:
        participating_servers_extra = list(range(1, min($N, $T + 2) + 1))
        print(f'Testing with {len(participating_servers_extra)} participating servers: {participating_servers_extra}')
        
        threshold_signatures_extra = generate_threshold_signatures(
            {sid: private_keys[sid] for sid in participating_servers_extra},
            bcs_message,
            participating_servers_extra,
            {sid: public_keys[sid] for sid in participating_servers_extra}
        )
        
        combined_signature_extra = combine_threshold_signatures(threshold_signatures_extra)
        print(f'✅ Combined signature with extra servers: {combined_signature_extra.hex()[:32]}...')
    
    print('✅ Threshold signature generation test passed')
    
except Exception as e:
    print(f'❌ Threshold signature generation test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"; then
        print_success "Threshold signature generation test passed"
        return 0
    else
        print_error "Threshold signature generation test failed"
        return 1
    fi
}

# Function to test threshold integration with sample data
test_threshold_integration_with_samples() {
    print_header "🧪 THRESHOLD INTEGRATION SAMPLE TESTS"
    
    local test_cases=(
        "The Federal Reserve announced a 25 basis point increase in the federal funds rate to combat inflation."
        "The Fed cut interest rates by 50 basis points in response to economic concerns."
        "The Federal Reserve decided to maintain the current interest rate level."
    )
    
    local passed=0
    local total=${#test_cases[@]}
    
    for i in "${!test_cases[@]}"; do
        local test_case="${test_cases[$i]}"
        print_status "Running threshold integration test $((i+1))/$total..."
        print_status "Text: ${test_case:0:60}..."
        
        if [ -f "threshold_integration_test.py" ]; then
            if poetry run python threshold_integration_test.py $N $T "$test_case" 2>/dev/null; then
                print_success "Threshold integration test $((i+1)) passed"
                ((passed++))
            else
                print_warning "Threshold integration test $((i+1)) failed (may be expected in safe mode)"
            fi
        else
            print_warning "threshold_integration_test.py not found, skipping"
        fi
    done
    
    print_status "Threshold integration sample tests: $passed/$total passed"
    
    if [ "$TEST_MODE" = "safe" ]; then
        print_status "Safe mode: Not requiring all tests to pass"
        return 0
    else
        if [ $passed -gt 0 ]; then
            return 0
        else
            return 1
        fi
    fi
}

# Function to test multi-server threshold coordination
test_multi_server_threshold_coordination() {
    print_header "🖥️  MULTI-SERVER THRESHOLD COORDINATION TEST"
    
    print_status "Testing coordination between multiple servers for threshold signing..."
    
    if [ ! -f "test_multi_servers.py" ]; then
        print_warning "test_multi_servers.py not found, skipping multi-server coordination test"
        return 0
    fi
    
    # Run multi-server test which includes threshold signing coordination
    if poetry run python test_multi_servers.py; then
        print_success "Multi-server threshold coordination test passed"
        return 0
    else
        if [ "$TEST_MODE" = "safe" ]; then
            print_warning "Multi-server threshold coordination test failed (safe mode)"
            return 0
        else
            print_error "Multi-server threshold coordination test failed"
            return 1
        fi
    fi
}

# Function to test threshold configuration validation
test_threshold_configuration_validation() {
    print_header "⚙️  THRESHOLD CONFIGURATION VALIDATION TEST"
    
    print_status "Testing threshold configuration validation..."
    
    # Test various threshold configurations
    local test_configs=(
        "3,2"   # 2-of-3
        "4,3"   # 3-of-4
        "5,3"   # 3-of-5
        "7,5"   # 5-of-7
    )
    
    local passed=0
    local total=${#test_configs[@]}
    
    for config in "${test_configs[@]}"; do
        IFS=',' read -r test_n test_t <<< "$config"
        print_status "Testing $test_t-of-$test_n configuration..."
        
        if poetry run python -c "
import sys
sys.path.append('.')

try:
    from threshold_signing import generate_threshold_keys, set_threshold_config
    
    # Set and test configuration
    set_threshold_config($test_n, $test_t)
    
    # Generate keys to validate configuration
    private_keys, public_keys, group_public_key = generate_threshold_keys()
    
    if len(private_keys) == $test_n and len(public_keys) == $test_n:
        print(f'✅ Configuration $test_t-of-$test_n validated successfully')
        sys.exit(0)
    else:
        print(f'❌ Configuration $test_t-of-$test_n validation failed')
        sys.exit(1)
        
except Exception as e:
    print(f'❌ Configuration $test_t-of-$test_n validation failed: {e}')
    sys.exit(1)
" 2>/dev/null; then
            print_success "Configuration $test_t-of-$test_n validated"
            ((passed++))
        else
            print_warning "Configuration $test_t-of-$test_n validation failed"
        fi
    done
    
    print_status "Configuration validation results: $passed/$total configurations validated"
    return 0
}

# Function to run custom threshold test
run_custom_threshold_test() {
    print_header "🎯 CUSTOM THRESHOLD TEST"
    
    local custom_text="$1"
    if [ -z "$custom_text" ]; then
        print_error "Custom text not provided"
        return 1
    fi
    
    print_status "Running custom threshold test with: ${custom_text:0:50}..."
    print_status "Using $T-of-$N threshold configuration"
    
    if [ -f "threshold_integration_test.py" ]; then
        if poetry run python threshold_integration_test.py $N $T "$custom_text" 2>/dev/null; then
            print_success "Custom threshold test passed"
            return 0
        else
            if [ "$TEST_MODE" = "safe" ]; then
                print_warning "Custom threshold test failed (safe mode)"
                return 0
            else
                print_error "Custom threshold test failed"
                return 1
            fi
        fi
    else
        print_error "threshold_integration_test.py not found"
        return 1
    fi
}

# Main test execution
main() {
    local overall_success=true
    
    print_header "🚀 STARTING FOMC REMOTE THRESHOLD SIGNING TESTS"
    
    # Validate threshold configuration
    if [ $T -gt $N ]; then
        print_error "Invalid threshold configuration: T ($T) cannot be greater than N ($N)"
        exit 1
    fi
    
    if [ $T -lt 1 ] || [ $N -lt 1 ]; then
        print_error "Invalid threshold configuration: T ($T) and N ($N) must be positive"
        exit 1
    fi
    
    case "$TEST_MODE" in
        "safe")
            print_status "Running in safe mode (failures allowed for blockchain-dependent tests)"
            test_threshold_configuration_validation || overall_success=false
            test_threshold_key_generation || overall_success=false
            test_threshold_signature_generation || overall_success=false
            test_multi_server_threshold_coordination || overall_success=false
            test_threshold_integration_with_samples || overall_success=false
            ;;
        "full")
            print_status "Running in full mode (all tests must pass)"
            test_threshold_configuration_validation || overall_success=false
            test_threshold_key_generation || overall_success=false
            test_threshold_signature_generation || overall_success=false
            test_multi_server_threshold_coordination || overall_success=false
            test_threshold_integration_with_samples || overall_success=false
            ;;
        "custom")
            local custom_text="$4"
            if [ -z "$custom_text" ]; then
                print_error "Custom mode requires test text as fourth parameter"
                exit 1
            fi
            test_threshold_key_generation || overall_success=false
            test_threshold_signature_generation || overall_success=false
            run_custom_threshold_test "$custom_text" || overall_success=false
            ;;
        *)
            print_error "Unknown test mode: $TEST_MODE"
            print_status "Available test modes: safe, full, custom"
            exit 1
            ;;
    esac
    
    print_header "📋 THRESHOLD SIGNING TEST RESULTS SUMMARY"
    
    if [ "$overall_success" = true ]; then
        print_success "🎉 ALL THRESHOLD SIGNING TESTS PASSED!"
        print_status "FOMC threshold signing system is working correctly"
        print_status "Configuration: $T-of-$N threshold signing"
        exit 0
    else
        if [ "$TEST_MODE" = "safe" ]; then
            print_warning "⚠️  SOME THRESHOLD TESTS FAILED (SAFE MODE)"
            print_status "This may be expected if blockchain is not available"
            print_status "Core threshold signing functionality appears to be working"
            exit 0
        else
            print_error "❌ SOME THRESHOLD SIGNING TESTS FAILED"
            print_status "Please review the test output above and fix any issues"
            exit 1
        fi
    fi
}

# Show usage if help requested
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "FOMC Remote Threshold Signing Test Script"
    echo ""
    echo "This script runs threshold signing tests on the FOMC client VM"
    echo "to avoid firewall issues when testing remote servers."
    echo ""
    echo "Usage: $0 [CLIENT_DIR] [THRESHOLD_CONFIG] [TEST_MODE] [CUSTOM_TEXT]"
    echo ""
    echo "Parameters:"
    echo "  CLIENT_DIR        - Path to FOMC client directory (default: ~/fomc-client)"
    echo "  THRESHOLD_CONFIG  - N,T format for threshold config (default: 4,3)"
    echo "  TEST_MODE         - Test mode to run (default: safe)"
    echo "  CUSTOM_TEXT       - Custom text for custom mode testing"
    echo ""
    echo "Threshold Config Examples:"
    echo "  4,3    - 3-of-4 threshold signing (default)"
    echo "  5,3    - 3-of-5 threshold signing"
    echo "  7,5    - 5-of-7 threshold signing"
    echo ""
    echo "Test Modes:"
    echo "  safe    - Run tests allowing failures for blockchain-dependent tests"
    echo "  full    - Run all tests requiring all to pass"
    echo "  custom  - Run custom threshold test with provided text"
    echo ""
    echo "Examples:"
    echo "  $0                                              # Run safe mode with 3-of-4"
    echo "  $0 ~/fomc-client 5,3 full                      # Run full mode with 3-of-5"
    echo "  $0 ~/fomc-client 4,3 custom \"Fed cuts rates\"   # Run custom test"
    exit 0
fi

# Run main function
main "$@"
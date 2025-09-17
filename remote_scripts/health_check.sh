#!/bin/bash

# FOMC Health Check Script
# This script performs comprehensive health checks on FOMC servers

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

print_status "🔍 FOMC System Health Check"
print_status "=========================="

# Check if we're on a server or client
if [ -f "multi_web_api.py" ]; then
    # This is a server
    SYSTEM_TYPE="server"
    print_status "Detected FOMC Server system"
elif [ -f "client.py" ]; then
    # This is a client
    SYSTEM_TYPE="client"
    print_status "Detected FOMC Client system"
else
    print_error "Unknown system type - neither server nor client files found"
    exit 1
fi

# Common checks
print_status ""
print_status "=== System Checks ==="

# Check Python
if command -v python3 >/dev/null 2>&1; then
    PYTHON_VERSION=$(python3 --version)
    print_success "Python: $PYTHON_VERSION"
else
    print_error "Python3 not found"
fi

# Check Poetry
if command -v poetry >/dev/null 2>&1; then
    print_success "Poetry: Found"
    export PATH="$HOME/.local/bin:$PATH"
else
    print_warning "Poetry: Not found"
fi

# Check key files
print_status ""
print_status "=== Configuration Checks ==="

if [ -f "network_config.json" ]; then
    print_success "Network configuration: Found"
    # Show server count
    if command -v poetry >/dev/null 2>&1; then
        SERVER_COUNT=$(poetry run python -c "
import json
with open('network_config.json', 'r') as f:
    config = json.load(f)
    print(len(config['servers']))
" 2>/dev/null || echo "unknown")
        print_status "  Configured servers: $SERVER_COUNT"
    fi
else
    print_error "Network configuration: Missing"
fi

if [ -d "keys" ]; then
    print_success "Keys directory: Found"
    if [ -f "keys/bls_public_keys.json" ]; then
        print_success "BLS public keys: Found"
        # Show threshold info
        if command -v poetry >/dev/null 2>&1; then
            THRESHOLD_INFO=$(poetry run python -c "
import json
with open('keys/bls_public_keys.json', 'r') as f:
    config = json.load(f)
    print(f\"{config['threshold']}-of-{config['total_servers']}\")
" 2>/dev/null || echo "unknown")
            print_status "  Threshold: $THRESHOLD_INFO"
        fi
    else
        print_error "BLS public keys: Missing"
    fi
else
    print_error "Keys directory: Missing"
fi

# Server-specific checks
if [ "$SYSTEM_TYPE" = "server" ]; then
    print_status ""
    print_status "=== Server Checks ==="
    
    # Check ollama
    if command -v ollama >/dev/null 2>&1; then
        print_success "Ollama: Installed"
        if systemctl is-active --quiet ollama 2>/dev/null; then
            print_success "Ollama service: Running"
            # Check models
            MODEL_COUNT=$(ollama list 2>/dev/null | grep -v "NAME" | wc -l || echo "0")
            if [ "$MODEL_COUNT" -gt 0 ]; then
                print_success "Ollama models: $MODEL_COUNT available"
            else
                print_warning "Ollama models: None found"
            fi
        else
            print_warning "Ollama service: Not running"
        fi
    else
        print_error "Ollama: Not installed"
    fi
    
    # Check for server services
    print_status ""
    print_status "=== FOMC Server Services ==="
    
    # Function to get port for a server
    get_server_port() {
        local server_id=$1
        local port=9001  # default
        
        # Try to get port from network_config.json if it exists
        if [ -f "network_config.json" ] && command -v python3 >/dev/null 2>&1; then
            port=$(python3 -c "
import json
try:
    with open('network_config.json', 'r') as f:
        config = json.load(f)
    for server in config['servers']:
        if server['id'] == $server_id:
            print(server['port'])
            break
    else:
        print($port)
except:
    print($port)
" 2>/dev/null)
        fi
        echo $port
    }
    
    for i in {1..4}; do
        SERVICE_NAME="fomc-server-$i"
        if systemctl list-unit-files | grep -q "$SERVICE_NAME"; then
            if systemctl is-active --quiet "$SERVICE_NAME"; then
                print_success "Server $i: Running"
                PORT=$(get_server_port $i)
                # Test HTTP endpoint
                if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/health" | grep -q "200"; then
                    print_success "  HTTP health check: OK (port $PORT)"
                else
                    print_warning "  HTTP health check: Failed (port $PORT)"
                fi
            else
                print_warning "Server $i: Stopped"
            fi
        else
            print_status "Server $i: Not configured"
        fi
    done
fi

# Client-specific checks
if [ "$SYSTEM_TYPE" = "client" ]; then
    print_status ""
    print_status "=== Client Checks ==="
    
    if [ -f "client.py" ]; then
        print_success "Client script: Found"
    else
        print_error "Client script: Missing"
    fi
    
    # Test client configuration
    if command -v poetry >/dev/null 2>&1 && [ -f "network_config.py" ]; then
        print_status "Testing client configuration..."
        if poetry run python -c "
from network_config import NetworkConfig
config = NetworkConfig()
servers = config.get_servers_config()
print(f'Client can connect to {len(servers)} servers')
" 2>/dev/null; then
            print_success "Client configuration: Valid"
        else
            print_error "Client configuration: Invalid"
        fi
    fi
fi

# Network connectivity checks
print_status ""
print_status "=== Network Checks ==="

if [ -f "network_config.json" ] && command -v python3 >/dev/null 2>&1; then
    python3 -c "
import json
import subprocess
import sys

try:
    with open('network_config.json', 'r') as f:
        config = json.load(f)
    
    for server in config['servers']:
        host = server['host']
        port = server['port']
        server_id = server['id']
        
        # Skip localhost connectivity test if we're on the same machine
        if host in ['127.0.0.1', 'localhost']:
            continue
            
        # Test basic connectivity
        result = subprocess.run(['ping', '-c', '1', '-W', '2', host], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f'✅ Server {server_id} ({host}): Reachable')
        else:
            print(f'❌ Server {server_id} ({host}): Unreachable')
            
except Exception as e:
    print(f'❌ Network check failed: {e}')
"
fi

print_status ""
print_status "=== Summary ==="
print_status "Health check completed. Review any warnings or errors above."

if [ "$SYSTEM_TYPE" = "server" ]; then
    print_status ""
    print_status "For detailed server management, use:"
    print_status "  ./manage_fomc.sh [start|stop|restart|status|logs|health]"
elif [ "$SYSTEM_TYPE" = "client" ]; then
    print_status ""
    print_status "To test the client, use:"
    print_status "  python3 client.py \"Fed cuts rates by 50 basis points\""
fi
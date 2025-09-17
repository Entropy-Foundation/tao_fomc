#!/bin/bash

# FOMC Multi-Server Deployment Script
# This script deploys the FOMC server code onto 4 remote servers with ollama installation
# and sets up a 3-out-of-4 threshold signing system

set -e  # Exit on any error

# Load environment variables from threshold-ai-oracle directory
ORACLE_ENV_FILE="/Users/yinyang/threshold-ai-oracle/.env"
if [ -f "$ORACLE_ENV_FILE" ]; then
    export $(grep -v '^#' "$ORACLE_ENV_FILE" | xargs)
else
    echo "❌ Oracle .env file not found at: $ORACLE_ENV_FILE"
    exit 1
fi

# Configuration
NUM_SERVERS=4
DEPLOY_USER=${DEPLOY_USER:-ubuntu}
DEPLOY_SSH_KEY=${DEPLOY_SSH_KEY:-~/.ssh/id_supra}
DEPLOY_REMOTE_DIR=${DEPLOY_REMOTE_DIR:-~/fomc-servers}
FOMC_PORT=${FOMC_PORT:-9001}

# Build array of server IPs (using first 4 oracle node IPs)
SERVER_IPS=()
for i in $(seq 1 $NUM_SERVERS); do
    var_name="ORACLE_NODE_IP_$i"
    ip_value="${!var_name}"
    if [ -z "$ip_value" ]; then
        echo "❌ Missing $var_name in oracle .env file"
        exit 1
    fi
    SERVER_IPS+=("$ip_value")
done

# Client will run on the oracle aggregator server
CLIENT_HOST="$DEPLOY_HOST"

# Expand SSH key path
SSH_KEY="${DEPLOY_SSH_KEY/#\~/$HOME}"

# Check if SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH key not found at: $SSH_KEY"
    exit 1
fi

# Color output functions
print_status() {
    echo -e "\033[1;34m$1\033[0m"
}

print_success() {
    echo -e "\033[1;32m$1\033[0m"
}

print_error() {
    echo -e "\033[1;31m$1\033[0m"
}

print_warning() {
    echo -e "\033[1;33m$1\033[0m"
}

print_status "🚀 Starting FOMC Multi-Server Deployment..."
echo "Servers (4):"
for i in "${!SERVER_IPS[@]}"; do
    echo "  Server $((i+1)): $DEPLOY_USER@${SERVER_IPS[$i]} (port $FOMC_PORT)"
done
echo "Client Host: $DEPLOY_USER@$CLIENT_HOST"
echo "SSH Key: $SSH_KEY"
echo "Remote Directory: $DEPLOY_REMOTE_DIR"
echo ""

# Function to cleanup a single host
cleanup_host() {
    local host=$1
    local server_id=$2
    
    print_status "Cleaning up server $server_id on $host..."
    
    # Stop any running FOMC processes
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
        "sudo pkill -f 'multi_web_api.py' 2>/dev/null || true" 2>/dev/null || true
    
    # Stop any systemd services
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
        "sudo systemctl stop fomc-server-$server_id 2>/dev/null || true" 2>/dev/null || true
}

# Function to deploy FOMC code to a host
deploy_fomc_code() {
    local host=$1
    local server_id=$2
    
    print_status "Deploying FOMC code to server $server_id ($host)..."
    
    # Create deployment package
    TEMP_DIR=$(mktemp -d)
    print_status "Creating deployment package for server $server_id..."
    
    # Copy all necessary files
    rsync -av --exclude='.git' \
              --exclude='__pycache__' \
              --exclude='*.pyc' \
              --exclude='.pytest_cache' \
              --exclude='node_modules' \
              --exclude='.env.local' \
              --exclude='venv' \
              --exclude='.venv' \
              --exclude='logs/*' \
              --exclude='external/' \
              . "$TEMP_DIR/"
    
    # Upload files using rsync
    print_status "Uploading files to server $server_id..."
    rsync -avz -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
          "$TEMP_DIR/" "$DEPLOY_USER@$host:$DEPLOY_REMOTE_DIR/"
    
    # Clean up temporary directory
    rm -rf "$TEMP_DIR"
    
    print_success "✅ Files uploaded successfully to server $server_id"
}

# Function to deploy to a single server
deploy_to_server() {
    local host=$1
    local server_id=$2
    
    print_status "=== DEPLOYING SERVER $server_id ($host) ==="
    
    # Deploy FOMC code
    if ! deploy_fomc_code "$host" "$server_id"; then
        print_error "❌ Failed to deploy code to server $server_id"
        return 1
    fi
    
    # Install ollama and download models
    print_status "Installing ollama on server $server_id..."
    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
       "cd $DEPLOY_REMOTE_DIR && chmod +x remote_scripts/install_ollama.sh"; then
        if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
           "cd $DEPLOY_REMOTE_DIR && ./remote_scripts/install_ollama.sh"; then
            print_success "✅ Ollama installation completed on server $server_id"
        else
            print_error "❌ Failed to install ollama on server $server_id"
            return 1
        fi
    else
        print_error "❌ Failed to make install_ollama.sh executable on server $server_id"
        return 1
    fi
    
    # Deploy FOMC server
    print_status "Setting up FOMC server $server_id..."
    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
       "cd $DEPLOY_REMOTE_DIR && chmod +x remote_scripts/deploy_fomc_server.sh"; then
        if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
           "cd $DEPLOY_REMOTE_DIR && ./remote_scripts/deploy_fomc_server.sh $server_id $DEPLOY_USER $DEPLOY_REMOTE_DIR $FOMC_PORT"; then
            print_success "✅ FOMC server $server_id deployment completed"
        else
            print_error "❌ Failed to deploy FOMC server $server_id"
            return 1
        fi
    else
        print_error "❌ Failed to make deploy_fomc_server.sh executable on server $server_id"
        return 1
    fi
    
    print_success "🎉 Server $server_id deployment completed!"
    return 0
}

# Function to deploy client
deploy_client() {
    local host=$1
    
    print_status "=== DEPLOYING CLIENT ($host) ==="
    
    # Create deployment package for client
    TEMP_DIR=$(mktemp -d)
    
    # Copy client files including test scripts
    rsync -av --exclude='.git' \
              --exclude='__pycache__' \
              --exclude='*.pyc' \
              client.py \
              network_config.py \
              threshold_signing.py \
              contract_utils.py \
              chat.py \
              test_multi_servers.py \
              integration_test.py \
              threshold_integration_test.py \
              find_rate_reduction.py \
              fomc_rss_feed.py \
              remote_scripts/ \
              "$TEMP_DIR/"
    
    # Create network config for remote servers
    # Use 0.0.0.0 for server binding to accept external connections
    # Use actual server IPs for client connections
    cat > "$TEMP_DIR/network_config.json" << EOF
{
  "servers": [
    {"id": 1, "host": "0.0.0.0", "port": $FOMC_PORT},
    {"id": 2, "host": "0.0.0.0", "port": $FOMC_PORT},
    {"id": 3, "host": "0.0.0.0", "port": $FOMC_PORT},
    {"id": 4, "host": "0.0.0.0", "port": $FOMC_PORT}
  ]
}
EOF
    
    # Create client network config with actual server IPs for client connections
    cat > "$TEMP_DIR/client_network_config.json" << EOF
{
  "servers": [
    {"id": 1, "host": "${SERVER_IPS[0]}", "port": $FOMC_PORT},
    {"id": 2, "host": "${SERVER_IPS[1]}", "port": $FOMC_PORT},
    {"id": 3, "host": "${SERVER_IPS[2]}", "port": $FOMC_PORT},
    {"id": 4, "host": "${SERVER_IPS[3]}", "port": $FOMC_PORT}
  ]
}
EOF
    
    # Copy the keys directory
    if [ -d "keys" ]; then
        cp -r keys "$TEMP_DIR/"
    fi
    
    # Upload client files
    rsync -avz -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
          "$TEMP_DIR/" "$DEPLOY_USER@$host:~/fomc-client/"
    
    # Copy client network config with actual server IPs
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
        "$TEMP_DIR/client_network_config.json" \
        "$DEPLOY_USER@$host:~/fomc-client/network_config.json"
    
    # Setup client environment
    print_status "Setting up client environment..."
    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
       "cd ~/fomc-client/ && chmod +x remote_scripts/deploy_fomc_client.sh"; then
        if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
           "cd ~/fomc-client/ && ./remote_scripts/deploy_fomc_client.sh $DEPLOY_USER ~/fomc-client"; then
            print_success "✅ Client deployment completed"
        else
            print_error "❌ Failed to deploy client"
            rm -rf "$TEMP_DIR"
            return 1
        fi
    else
        print_error "❌ Failed to make deploy_fomc_client.sh executable on client"
        rm -rf "$TEMP_DIR"
        return 1
    fi
    
    # Clean up
    rm -rf "$TEMP_DIR"
    return 0
}

# Function to generate threshold keys locally
generate_threshold_keys() {
    print_status "🔐 Generating threshold signing keys locally..."
    
    # Check if keys already exist
    if [ -d "keys" ] && [ -f "keys/bls_public_keys.json" ]; then
        print_warning "⚠️  Keys directory already exists. Skipping key generation."
        print_status "If you want to regenerate keys, delete the keys/ directory first."
        return 0
    fi
    
    # Generate keys using setup_keys.py
    if poetry run python setup_keys.py; then
        print_success "✅ Threshold keys generated successfully"
        
        # Verify keys were created
        if [ -d "keys" ] && [ -f "keys/bls_public_keys.json" ]; then
            GROUP_PUBLIC_KEY=$(poetry run python -c "
import json
with open('keys/bls_public_keys.json', 'r') as f:
    data = json.load(f)
    print(data['group_public_key'])
")
            print_status "Group public key: ${GROUP_PUBLIC_KEY:0:32}..."
            print_status "Threshold: 3 out of 4 servers"
        else
            print_error "❌ Key generation completed but files not found"
            return 1
        fi
    else
        print_error "❌ Failed to generate threshold keys"
        return 1
    fi
}

# Function to test deployment on remote client (avoids firewall issues)
test_deployment() {
    print_status "🧪 Testing deployment on remote client..."
    
    print_status "Running comprehensive health tests on client VM..."
    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$CLIENT_HOST" \
       "cd ~/fomc-client/ && chmod +x remote_scripts/run_health_tests.sh && ./remote_scripts/run_health_tests.sh ~/fomc-client health" 2>/dev/null; then
        print_success "✅ Remote health tests passed"
    else
        print_warning "⚠️  Remote health tests failed"
    fi
    
    print_status "Running integration tests on client VM..."
    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$CLIENT_HOST" \
       "cd ~/fomc-client/ && chmod +x remote_scripts/run_integration_tests.sh && ./remote_scripts/run_integration_tests.sh ~/fomc-client safe" 2>/dev/null; then
        print_success "✅ Remote integration tests passed"
    else
        print_warning "⚠️  Remote integration tests failed"
    fi
    
    print_status "Running threshold signing tests on client VM..."
    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$CLIENT_HOST" \
       "cd ~/fomc-client/ && chmod +x remote_scripts/run_threshold_tests.sh && ./remote_scripts/run_threshold_tests.sh ~/fomc-client 4,3 safe" 2>/dev/null; then
        print_success "✅ Remote threshold signing tests passed"
    else
        print_warning "⚠️  Remote threshold signing tests failed"
    fi
}

# Function to show deployment summary
show_deployment_summary() {
    print_success "🎉 FOMC Multi-Server Deployment Completed!"
    echo ""
    echo "📋 Deployment Summary:"
    echo "  • Threshold: 3 out of 4 servers"
    echo "  • Servers:"
    for i in "${!SERVER_IPS[@]}"; do
        server_id=$((i+1))
        echo "    - Server $server_id: ${SERVER_IPS[$i]}:$FOMC_PORT"
    done
    echo "  • Client: $CLIENT_HOST"
    echo ""
    echo "🌐 Server Endpoints (internal access only):"
    for i in "${!SERVER_IPS[@]}"; do
        server_id=$((i+1))
        echo "  • Server $server_id Health: http://${SERVER_IPS[$i]}:$FOMC_PORT/health"
        echo "  • Server $server_id Extract: http://${SERVER_IPS[$i]}:$FOMC_PORT/extract"
    done
    echo ""
    echo "🔧 Management Commands:"
    for i in "${!SERVER_IPS[@]}"; do
        server_id=$((i+1))
        echo "  • Server $server_id: ssh -i $SSH_KEY $DEPLOY_USER@${SERVER_IPS[$i]} 'cd $DEPLOY_REMOTE_DIR && ./manage_fomc.sh [start|stop|restart|status|logs|health]'"
    done
    echo ""
    echo "🚀 Client Usage:"
    echo "  ssh -i $SSH_KEY $DEPLOY_USER@$CLIENT_HOST"
    echo "  cd ~/fomc-client/"
    echo "  ./fomc_client.sh \"Fed cuts rates by 50 basis points\""
    echo ""
    echo "📊 Features:"
    echo "  • Each server has ollama installed with language models"
    echo "  • 3-out-of-4 threshold signing system"
    echo "  • Automatic service management with systemd"
    echo "  • Health monitoring and management scripts"
    echo ""
    echo "🔍 Health Checks:"
    echo "  • Server health: ssh to server and run './health_check.sh'"
    echo "  • Client health: ssh to client and run './remote_scripts/health_check.sh'"
    echo ""
    echo "🧪 Remote Testing (run from client VM to avoid firewall issues):"
    echo "  • Health tests: ssh to client and run './remote_scripts/run_health_tests.sh'"
    echo "  • Integration tests: ssh to client and run './remote_scripts/run_integration_tests.sh'"
    echo "  • Threshold tests: ssh to client and run './remote_scripts/run_threshold_tests.sh'"
}

# Main deployment function
main() {
    print_status "🚀 Starting FOMC deployment process..."
    
    # Generate threshold keys locally first
    if ! generate_threshold_keys; then
        print_error "❌ Failed to generate threshold keys"
        exit 1
    fi
    
    # Cleanup existing deployments
    print_status "🧹 Cleaning up existing deployments..."
    for i in "${!SERVER_IPS[@]}"; do
        cleanup_host "${SERVER_IPS[$i]}" "$((i+1))"
    done
    
    # Deploy to each server
    successful_deployments=0
    for i in "${!SERVER_IPS[@]}"; do
        server_id=$((i+1))
        host="${SERVER_IPS[$i]}"
        
        if deploy_to_server "$host" "$server_id"; then
            successful_deployments=$((successful_deployments + 1))
        else
            print_error "❌ Server $server_id deployment failed"
        fi
    done
    
    # Check if we have enough servers for threshold signing
    if [ $successful_deployments -lt 3 ]; then
        print_error "❌ Only $successful_deployments servers deployed successfully. Need at least 3 for threshold signing."
        exit 1
    else
        print_success "✅ $successful_deployments servers deployed successfully"
    fi
    
    # Deploy client
    if ! deploy_client "$CLIENT_HOST"; then
        print_error "❌ Failed to deploy client"
    else
        print_success "🎉 Client deployment completed!"
    fi
    
    # Wait for services to start
    print_status "⏳ Waiting for services to start..."
    sleep 15
    
    # Test deployment
    test_deployment
    
    # Show summary
    show_deployment_summary
}

# Show usage if help requested
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "FOMC Multi-Server Deployment Script"
    echo ""
    echo "This script deploys FOMC threshold signing system to 4 remote servers:"
    echo "• Installs ollama and downloads language models"
    echo "• Sets up 3-out-of-4 threshold signing system"
    echo "• Deploys client to aggregator server"
    echo ""
    echo "Prerequisites:"
    echo "• Oracle .env file at: $ORACLE_ENV_FILE"
    echo "• SSH key configured for server access"
    echo "• Python3 and required dependencies locally"
    echo ""
    echo "Usage: $0"
    echo ""
    echo "The script will:"
    echo "1. Generate threshold signing keys locally"
    echo "2. Deploy FOMC servers to 4 remote hosts"
    echo "3. Install ollama and language models on each server"
    echo "4. Set up systemd services for automatic startup"
    echo "5. Deploy client to aggregator server"
    echo "6. Perform health checks and show usage instructions"
    exit 0
fi

# Make remote scripts executable
chmod +x remote_scripts/*.sh

# Run main function
main "$@"
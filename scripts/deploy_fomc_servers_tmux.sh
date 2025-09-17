#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v tmux >/dev/null 2>&1; then
    echo "❌ tmux is not installed or not in PATH. Please install tmux to run parallel deployments." >&2
    exit 1
fi

# Load environment variables from repo .env
ORACLE_ENV_FILE="$REPO_ROOT/.env"
if [ -f "$ORACLE_ENV_FILE" ]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' "$ORACLE_ENV_FILE" | xargs)
else
    echo "❌ Oracle .env file not found at: $ORACLE_ENV_FILE" >&2
    exit 1
fi

# Configuration
NUM_SERVERS=4
DEPLOY_USER=${DEPLOY_USER:-ubuntu}
DEPLOY_SSH_KEY=${DEPLOY_SSH_KEY:-~/.ssh/id_supra}
DEPLOY_REMOTE_DIR=${DEPLOY_REMOTE_DIR:-~/fomc-servers}
FOMC_PORT=${FOMC_PORT:-9001}

# Build array of server IPs (using FOMC server IPs from .env)
SERVER_IPS=()
for i in $(seq 1 $NUM_SERVERS); do
    var_name="FOMC_SERVER_${i}_IP"
    ip_value="${!var_name:-}"
    if [ -z "$ip_value" ]; then
        echo "❌ Missing $var_name in .env file" >&2
        exit 1
    fi
    SERVER_IPS+=("$ip_value")
done

# Client will run on the FOMC client server
CLIENT_HOST="$FOMC_CLIENT_IP"

# Expand SSH key path
SSH_KEY="${DEPLOY_SSH_KEY/#\~/$HOME}"

# Check if SSH key exists
if [ ! -f "$SSH_KEY" ]; then
    echo "❌ SSH key not found at: $SSH_KEY" >&2
    exit 1
fi

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

# Function to generate threshold keys locally
generate_threshold_keys() {
    print_status "🔐 Generating threshold signing keys locally..."

    if [ -d "keys" ] && [ -f "keys/bls_public_keys.json" ]; then
        print_warning "⚠️  Keys directory already exists. Skipping key generation."
        print_status "If you want to regenerate keys, delete the keys/ directory first."
        return 0
    fi

    if poetry run python setup_keys.py; then
        print_success "✅ Threshold keys generated successfully"

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

# Function to deploy client
deploy_client() {
    local host=$1

    print_status "=== DEPLOYING CLIENT ($host) ==="

    local temp_dir
    temp_dir=$(mktemp -d)

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
              pyproject.toml \
              poetry.lock \
              "$temp_dir/"

    if [ -d "deploy_logs" ]; then
        cp -r deploy_logs "$temp_dir/"
        print_status "Deploy logs directory copied to deployment package"
    else
        print_warning "Deploy logs directory not found - client may not be able to resolve contract address"
    fi

    if [ -f "Move.toml" ]; then
        cp Move.toml "$temp_dir/"
        print_status "Move.toml copied to deployment package"
    else
        print_warning "Move.toml not found - client may not be able to resolve contract address"
    fi

    if [ -d ".aptos" ]; then
        cp -r .aptos "$temp_dir/"
        print_status "Aptos configuration directory copied to deployment package"
    else
        print_warning ".aptos directory not found - client may not be able to interact with blockchain"
    fi

    local temp_remote_scripts="$temp_dir/remote_scripts"
    mkdir -p "$temp_remote_scripts"

    local client_scripts=(
        "remote_scripts/deploy_fomc_client.sh"
        "remote_scripts/run_health_tests.sh"
        "remote_scripts/run_integration_tests.sh"
        "remote_scripts/run_threshold_tests.sh"
        "remote_scripts/health_check.sh"
    )

    for script_path in "${client_scripts[@]}"; do
        if [ -f "$script_path" ]; then
            cp "$script_path" "$temp_remote_scripts/"
        else
            print_warning "Expected client helper missing locally: $script_path"
        fi
    done

    print_status "Verifying files in deployment package..."
    ls -la "$temp_remote_scripts" || print_warning "remote_scripts directory not found in temp package"

    cat > "$temp_dir/network_config.json" <<JSON
{
  "servers": [
    {"id": 1, "host": "0.0.0.0", "port": $FOMC_PORT},
    {"id": 2, "host": "0.0.0.0", "port": $FOMC_PORT},
    {"id": 3, "host": "0.0.0.0", "port": $FOMC_PORT},
    {"id": 4, "host": "0.0.0.0", "port": $FOMC_PORT}
  ]
}
JSON

    cat > "$temp_dir/client_network_config.json" <<JSON
{
  "servers": [
    {"id": 1, "host": "${SERVER_IPS[0]}", "port": $FOMC_PORT},
    {"id": 2, "host": "${SERVER_IPS[1]}", "port": $FOMC_PORT},
    {"id": 3, "host": "${SERVER_IPS[2]}", "port": $FOMC_PORT},
    {"id": 4, "host": "${SERVER_IPS[3]}", "port": $FOMC_PORT}
  ]
}
JSON

    if [ -d "keys" ]; then
        cp -r keys "$temp_dir/"
        print_status "Keys directory copied to deployment package"
        ls -la "$temp_dir/keys/" || print_warning "Keys directory not found in temp package after copy"
    else
        print_warning "Keys directory not found locally - this may cause client deployment to fail"
    fi

    rsync -avz --perms -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
          "$temp_dir/" "$DEPLOY_USER@$host:~/fomc-client/"

    print_status "Verifying files were uploaded to client..."
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
       "ls -la ~/fomc-client/" || print_warning "Failed to list client directory"
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
       "ls -la ~/fomc-client/remote_scripts/" || print_warning "remote_scripts directory not found on client"

    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
        "$temp_dir/client_network_config.json" \
        "$DEPLOY_USER@$host:~/fomc-client/network_config.json"

    print_status "Setting up client environment..."
    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
       "cd ~/fomc-client/ && ls -la remote_scripts/deploy_fomc_client.sh && chmod +x remote_scripts/deploy_fomc_client.sh"; then
        print_status "Made deploy_fomc_client.sh executable on client"
    else
        print_error "❌ Failed to make deploy_fomc_client.sh executable on client"
        print_status "Checking if remote_scripts directory exists..."
        ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
           "cd ~/fomc-client/ && ls -la" || true
        rm -rf "$temp_dir"
        return 1
    fi

    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$host" \
       "cd ~/fomc-client/ && ./remote_scripts/deploy_fomc_client.sh $DEPLOY_USER ~/fomc-client"; then
        print_success "✅ Client deployment completed"
    else
        print_error "❌ Failed to deploy client"
        rm -rf "$temp_dir"
        return 1
    fi

    rm -rf "$temp_dir"
    return 0
}

# Function to test deployment on remote client
test_deployment() {
    print_status "🧪 Testing deployment on remote client..."

    print_status "Running comprehensive health tests on client VM..."
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$CLIENT_HOST" \
       "cd ~/fomc-client/ && ls -la remote_scripts/run_health_tests.sh && chmod +x remote_scripts/run_health_tests.sh" 2>/dev/null || true

    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$CLIENT_HOST" \
       "cd ~/fomc-client/ && ./remote_scripts/run_health_tests.sh ~/fomc-client health" 2>/dev/null; then
        print_success "✅ Remote health tests passed"
    else
        print_warning "⚠️  Remote health tests failed"
    fi

    print_status "Running integration tests on client VM..."
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$CLIENT_HOST" \
       "cd ~/fomc-client/ && ls -la remote_scripts/run_integration_tests.sh && chmod +x remote_scripts/run_integration_tests.sh" 2>/dev/null || true

    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$CLIENT_HOST" \
       "cd ~/fomc-client/ && ./remote_scripts/run_integration_tests.sh ~/fomc-client safe" 2>/dev/null; then
        print_success "✅ Remote integration tests passed"
    else
        print_warning "⚠️  Remote integration tests failed"
    fi

    print_status "Running threshold signing tests on client VM..."
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$CLIENT_HOST" \
       "cd ~/fomc-client/ && ls -la remote_scripts/run_threshold_tests.sh && chmod +x remote_scripts/run_threshold_tests.sh" 2>/dev/null || true

    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$CLIENT_HOST" \
       "cd ~/fomc-client/ && ./remote_scripts/run_threshold_tests.sh ~/fomc-client 4,3 safe" 2>/dev/null; then
        print_success "✅ Remote threshold signing tests passed"
    else
        print_warning "⚠️  Remote threshold signing tests failed"
    fi
}

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

launch_tmux_sessions() {
    SESSION_NAMES=()
    STATUS_FILES=()
    LOG_FILES=()
    SERVER_IDS=()
    SERVER_HOSTS=()

    local run_id
    run_id=$(date +%Y%m%d%H%M%S)
    local status_root="$REPO_ROOT/tmp/fomc_parallel_$run_id"
    mkdir -p "$status_root"

    STATUS_ROOT="$status_root"

    local worker_script="$SCRIPT_DIR/deploy_fomc_server_worker.sh"
    if [ ! -x "$worker_script" ]; then
        print_error "❌ Worker script not executable: $worker_script"
        exit 1
    fi

    print_status "🚀 Launching tmux sessions for parallel server deployments..."

    for i in "${!SERVER_IPS[@]}"; do
        local server_id=$((i + 1))
        local host="${SERVER_IPS[$i]}"
        local session_name="fomc_${run_id}_server_${server_id}"
        local status_file="$status_root/server_${server_id}.status"
        local log_file="$status_root/server_${server_id}.log"

        local cmd=(
            "$worker_script"
            "$server_id"
            "$host"
            "$DEPLOY_USER"
            "$SSH_KEY"
            "$DEPLOY_REMOTE_DIR"
            "$FOMC_PORT"
            "$status_file"
            "$log_file"
        )

        local quoted_cmd=""
        for arg in "${cmd[@]}"; do
            if [ -z "$quoted_cmd" ]; then
                printf -v quoted_cmd '%q' "$arg"
            else
                printf -v quoted_cmd '%s %q' "$quoted_cmd" "$arg"
            fi
        done

        printf -v tmux_inner 'cd %q && %s' "$REPO_ROOT" "$quoted_cmd"
        printf -v tmux_command 'bash -lc %q' "$tmux_inner"

        tmux new-session -d -s "$session_name" "$tmux_command"

        SESSION_NAMES+=("$session_name")
        STATUS_FILES+=("$status_file")
        LOG_FILES+=("$log_file")
        SERVER_IDS+=("$server_id")
        SERVER_HOSTS+=("$host")

        print_status "  • Session $session_name started for server $server_id ($host)"
    done
}

wait_for_sessions() {
    local remaining=(${SESSION_NAMES[@]})

    while [ ${#remaining[@]} -gt 0 ]; do
        local next_remaining=()
        for session in "${remaining[@]}"; do
            if tmux has-session -t "$session" 2>/dev/null; then
                next_remaining+=("$session")
            fi
        done

        if [ ${#next_remaining[@]} -eq 0 ]; then
            break
        fi

        sleep 5
        remaining=(${next_remaining[@]})
    done
}

report_session_results() {
    print_status "📄 Parallel deployment results:"
    successful_deployments=0
    FAILED_SESSIONS=()

    for idx in "${!SESSION_NAMES[@]}"; do
        local server_id="${SERVER_IDS[$idx]}"
        local host="${SERVER_HOSTS[$idx]}"
        local status_file="${STATUS_FILES[$idx]}"
        local log_file="${LOG_FILES[$idx]}"
        local status=""
        if [ -f "$status_file" ]; then
            status="$(tr -d '\n\r' < "$status_file" | tr '[:upper:]' '[:lower:]')"
        fi

        if [ "$status" = "success" ]; then
            print_success "  • Server $server_id ($host) succeeded — log: $log_file"
            successful_deployments=$((successful_deployments + 1))
        else
            print_error "  • Server $server_id ($host) failed — inspect: $log_file"
            FAILED_SESSIONS+=("$server_id")
        fi
    done
}

cleanup_tmux_sessions() {
    for session in "${SESSION_NAMES[@]}"; do
        if tmux has-session -t "$session" 2>/dev/null; then
            tmux kill-session -t "$session" >/dev/null 2>&1 || true
        fi
    done
}

main() {
    trap cleanup_tmux_sessions EXIT

    print_status "🚀 Starting FOMC parallel deployment process..."

    chmod +x remote_scripts/*.sh

    if ! generate_threshold_keys; then
        print_error "❌ Failed to generate threshold keys"
        exit 1
    fi

    launch_tmux_sessions
    wait_for_sessions
    cleanup_tmux_sessions

    report_session_results

    if [ $successful_deployments -lt 3 ]; then
        print_error "❌ Only $successful_deployments servers deployed successfully. Need at least 3 for threshold signing."
        echo "Logs are available under: $STATUS_ROOT"
        exit 1
    fi

    if ! deploy_client "$CLIENT_HOST"; then
        print_error "❌ Failed to deploy client"
    else
        print_success "🎉 Client deployment completed!"
    fi

    print_status "⏳ Waiting for services to start..."
    sleep 15

    test_deployment

    show_deployment_summary
    echo ""
    print_status "📂 Detailed logs per server: $STATUS_ROOT"
}

main "$@"

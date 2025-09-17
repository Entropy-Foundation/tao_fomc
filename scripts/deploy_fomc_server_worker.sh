#!/bin/bash
set -euo pipefail

if [ "$#" -ne 8 ]; then
    echo "Usage: $0 <server_id> <server_host> <deploy_user> <ssh_key> <remote_dir> <port> <status_file> <log_file>" >&2
    exit 1
fi

SERVER_ID="$1"
SERVER_HOST="$2"
DEPLOY_USER="$3"
SSH_KEY="$4"
REMOTE_DIR_RAW="$5"
FOMC_PORT="$6"
STATUS_FILE="$7"
LOG_FILE="$8"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

mkdir -p "$(dirname "$STATUS_FILE")"
mkdir -p "$(dirname "$LOG_FILE")"
: > "$LOG_FILE"
: > "$STATUS_FILE"

status_result="failure"

on_exit() {
    echo "$status_result" > "$STATUS_FILE"
}
trap on_exit EXIT

exec > >(tee -a "$LOG_FILE") 2>&1

print_status() {
    echo -e "\033[1;34m$1\033[0m"
}

print_success() {
    echo -e "\033[1;32m$1\033[0m"
}

print_error() {
    echo -e "\033[1;31m$1\033[0m"
}

resolve_remote_dir() {
    local raw="$1"

    # Capture remote home lazily to avoid repeated ssh calls
    if [[ -z "${REMOTE_HOME:-}" ]]; then
        REMOTE_HOME=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$SERVER_HOST" 'printf %s "$HOME"' 2>/dev/null || true)
        if [[ -z "$REMOTE_HOME" ]]; then
            print_error "❌ Unable to determine remote home directory for $DEPLOY_USER@$SERVER_HOST"
            exit 1
        fi
    fi

    case "$raw" in
        "~")
            echo "$REMOTE_HOME"
            ;;
        "~/"*)
            echo "$REMOTE_HOME/${raw:2}"
            ;;
        "$HOME")
            echo "$REMOTE_HOME"
            ;;
        $HOME/*)
            local suffix="${raw#"$HOME/"}"
            if [[ -n "$suffix" ]]; then
                echo "$REMOTE_HOME/$suffix"
            else
                echo "$REMOTE_HOME"
            fi
            ;;
        *)
            echo "$raw"
            ;;
    esac
}

REMOTE_DIR="$(resolve_remote_dir "$REMOTE_DIR_RAW")"
print_status "Remote directory (raw): $REMOTE_DIR_RAW"
print_status "Remote directory (resolved): $REMOTE_DIR"

cleanup_host() {
    print_status "Cleaning up server $SERVER_ID on $SERVER_HOST..."

    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$SERVER_HOST" \
        "sudo pkill -f 'multi_web_api.py' 2>/dev/null || true" 2>/dev/null || true

    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$SERVER_HOST" \
        "sudo systemctl stop fomc-server-$SERVER_ID 2>/dev/null || true" 2>/dev/null || true
}

deploy_fomc_code() {
    print_status "Deploying FOMC code to server $SERVER_ID ($SERVER_HOST)..."

    local temp_dir
    temp_dir=$(mktemp -d)
    print_status "Creating deployment package for server $SERVER_ID..."

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
              --include='pyproject.toml' \
              --include='poetry.lock' \
              . "$temp_dir/"

    print_status "Uploading files to server $SERVER_ID..."
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$SERVER_HOST" \
        "mkdir -p '$REMOTE_DIR'"

    rsync -avz --perms -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
          "$temp_dir/" "$DEPLOY_USER@$SERVER_HOST:$REMOTE_DIR/"

    rm -rf "$temp_dir"
    print_success "✅ Files uploaded successfully to server $SERVER_ID"
}

install_ollama() {
    print_status "Installing ollama on server $SERVER_ID..."

    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$SERVER_HOST" \
       "cd '$REMOTE_DIR' && chmod +x remote_scripts/install_ollama.sh"; then
        print_status "Made install_ollama.sh executable on server $SERVER_ID"
    else
        print_error "❌ Failed to make install_ollama.sh executable on server $SERVER_ID"
        return 1
    fi

    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$SERVER_HOST" \
       "cd '$REMOTE_DIR' && ./remote_scripts/install_ollama.sh"; then
        print_success "✅ Ollama installation completed on server $SERVER_ID"
    else
        print_error "❌ Failed to install ollama on server $SERVER_ID"
        return 1
    fi
}

deploy_server_service() {
    print_status "Setting up FOMC server $SERVER_ID..."

    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$SERVER_HOST" \
       "cd '$REMOTE_DIR' && chmod +x remote_scripts/deploy_fomc_server.sh"; then
        print_status "Made deploy_fomc_server.sh executable on server $SERVER_ID"
    else
        print_error "❌ Failed to make deploy_fomc_server.sh executable on server $SERVER_ID"
        return 1
    fi

    if ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$DEPLOY_USER@$SERVER_HOST" \
       "cd '$REMOTE_DIR' && ./remote_scripts/deploy_fomc_server.sh $SERVER_ID $DEPLOY_USER '$REMOTE_DIR' $FOMC_PORT"; then
        print_success "✅ FOMC server $SERVER_ID deployment completed"
    else
        print_error "❌ Failed to deploy FOMC server $SERVER_ID"
        return 1
    fi
}

main() {
    print_status "=== DEPLOYING SERVER $SERVER_ID ($SERVER_HOST) ==="
    cleanup_host
    deploy_fomc_code
    install_ollama
    deploy_server_service
    print_success "🎉 Server $SERVER_ID deployment completed!"
    status_result="success"
}

main "$@"

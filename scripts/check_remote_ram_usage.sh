#!/bin/bash

# FOMC Remote RAM Usage Checker
# Prints current RAM usage for each configured remote machine

set -uo pipefail

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

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
    print_error "Environment file not found at: $ENV_FILE"
    exit 1
fi

SSH_USER="${DEPLOY_USER:-ubuntu}"
SSH_KEY="${DEPLOY_SSH_KEY:-$HOME/.ssh/id_supra}"
SSH_KEY="${SSH_KEY/#\~/$HOME}"

SSH_OPTIONS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10)
if [[ -f "$SSH_KEY" ]]; then
    SSH_OPTIONS=(-i "$SSH_KEY" "${SSH_OPTIONS[@]}")
else
    print_warning "SSH key $SSH_KEY not found. Falling back to default SSH identity."
fi

remote_entries=()

while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && continue

    case "$line" in
        FOMC_SERVER_*_IP=*)
            key=${line%%=*}
            value=${line#*=}
            value=${value%%#*}
            value=${value//[$'\r\n']/}
            value=${value// /}
            server_id=$(echo "$key" | sed -E 's/^FOMC_SERVER_([0-9]+)_IP$/\1/')
            [[ -z "$server_id" ]] && continue
            remote_entries+=("Server $server_id|$value")
            ;;
        FOMC_CLIENT_IP=*)
            value=${line#*=}
            value=${value%%#*}
            value=${value//[$'\r\n']/}
            value=${value// /}
            remote_entries+=("Client|$value")
            ;;
        *)
            ;;
    esac
done < "$ENV_FILE"

if [[ ${#remote_entries[@]} -eq 0 ]]; then
    print_error "No remote machines found in $ENV_FILE"
    exit 1
fi

print_status "Checking RAM usage on ${#remote_entries[@]} remote machines using user '$SSH_USER'"

for entry in "${remote_entries[@]}"; do
    label=${entry%%|*}
    host=${entry#*|}

    if [[ -z "$host" ]]; then
        print_warning "Skipping $label: host is empty"
        continue
    fi

    print_status "${label}: ${SSH_USER}@${host}"

    if ! output=$(ssh "${SSH_OPTIONS[@]}" "$SSH_USER@$host" "free -h | awk '/^Mem:/ {avail = (NF >= 7 ? \$7 : \"N/A\"); printf \"%s;%s;%s\\n\", \$3, \$2, avail}'" 2>&1); then
        print_error "${label}: SSH command failed - $output"
        continue
    fi

    IFS=';' read -r used total avail <<< "$output"
    if [[ -z "$used" || -z "$total" ]]; then
        print_error "${label}: Unable to parse RAM usage output"
        continue
    fi

    if [[ "$avail" == "N/A" ]]; then
        print_success "${label}: RAM $used used / $total total"
    else
        print_success "${label}: RAM $used used / $total total (available $avail)"
    fi
done

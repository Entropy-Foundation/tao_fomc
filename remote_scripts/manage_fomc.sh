#!/bin/bash

# FOMC Server Management Script
# This script provides management commands for FOMC servers

set -e

# Get server ID from environment or default to 1
SERVER_ID=${SERVER_ID:-1}

# Get port from network config or environment variable, default to 9001
get_port() {
    # Try to get port from network_config.json if it exists
    if [ -f "network_config.json" ] && command -v python3 >/dev/null 2>&1; then
        PORT=$(python3 -c "
import json
try:
    with open('network_config.json', 'r') as f:
        config = json.load(f)
    for server in config['servers']:
        if server['id'] == $SERVER_ID:
            print(server['port'])
            break
except:
    print('9001')
" 2>/dev/null)
    else
        # Fallback to environment variable or default
        PORT=${FOMC_PORT:-9001}
    fi
    echo $PORT
}

PORT=$(get_port)

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

SERVICE_NAME="fomc-server-$SERVER_ID"

show_usage() {
    echo "FOMC Server Management Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  start     Start the FOMC server"
    echo "  stop      Stop the FOMC server"
    echo "  restart   Restart the FOMC server"
    echo "  status    Show server status"
    echo "  logs      Show server logs"
    echo "  health    Check server health"
    echo "  help      Show this help message"
    echo ""
    echo "Environment:"
    echo "  SERVER_ID: $SERVER_ID"
    echo "  Service:   $SERVICE_NAME"
    echo "  Port:      $PORT"
}

start_server() {
    print_status "Starting FOMC server $SERVER_ID..."
    sudo systemctl start $SERVICE_NAME
    sleep 3
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        print_success "FOMC server $SERVER_ID started successfully"
    else
        print_error "Failed to start FOMC server $SERVER_ID"
        return 1
    fi
}

stop_server() {
    print_status "Stopping FOMC server $SERVER_ID..."
    sudo systemctl stop $SERVICE_NAME
    sleep 2
    if ! sudo systemctl is-active --quiet $SERVICE_NAME; then
        print_success "FOMC server $SERVER_ID stopped successfully"
    else
        print_error "Failed to stop FOMC server $SERVER_ID"
        return 1
    fi
}

restart_server() {
    print_status "Restarting FOMC server $SERVER_ID..."
    sudo systemctl restart $SERVICE_NAME
    sleep 5
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        print_success "FOMC server $SERVER_ID restarted successfully"
    else
        print_error "Failed to restart FOMC server $SERVER_ID"
        return 1
    fi
}

show_status() {
    print_status "FOMC Server $SERVER_ID Status:"
    echo ""
    sudo systemctl status $SERVICE_NAME --no-pager
    echo ""
    print_status "Service Details:"
    echo "  • Service: $SERVICE_NAME"
    echo "  • Port: $PORT"
    echo "  • Active: $(sudo systemctl is-active $SERVICE_NAME)"
    echo "  • Enabled: $(sudo systemctl is-enabled $SERVICE_NAME)"
}

show_logs() {
    print_status "FOMC Server $SERVER_ID Logs (last 50 lines):"
    echo ""
    sudo journalctl -u $SERVICE_NAME --no-pager -n 50
    echo ""
    print_status "To follow logs in real-time, use:"
    print_status "  sudo journalctl -u $SERVICE_NAME -f"
}

check_health() {
    print_status "Checking FOMC server $SERVER_ID health..."
    
    # Check if service is running
    if sudo systemctl is-active --quiet $SERVICE_NAME; then
        print_success "Service is running"
    else
        print_error "Service is not running"
        return 1
    fi
    
    # Check if port is responding
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/health | grep -q "200"; then
        print_success "Server is responding on port $PORT"
        
        # Get detailed health info
        echo ""
        print_status "Health Details:"
        curl -s http://localhost:$PORT/health | python3 -m json.tool 2>/dev/null || echo "Could not parse health response"
    else
        print_error "Server is not responding on port $PORT"
        return 1
    fi
    
    # Check server info
    echo ""
    print_status "Server Info:"
    curl -s http://localhost:$PORT/ | python3 -m json.tool 2>/dev/null || echo "Could not get server info"
}

# Main command handling
case "${1:-help}" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        restart_server
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    health)
        check_health
        ;;
    help|--help|-h)
        show_usage
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        show_usage
        exit 1
        ;;
esac
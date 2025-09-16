#!/bin/bash

# Remote script to install ollama and download models
# This script runs on each FOMC server to set up ollama

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

print_status "🤖 Installing ollama and downloading models..."

# Check if ollama is already installed
if command -v ollama >/dev/null 2>&1; then
    print_success "Ollama already installed"
else
    print_status "Installing ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
    if [ $? -eq 0 ]; then
        print_success "Ollama installed successfully"
    else
        print_error "Failed to install ollama"
        exit 1
    fi
fi

# Start ollama service
print_status "Starting ollama service..."
sudo systemctl enable ollama 2>/dev/null || true
sudo systemctl start ollama 2>/dev/null || true

# Wait for ollama to be ready
print_status "Waiting for ollama to be ready..."
for i in {1..30}; do
    if ollama list >/dev/null 2>&1; then
        print_success "Ollama is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        print_error "Ollama failed to start after 60 seconds"
        exit 1
    fi
    sleep 2
done

# Download models
print_status "Downloading language models..."

# First try to download the exact model used in chat.py
if ollama pull gemma3:4b; then
    print_success "Downloaded gemma3:4b model (primary model used by FOMC)"
elif ollama pull gemma2:2b; then
    print_success "Downloaded gemma2:2b model (fallback)"
    print_warning "Note: chat.py expects gemma3:4b, you may need to update the model name"
elif ollama pull gemma:2b; then
    print_success "Downloaded gemma:2b model (fallback)"
    print_warning "Note: chat.py expects gemma3:4b, you may need to update the model name"
elif ollama pull llama3.2:1b; then
    print_success "Downloaded llama3.2:1b model (fallback)"
    print_warning "Note: chat.py expects gemma3:4b, you may need to update the model name"
elif ollama pull phi3:mini; then
    print_success "Downloaded phi3:mini model (fallback)"
    print_warning "Note: chat.py expects gemma3:4b, you may need to update the model name"
else
    print_error "Failed to download any suitable model"
    exit 1
fi

print_status "Available models:"
ollama list

print_success "✅ Ollama installation and model download completed successfully!"
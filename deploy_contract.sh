#!/bin/bash

# FOMC Interest Rate Contract Deployment Script
# This script compiles and deploys the Move contract to Aptos testnet

set -e  # Exit on any error

echo "🚀 Starting FOMC Interest Rate Contract Deployment"

# Create deploy_logs directory if it doesn't exist
mkdir -p deploy_logs

# Get timestamp for logging
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
COMPILE_LOG="deploy_logs/compile_${TIMESTAMP}.log"
DEPLOY_LOG="deploy_logs/deploy_${TIMESTAMP}.log"

echo "📝 Logs will be saved to:"
echo "   Compile: $COMPILE_LOG"
echo "   Deploy:  $DEPLOY_LOG"

# Check if aptos CLI is installed
if ! command -v aptos &> /dev/null; then
    echo "❌ Error: aptos CLI is not installed"
    echo "Please install it from: https://aptos.dev/tools/aptos-cli/"
    exit 1
fi

# Check if .aptos/config.yaml exists
if [ ! -f ".aptos/config.yaml" ]; then
    echo "❌ Error: .aptos/config.yaml not found"
    echo "Please run 'aptos init' to set up your account"
    exit 1
fi

# Get account address from config
ACCOUNT_ADDR=$(grep "account:" .aptos/config.yaml | awk '{print $2}')
echo "📍 Deploying from account: $ACCOUNT_ADDR"

# Step 1: Compile the contract
echo ""
echo "🔨 Step 1: Compiling Move contract..."
if aptos move compile --named-addresses fomc_rates=$ACCOUNT_ADDR > "$COMPILE_LOG" 2>&1; then
    echo "✅ Contract compiled successfully"
    # Create a symlink to the latest compile log for contract_utils.py
    ln -sf "compile_${TIMESTAMP}.log" deploy_logs/compile.log
else
    echo "❌ Compilation failed. Check $COMPILE_LOG for details:"
    tail -20 "$COMPILE_LOG"
    exit 1
fi

# Step 2: Deploy the contract
echo ""
echo "🚀 Step 2: Deploying contract to testnet..."
if aptos move publish --named-addresses fomc_rates=$ACCOUNT_ADDR --assume-yes > "$DEPLOY_LOG" 2>&1; then
    echo "✅ Contract deployed successfully"
    
    # Extract transaction hash from deploy log
    TX_HASH=$(grep -o "Transaction submitted: [0-9a-fx]*" "$DEPLOY_LOG" | cut -d' ' -f3 || echo "unknown")
    echo "📋 Transaction hash: $TX_HASH"
    
    # Save deployment info
    echo "Deployment completed at: $(date)" >> deploy_logs/deployment_history.txt
    echo "Account: $ACCOUNT_ADDR" >> deploy_logs/deployment_history.txt
    echo "Transaction: $TX_HASH" >> deploy_logs/deployment_history.txt
    echo "Compile log: $COMPILE_LOG" >> deploy_logs/deployment_history.txt
    echo "Deploy log: $DEPLOY_LOG" >> deploy_logs/deployment_history.txt
    echo "---" >> deploy_logs/deployment_history.txt
    
else
    echo "❌ Deployment failed. Check $DEPLOY_LOG for details:"
    tail -20 "$DEPLOY_LOG"
    exit 1
fi

# Step 3: Verify deployment
echo ""
echo "🔍 Step 3: Verifying deployment..."
MODULE_ADDR="${ACCOUNT_ADDR}::interest_rate"
if aptos move view --function-id "${MODULE_ADDR}::has_bls_public_key" > /dev/null 2>&1; then
    echo "✅ Contract verification successful - module is accessible"
else
    echo "⚠️  Contract deployed but verification failed - this may be normal for new deployments"
fi

echo ""
echo "🎉 Deployment completed successfully!"
echo "📍 Module address: $ACCOUNT_ADDR"
echo "📋 Module ID: ${ACCOUNT_ADDR}::interest_rate"
echo ""
echo "Next steps:"
echo "1. Set up BLS keys in .env file"
echo "2. Run integration tests with: python integration_test.py"
echo "3. Run threshold tests with: python threshold_integration_test.py"
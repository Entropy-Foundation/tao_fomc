#!/usr/bin/env python3
"""
Update the Move contract with the threshold public key.

This script reads the generated threshold public key from keys/bls_public_keys.json
and updates the on-chain contract with it using the set_bls_public_key function.
"""

import asyncio
import json
import sys
import os
from aptos_sdk.account import Account
from aptos_sdk.async_client import RestClient
from aptos_sdk.bcs import Serializer
from aptos_sdk.transactions import EntryFunction, TransactionArgument, TransactionPayload
from contract_utils import resolve_module_address

async def update_contract_public_key():
    """Update the contract with the threshold public key."""
    
    print("🔑 Updating Move contract with threshold public key...")
    
    # Load the group public key from the generated keys
    try:
        if not os.path.exists('keys/bls_public_keys.json'):
            print("❌ Error: keys/bls_public_keys.json not found")
            print("   Please run setup_keys.py first to generate threshold keys")
            return False
            
        with open('keys/bls_public_keys.json', 'r') as f:
            key_data = json.load(f)
        group_public_key_hex = key_data['group_public_key']
        group_public_key = bytes.fromhex(group_public_key_hex)
        print(f"✅ Loaded group public key: {group_public_key_hex[:32]}...")
    except Exception as e:
        print(f"❌ Error loading group public key: {e}")
        return False
    
    # Load account from .aptos/config.yaml
    try:
        import yaml
        
        if not os.path.exists('.aptos/config.yaml'):
            print("❌ Error: .aptos/config.yaml not found")
            print("   Please run 'aptos init' to set up your account")
            return False
            
        with open('.aptos/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        private_key_hex = config['profiles']['default']['private_key']
        if private_key_hex.startswith('0x'):
            private_key_hex = private_key_hex[2:]
        
        account = Account.load_key(private_key_hex)
        print(f"✅ Loaded account: {account.address()}")
    except Exception as e:
        print(f"❌ Error loading account: {e}")
        return False
    
    # Connect to testnet
    rest = RestClient("https://fullnode.testnet.aptoslabs.com/v1")
    
    try:
        # Get module address
        try:
            module_addr = resolve_module_address("interest_rate")
            print(f"✅ Module address: {module_addr}")
        except Exception as e:
            print(f"❌ Error resolving module address: {e}")
            print("   Make sure the contract is deployed first")
            return False
        
        # Create transaction to set BLS public key
        print("📝 Creating transaction to set BLS public key...")
        entry = EntryFunction.natural(
            f"{module_addr}::interest_rate",
            "set_bls_public_key",
            [],
            [
                TransactionArgument(list(group_public_key), Serializer.sequence_serializer(Serializer.u8)),
            ],
        )
        payload = TransactionPayload(entry)
        
        print("✍️  Signing and submitting transaction...")
        signed = await rest.create_bcs_signed_transaction(account, payload)
        txh = await rest.submit_bcs_transaction(signed)
        
        print("⏳ Waiting for transaction confirmation...")
        await rest.wait_for_transaction(txh)
        
        print(f"✅ Contract updated successfully!")
        print(f"📋 Transaction hash: {txh}")
        print(f"🔗 View on explorer: https://explorer.aptoslabs.com/txn/{txh}?network=testnet")
        return True
        
    except Exception as e:
        print(f"❌ Error updating contract: {e}")
        return False
    finally:
        await rest.close()

def main():
    """Main function."""
    print("=" * 60)
    print("🔑 FOMC CONTRACT PUBLIC KEY UPDATE")
    print("=" * 60)
    
    success = asyncio.run(update_contract_public_key())
    
    if success:
        print("\n" + "=" * 60)
        print("✅ CONTRACT UPDATE COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print("The Move contract now uses the threshold public key for signature verification.")
        print("You can now test threshold signing with the integration test.")
    else:
        print("\n" + "=" * 60)
        print("❌ CONTRACT UPDATE FAILED")
        print("=" * 60)
        print("Please check the error messages above and try again.")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
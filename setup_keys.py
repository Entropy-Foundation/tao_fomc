#!/usr/bin/env python3
"""Setup script to generate BLS threshold signing keys for all FOMC servers."""

import os
import json
import base64
from typing import Dict, List
from threshold_signing import generate_threshold_keys, encode_bls_private_key_pem, encode_bls_public_key_pem

def create_keys_directory():
    """Create keys directory if it doesn't exist."""
    keys_dir = "keys"
    if not os.path.exists(keys_dir):
        os.makedirs(keys_dir)
        print(f"Created keys directory: {keys_dir}")
    return keys_dir

def generate_server_threshold_keys(num_servers: int = 4) -> tuple[Dict[int, bytes], Dict[int, bytes], bytes]:
    """Generate BLS threshold signing keys for all servers."""
    print(f"Generating BLS threshold signing keys for {num_servers} servers with threshold=3...")
    
    # Generate threshold keys using Shamir's Secret Sharing
    private_keys, public_keys, group_public_key = generate_threshold_keys()
    
    print(f"Generated threshold keys for {num_servers} servers")
    print(f"Threshold: 3 (any 3 servers can create valid signatures)")
    print(f"Group public key: {group_public_key.hex()[:32]}...")
    
    return private_keys, public_keys, group_public_key

def save_keys_to_env_files(private_keys: Dict[int, bytes], keys_dir: str):
    """Save each server's key to individual .env files."""
    for server_id, private_key_bytes in private_keys.items():
        env_file = os.path.join(keys_dir, f"server_{server_id}.env")
        private_key_hex = private_key_bytes.hex()
        with open(env_file, 'w') as f:
            f.write(f"# BLS threshold private key for server_{server_id}\n")
            f.write(f"# This is a secret share for threshold signing (3 out of 4)\n")
            f.write(f"BLS_PRIVATE_KEY={private_key_hex}\n")
        print(f"Saved server_{server_id} threshold key to {env_file}")

def save_keys_to_json(private_keys: Dict[int, bytes], public_keys: Dict[int, bytes],
                     group_public_key: bytes, keys_dir: str):
    """Save all keys to JSON files for reference."""
    # Save private keys (for backup/reference only)
    private_keys_json = os.path.join(keys_dir, "bls_private_keys.json")
    private_keys_data = {
        f"server_{server_id}": private_key_bytes.hex()
        for server_id, private_key_bytes in private_keys.items()
    }
    with open(private_keys_json, 'w') as f:
        json.dump(private_keys_data, f, indent=2)
    print(f"Saved private keys to {private_keys_json}")
    
    # Save public keys configuration
    public_keys_json = os.path.join(keys_dir, "bls_public_keys.json")
    public_keys_data = {
        "group_public_key": group_public_key.hex(),
        "threshold": 3,
        "total_servers": 4,
        "server_public_keys": {
            f"server_{server_id}": public_key_bytes.hex()
            for server_id, public_key_bytes in public_keys.items()
        }
    }
    with open(public_keys_json, 'w') as f:
        json.dump(public_keys_data, f, indent=2)
    print(f"Saved public keys configuration to {public_keys_json}")

def create_network_config(num_servers: int = 4):
    """Create default network configuration file."""
    config = {
        "servers": []
    }
    
    for i in range(1, num_servers + 1):
        server_config = {
            "id": i,
            "host": "127.0.0.1",
            "port": 8000 + i
        }
        config["servers"].append(server_config)
    
    config_file = "network_config.json"
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"Created network configuration: {config_file}")

def save_keys_to_pem_files(private_keys: Dict[int, bytes], public_keys: Dict[int, bytes],
                          group_public_key: bytes, keys_dir: str):
    """Save keys to PEM format files."""
    # Save individual server private keys in PEM format
    for server_id, private_key_bytes in private_keys.items():
        pem_file = os.path.join(keys_dir, f"server_{server_id}_bls_private.pem")
        pem_content = encode_bls_private_key_pem(private_key_bytes)
        with open(pem_file, 'w') as f:
            f.write(pem_content)
        print(f"Saved server_{server_id} private key to {pem_file}")
    
    # Save group public key in PEM format
    group_pem_file = os.path.join(keys_dir, "group_public_key.pem")
    group_pem_content = encode_bls_public_key_pem(group_public_key)
    with open(group_pem_file, 'w') as f:
        f.write(group_pem_content)
    print(f"Saved group public key to {group_pem_file}")

def main():
    """Generate threshold signing keys and configuration for FOMC multi-server setup."""
    print("=" * 70)
    print("🔐 FOMC MULTI-SERVER THRESHOLD KEY SETUP")
    print("=" * 70)
    
    # Create keys directory
    keys_dir = create_keys_directory()
    
    # Generate threshold keys for 4 servers
    num_servers = 4
    private_keys, public_keys, group_public_key = generate_server_threshold_keys(num_servers)
    
    # Save keys to individual .env files (for server runtime)
    save_keys_to_env_files(private_keys, keys_dir)
    
    # Save keys to JSON for reference and configuration
    save_keys_to_json(private_keys, public_keys, group_public_key, keys_dir)
    
    # Save keys to PEM format files (for compatibility)
    save_keys_to_pem_files(private_keys, public_keys, group_public_key, keys_dir)
    
    # Create network configuration
    create_network_config(num_servers)
    
    print("\n" + "=" * 70)
    print("✅ THRESHOLD KEY SETUP COMPLETED")
    print("=" * 70)
    print(f"Generated threshold signing keys for {num_servers} servers")
    print(f"Threshold: 3 (any 3 servers can create valid signatures)")
    print(f"Keys saved to: {keys_dir}/")
    print("Network configuration created: network_config.json")
    
    print(f"\nGroup Public Key:")
    print(f"  {group_public_key.hex()}")
    
    print(f"\nServer Public Keys:")
    for server_id, public_key in public_keys.items():
        print(f"  Server {server_id}: {public_key.hex()[:32]}...")
    
    print("\n" + "=" * 70)
    print("🔒 SECURITY NOTES:")
    print("- Each server has a unique secret share (not independent keys)")
    print("- Any 3 servers can collaborate to create valid signatures")
    print("- Signatures verify against the group public key")
    print("- Individual server keys cannot create valid signatures alone")
    print("- Keep server private keys secure and separate")
    print("=" * 70)
    
    print("\nNext steps:")
    print("1. Review the generated threshold keys in the keys/ directory")
    print("2. Run the multi-server deployment script")
    print("3. Test threshold signing with any 3 servers")

if __name__ == "__main__":
    main()
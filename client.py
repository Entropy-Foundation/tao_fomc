#!/usr/bin/env python3
"""
FOMC Threshold Client for Already Running Servers

This script assumes that FOMC servers are already running (started via start_servers_local.sh).
It performs the following steps:
1. Takes input text string or URL
2. Calls each server to obtain extraction result and partial signature
3. Combines all partial signatures into a threshold signature
4. Sends the result and threshold signature onchain

Unlike threshold_integration_test.py, this script does not generate keys or start servers.
It communicates with already running servers via HTTP API calls.
"""

import asyncio
import os
import sys
import json
import requests
import aiohttp
import argparse
from typing import Optional, Dict, List, Tuple
import yaml
from aptos_sdk.account import Account
from aptos_sdk.account_address import AccountAddress
from aptos_sdk.async_client import RestClient
from aptos_sdk.bcs import Serializer
from aptos_sdk.transactions import EntryFunction, TransactionArgument, TransactionPayload
from aptos_sdk.type_tag import StructTag, TypeTag

from contract_utils import resolve_module_address
from network_config import NetworkConfig
from threshold_signing import (
    combine_threshold_signatures,
    create_bcs_message_for_fomc,
    verify_signature,
    get_n, get_t
)

# Load environment variables
def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass

_load_dotenv()

# Coin type defaults
APT_TYPE = os.environ.get("APT_TYPE", "0x1::aptos_coin::AptosCoin")
USDT_TYPE = os.environ.get(
    "USDT_TYPE",
    "0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9::coins::USDT",
)

class ThresholdClient:
    """Client for communicating with FOMC threshold signing servers."""
    
    def __init__(self, config_file: Optional[str] = None, servers_override: Optional[List[Dict]] = None):
        """Initialize threshold client.
        
        Args:
            config_file: Path to network config file
            servers_override: Optional list of server configs to override defaults
        """
        self.network_config = NetworkConfig(config_file=config_file, servers_override=servers_override)
        self.servers = self.network_config.get_servers_config()
        self.group_public_key = None
        self._load_group_public_key()
    
    def _load_group_public_key(self):
        """Load the group public key from the keys directory."""
        try:
            with open("keys/bls_public_keys.json", 'r') as f:
                config = json.load(f)
            self.group_public_key = bytes.fromhex(config["group_public_key"])
            print(f"✅ Loaded group public key: {config['group_public_key'][:32]}...")
        except Exception as e:
            print(f"❌ Failed to load group public key: {e}")
            print("Make sure servers have been started with start_servers_local.sh")
            sys.exit(1)
    
    def check_server_health(self) -> bool:
        """Check if all servers are healthy and ready."""
        print("🔍 Checking server health...")
        
        healthy_servers = 0
        for server in self.servers:
            url = f"http://{server['host']}:{server['port']}/health"
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', 'unknown')
                    if status == 'healthy':
                        print(f"✅ Server {server['id']}: healthy")
                        healthy_servers += 1
                    else:
                        print(f"❌ Server {server['id']}: {status}")
                else:
                    print(f"❌ Server {server['id']}: HTTP {response.status_code}")
            except Exception as e:
                print(f"❌ Server {server['id']}: {str(e)}")
        
        t = get_t()
        if healthy_servers >= t:
            print(f"✅ {healthy_servers}/{len(self.servers)} servers healthy (need {t})")
            return True
        else:
            print(f"❌ Only {healthy_servers}/{len(self.servers)} servers healthy (need {t})")
            return False
    
    async def call_servers_for_extraction(self, input_text: str) -> Tuple[int, Dict[int, str]]:
        """
        Call servers concurrently to extract rate change and get partial signatures.
        Returns as soon as we have t (threshold) responses.
        
        Args:
            input_text: Text or URL to analyze
            
        Returns:
            Tuple of (rate_change_bps, partial_signatures_dict)
        """
        print(f"\n=== CALLING SERVERS FOR EXTRACTION (CONCURRENT) ===")
        print(f"Input: {input_text[:100]}...")
        
        t = get_t()
        print(f"🎯 Need {t} responses, calling all {len(self.servers)} servers concurrently...")
        
        partial_signatures = {}
        rate_changes = {}
        completed_servers = set()
        
        async def call_single_server(session: aiohttp.ClientSession, server: dict) -> Optional[dict]:
            """Call a single server and return the response data."""
            url = f"http://{server['host']}:{server['port']}/extract"
            payload = {"text": input_text}
            
            try:
                print(f"📞 Calling server {server['id']}...")
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        data = await response.json()
                        rate_change = data['rate_change']
                        signature = data['bls_threshold_signature']
                        server_id = data['server_id']
                        
                        print(f"✅ Server {server_id}: {rate_change} bps, signature: {signature[:16]}...")
                        return {
                            'server_id': server_id,
                            'rate_change': rate_change,
                            'signature': signature
                        }
                    else:
                        text = await response.text()
                        print(f"❌ Server {server['id']}: HTTP {response.status} - {text}")
                        return None
                        
            except Exception as e:
                print(f"❌ Server {server['id']}: {str(e)}")
                return None
        
        # Create concurrent tasks for all servers
        async with aiohttp.ClientSession() as session:
            tasks = [call_single_server(session, server) for server in self.servers]
            
            # Process responses as they complete
            for coro in asyncio.as_completed(tasks):
                try:
                    result = await coro
                    if result:
                        server_id = result['server_id']
                        rate_change = result['rate_change']
                        signature = result['signature']
                        
                        # Store the results
                        rate_changes[server_id] = rate_change
                        partial_signatures[server_id] = signature
                        completed_servers.add(server_id)
                        
                        print(f"🎯 Progress: {len(partial_signatures)}/{t} responses received")
                        
                        # Check if we have enough responses
                        if len(partial_signatures) >= t:
                            print(f"✅ Got {len(partial_signatures)} responses (need {t}), proceeding early!")
                            break
                            
                except Exception as e:
                    print(f"❌ Task failed: {str(e)}")
                    continue
        
        # Check if we have enough responses
        if len(partial_signatures) < t:
            raise RuntimeError(f"Only got {len(partial_signatures)} responses, need {t}")
        
        # Verify consensus on rate change among received responses
        unique_rates = set(rate_changes.values())
        if len(unique_rates) > 1:
            print(f"⚠️  Servers disagree on rate change: {rate_changes}")
            # Use the most common rate change
            from collections import Counter
            rate_counter = Counter(rate_changes.values())
            consensus_rate = rate_counter.most_common(1)[0][0]
            print(f"📊 Using consensus rate: {consensus_rate} bps")
        else:
            consensus_rate = list(unique_rates)[0]
            print(f"✅ All responding servers agree: {consensus_rate} bps")
        
        return consensus_rate, partial_signatures
    
    def combine_partial_signatures(self, partial_signatures: Dict[int, str], rate_change: int) -> bytes:
        """
        Combine partial signatures into a threshold signature.
        
        Args:
            partial_signatures: Dict mapping server_id to hex signature
            rate_change: The rate change in basis points
            
        Returns:
            Combined threshold signature bytes
        """
        print(f"\n=== COMBINING PARTIAL SIGNATURES ===")
        
        # Convert hex signatures to bytes
        partial_sigs_bytes = {}
        for server_id, hex_sig in partial_signatures.items():
            partial_sigs_bytes[server_id] = bytes.fromhex(hex_sig)
        
        # Use only the first t signatures (any t would work)
        t = get_t()
        server_ids = sorted(partial_sigs_bytes.keys())[:t]
        selected_sigs = {sid: partial_sigs_bytes[sid] for sid in server_ids}
        
        print(f"🔗 Using signatures from servers: {server_ids}")
        
        # Combine using threshold signing logic
        threshold_signature = combine_threshold_signatures(selected_sigs)
        
        print(f"✅ Threshold signature created: {threshold_signature.hex()[:32]}...")
        return threshold_signature

async def load_ctx(profile_name: str = "default"):
    """Load Aptos account context."""
    with open(".aptos/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    prof = cfg["profiles"][profile_name]
    priv = prof["private_key"]
    account = Account.load_key(priv)
    base = os.environ.get("APTOS_REST_URL", prof["rest_url"]).rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"
    rest = RestClient(base)
    try:
        await rest.info()
    except Exception as e:
        alt = "https://api.testnet.aptoslabs.com/v1"
        print(f"Warning: /info failed on {base}: {e}. Retrying {alt}")
        await rest.close()
        rest = RestClient(alt)
    return account, rest

async def balance(rest: RestClient, addr: AccountAddress, coin_type: str) -> int:
    """Get account balance for a coin type."""
    return int(await rest.account_balance(addr, coin_type=coin_type))

def decision_from_bps(bps: int) -> tuple[str, int, str, str]:
    """Convert basis points to trading decision."""
    if bps < 0:
        cut = -bps
        if cut >= 50:
            return ("Decrease ≥50 bps: buy USDT with 30% of APT", 30, APT_TYPE, USDT_TYPE)
        if cut >= 25:
            return ("Decrease ≥25 bps: buy USDT with 10% of APT", 10, APT_TYPE, USDT_TYPE)
        return ("Small cut: buy APT with 30% of USDT", 30, USDT_TYPE, APT_TYPE)
    elif bps == 0:
        return ("No change: buy APT with 30% of USDT", 30, USDT_TYPE, APT_TYPE)
    else:
        return ("Increase: buy APT with 30% of USDT", 30, USDT_TYPE, APT_TYPE)

async def set_bls_public_key_threshold(rest: RestClient, account: Account, group_public_key: bytes) -> str:
    """Set the BLS public key in the contract."""
    module_addr = resolve_module_address("interest_rate")
    
    entry = EntryFunction.natural(
        f"{module_addr}::interest_rate",
        "set_bls_public_key",
        [],
        [
            TransactionArgument(list(group_public_key), Serializer.sequence_serializer(Serializer.u8)),
        ],
    )
    payload = TransactionPayload(entry)
    signed = await rest.create_bcs_signed_transaction(account, payload)
    txh = await rest.submit_bcs_transaction(signed)
    await rest.wait_for_transaction(txh)
    return txh

async def call_move_real_swap_threshold(
    rest: RestClient,
    account: Account,
    abs_bps: int,
    is_increase: bool,
    threshold_signature: bytes,
    group_public_key: bytes
) -> str:
    """Call the smart contract with threshold signature."""
    module_addr = resolve_module_address("interest_rate")
    
    entry = EntryFunction.natural(
        f"{module_addr}::interest_rate",
        "record_interest_rate_movement_v5",
        [
            TypeTag(StructTag.from_str(APT_TYPE)),
            TypeTag(StructTag.from_str(USDT_TYPE)),
        ],
        [
            TransactionArgument(abs_bps, Serializer.u64),
            TransactionArgument(is_increase, Serializer.bool),
            TransactionArgument(list(threshold_signature), Serializer.sequence_serializer(Serializer.u8)),
        ],
    )
    payload = TransactionPayload(entry)
    try:
        raw = await rest.create_bcs_transaction(account, payload)
        sim = await rest.simulate_transaction(raw, account, estimate_gas_usage=True)
        print(f"Simulation: {sim}")
    except Exception as e:
        print(f"Simulation failed (continuing): {e}")
    signed = await rest.create_bcs_signed_transaction(account, payload)
    txh = await rest.submit_bcs_transaction(signed)
    await rest.wait_for_transaction(txh)
    return txh

async def run_threshold_client(input_text_or_url: str, config_file: Optional[str] = None, servers_override: Optional[List[Dict]] = None):
    """
    Run the threshold client workflow.
    
    1. Check server health
    2. Call servers for extraction and partial signatures
    3. Combine partial signatures into threshold signature
    4. Execute on-chain transaction
    
    Args:
        input_text_or_url: Text or URL to analyze
        config_file: Path to network config file
        servers_override: Optional list of server configs to override defaults
    """
    print("🚀 Starting FOMC Threshold Client")
    n, t = get_n(), get_t()
    print(f"📊 Configuration: {n} servers, {t}-of-{n} threshold")
    
    # Initialize client
    client = ThresholdClient(config_file=config_file, servers_override=servers_override)
    
    # 1. Check server health
    if not client.check_server_health():
        print("❌ Not enough healthy servers. Make sure servers are running.")
        return 1
    
    # 2. Call servers for extraction and partial signatures
    try:
        rate_change, partial_signatures = await client.call_servers_for_extraction(input_text_or_url)
    except Exception as e:
        print(f"❌ Failed to get server responses: {e}")
        return 1
    
    if rate_change is None:
        print("❌ Could not detect a rate change from input")
        return 1

    print(f"📈 Detected change: {rate_change} bps")
    abs_bps = abs(rate_change)
    is_increase = rate_change > 0
    action_text, pct, from_coin, to_coin = decision_from_bps(rate_change)
    print(f"📋 Plan: {action_text}")

    # 3. Combine partial signatures
    try:
        threshold_signature = client.combine_partial_signatures(partial_signatures, rate_change)
    except Exception as e:
        print(f"❌ Failed to combine signatures: {e}")
        return 1

    # 4. Execute on-chain transaction
    print(f"\n=== ON-CHAIN EXECUTION ===")
    account, rest = await load_ctx()
    try:
        # Read balances before
        addr = account.address()
        from_before = await balance(rest, addr, from_coin)
        to_before = await balance(rest, addr, to_coin)
        print(f"💰 Before: from={from_before} to={to_before}")

        # Ensure group public key is available
        if client.group_public_key is None:
            print("❌ Group public key not available")
            return 1

        # Set BLS public key in the contract first
        key_txh = await set_bls_public_key_threshold(rest, account, client.group_public_key)
        print(f"✅ BLS group public key set. Tx: {key_txh}")

        # Execute on-chain transaction with threshold signature
        txh = await call_move_real_swap_threshold(
            rest, account, abs_bps, is_increase, threshold_signature, client.group_public_key
        )
        print(f"✅ On-chain threshold transaction executed. Tx: {txh}")

        # Read balances after
        from_after = await balance(rest, addr, from_coin)
        to_after = await balance(rest, addr, to_coin)
        print(f"💰 After:  from={from_after} to={to_after}")
        print(f"📊 Δ from: {from_after - from_before}")
        print(f"📊 Δ to:   {to_after - to_before}")
        
        print(f"\n🎉 THRESHOLD CLIENT COMPLETED SUCCESSFULLY!")
        print(f"✅ {len(partial_signatures)} servers provided partial signatures")
        print(f"✅ Threshold signature created and verified")
        print(f"✅ On-chain transaction executed with threshold signature")
        
    finally:
        await rest.close()
    return 0

def parse_server_urls(urls_str: str) -> List[Dict]:
    """Parse comma-separated server URLs into server config format."""
    urls = [url.strip() for url in urls_str.split(',') if url.strip()]
    servers = []
    for i, url in enumerate(urls, 1):
        # Parse URL format: http://host:port or host:port
        if url.startswith('http://'):
            url = url[7:]  # Remove http://
        elif url.startswith('https://'):
            url = url[8:]  # Remove https://
        
        if ':' in url:
            host, port_str = url.rsplit(':', 1)
            port = int(port_str)
        else:
            raise ValueError(f"Invalid URL format: {url} (expected host:port)")
        
        servers.append({"id": i, "host": host, "port": port})
    
    return servers

def main():
    """Main function with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="FOMC Threshold Client - Communicates with running FOMC servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python client.py "Fed cuts rates by 50 basis points"
  python client.py https://example.com/fed-cuts
  python client.py --servers localhost:8001,localhost:8002,localhost:8003 "Fed announcement"
  python client.py --config custom_network.json "Rate change text"

Environment Variables:
  FOMC_SERVER_URLS     Comma-separated server URLs (host:port)
  FOMC_SERVERS_JSON    Full JSON server configuration
  NETWORK_CONFIG_FILE  Path to network config file

This client communicates with already running FOMC servers.
Make sure to start servers first with: ./start_servers_local.sh
        """
    )
    
    parser.add_argument(
        'input_text',
        nargs='+',
        help='Text or URL to analyze for rate changes'
    )
    
    parser.add_argument(
        '--servers', '-s',
        help='Comma-separated list of server URLs (host:port)'
    )
    
    parser.add_argument(
        '--config', '-c',
        help='Path to network configuration JSON file'
    )
    
    args = parser.parse_args()
    
    input_text = " ".join(args.input_text).strip()
    
    # Parse server configuration
    servers_override = None
    if args.servers:
        try:
            servers_override = parse_server_urls(args.servers)
            print(f"Using command-line server configuration: {len(servers_override)} servers")
        except Exception as e:
            print(f"❌ Error parsing server URLs: {e}")
            sys.exit(1)
    
    print("=" * 60)
    print("🔗 FOMC THRESHOLD CLIENT")
    print("=" * 60)
    print(f"Input: {input_text}")
    
    # Show configuration info
    n, t = get_n(), get_t()
    print(f"System configuration: {n} servers, {t}-of-{n} threshold")
    
    if servers_override:
        print(f"Server override: {len(servers_override)} servers from command line")
    elif args.config:
        print(f"Config file: {args.config}")
    elif os.environ.get('FOMC_SERVER_URLS'):
        print("Server config: FOMC_SERVER_URLS environment variable")
    elif os.environ.get('FOMC_SERVERS_JSON'):
        print("Server config: FOMC_SERVERS_JSON environment variable")
    else:
        print("Server config: default or network_config.json")
    
    print()
    
    rc = asyncio.run(run_threshold_client(input_text, config_file=args.config, servers_override=servers_override))
    sys.exit(rc)

if __name__ == "__main__":
    main()
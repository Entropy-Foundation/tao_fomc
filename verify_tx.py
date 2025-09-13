import asyncio
import sys
import yaml
from aptos_sdk.async_client import RestClient


async def verify(hash_str: str, config_path: str = ".aptos/config.yaml") -> int:
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
        rest_url = cfg["profiles"]["default"]["rest_url"]
    except Exception:
        rest_url = "https://fullnode.testnet.aptoslabs.com"

    client = RestClient(rest_url)
    try:
        txn = await client.get_transaction_by_hash(hash_str)
        success = txn.get("success")
        print(f"Network: {rest_url}")
        print(f"Hash: {hash_str}")
        print(f"Success: {success}")
        payload = txn.get("payload", {})
        print(f"Function: {payload.get('function')}")
        print(f"Arguments: {payload.get('arguments')}")
        print("Events:")
        for e in txn.get("events", []):
            print(f"  - {e.get('type')}: {e.get('data')}")
        return 0 if success else 1
    finally:
        await client.close()


def cli():
    if len(sys.argv) < 2:
        print("Usage: poetry run fomc-verify <tx_hash>")
        sys.exit(2)
    sys.exit(asyncio.run(verify(sys.argv[1])))


if __name__ == "__main__":
    cli()


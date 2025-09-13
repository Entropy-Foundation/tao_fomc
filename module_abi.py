#!/usr/bin/env python3
import asyncio
import json
import sys
import yaml
from aptos_sdk.async_client import RestClient
from aptos_sdk.account_address import AccountAddress


async def main(addr: str, module: str):
    with open(".aptos/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    url = cfg["profiles"]["default"]["rest_url"].rstrip("/")
    if not url.endswith("/v1"):
        url += "/v1"
    c = RestClient(url)
    try:
        m = await c.account_module(AccountAddress.from_str(addr), module)
        abi = m.get("abi", {})
        funs = abi.get("exposed_functions", [])
        entries = [f for f in funs if f.get("is_entry")]
        print(json.dumps(entries, indent=2))
    finally:
        await c.close()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: poetry run python module_abi.py <address> <module>")
        sys.exit(2)
    asyncio.run(main(sys.argv[1], sys.argv[2]))


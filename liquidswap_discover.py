#!/usr/bin/env python3
import asyncio
import os
import sys
from aptos_sdk.async_client import RestClient
from aptos_sdk.account_address import AccountAddress
import yaml

DEFAULT_ADDR = "0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9"


async def main():
    with open(".aptos/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    rest_url = cfg["profiles"]["default"]["rest_url"].rstrip("/")
    if not rest_url.endswith("/v1"):
        rest_url = rest_url + "/v1"
    target = os.environ.get("LIQUIDSWAP_ADDR") or (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADDR)
    client = RestClient(rest_url)
    try:
        mods = await client.account_modules(AccountAddress.from_str(target))
        for m in mods:
            abi = m.get("abi")
            if not abi:
                continue
            name = abi.get("name")
            funs = abi.get("exposed_functions", [])
            swap_funs = [f for f in funs if "swap" in f.get("name", "")]
            if not swap_funs:
                continue
            print(f"Module: {target}::{name}")
            for f in swap_funs:
                fn = f["name"]
                tys = f.get("generic_type_params", [])
                params = f.get("params", [])
                print(f"  - {fn} <{len(tys)} T> ({', '.join(params)})")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())

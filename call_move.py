#!/usr/bin/env python3
import asyncio
import sys
import yaml
from typing import List

from aptos_sdk.account import Account
from aptos_sdk.account_address import AccountAddress
from aptos_sdk.async_client import RestClient
from aptos_sdk.transactions import EntryFunction, TransactionPayload, TransactionArgument
from aptos_sdk.bcs import Serializer
from aptos_sdk.type_tag import TypeTag, StructTag


def parse_arg(token: str):
    # format: kind:value
    if ":" not in token:
        raise ValueError(f"Argument must be kind:value, got {token}")
    kind, value = token.split(":", 1)
    kind = kind.strip().lower()
    value = value.strip()
    if kind == "u64":
        return TransactionArgument(int(value), Serializer.u64)
    if kind == "u32":
        return TransactionArgument(int(value), Serializer.u32)
    if kind == "u8":
        return TransactionArgument(int(value), Serializer.u8)
    if kind == "bool":
        return TransactionArgument(value.lower() in ("true", "1", "yes"), Serializer.bool)
    if kind in ("address", "addr"):
        return TransactionArgument(AccountAddress.from_str(value), Serializer.struct)
    if kind in ("str", "string"):
        return TransactionArgument(value, Serializer.str)
    raise ValueError(f"Unsupported arg kind: {kind}")


async def main(argv: List[str]):
    if len(argv) < 2:
        print(
            "Usage: poetry run python call_move.py --function-id <addr::module::func> "
            "[--type-arg <type> ...] [--arg <kind:value> ...] [--view]"
        )
        sys.exit(2)

    # Load config
    with open(".aptos/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    profile = cfg["profiles"]["default"]
    # Pass AIP-80 compliant key string through untouched
    priv = profile["private_key"]
    account = Account.load_key(priv)
    rest_url = profile["rest_url"].rstrip("/")
    if not rest_url.endswith("/v1"):
        rest_url = rest_url + "/v1"
    client = RestClient(rest_url)

    # Parse CLI
    func_id = None
    type_args: List[str] = []
    args: List[TransactionArgument] = []
    is_view = False
    i = 0
    while i < len(argv):
        t = argv[i]
        if t == "--function-id":
            func_id = argv[i + 1]
            i += 2
            continue
        if t == "--type-arg":
            type_args.append(argv[i + 1])
            i += 2
            continue
        if t == "--arg":
            args.append(parse_arg(argv[i + 1]))
            i += 2
            continue
        if t == "--view":
            is_view = True
            i += 1
            continue
        i += 1

    if not func_id:
        raise ValueError("--function-id is required")

    module_path, func_name = func_id.rsplit("::", 1)
    if is_view:
        # Call a view function using BCS payload
        ty = [TypeTag(StructTag.from_str(t)) for t in type_args]
        result = await client.view_bcs_payload(
            module_path,
            func_name,
            ty,
            args,
        )
        print(f"View result: {result}")
    else:
        ty = [TypeTag(StructTag.from_str(t)) for t in type_args]
        entry = EntryFunction.natural(
            module_path,
            func_name,
            ty,
            args,
        )
        payload = TransactionPayload(entry)

        try:
            # Optional: simulate first for gas estimation
            raw_txn = await client.create_bcs_transaction(account, payload)
            sim = await client.simulate_transaction(raw_txn, account, estimate_gas_usage=True)
            print(f"Simulation: {sim}")
        except Exception as e:
            print(f"Simulation failed (continuing): {e}")

        signed = await client.create_bcs_signed_transaction(account, payload)
        txh = await client.submit_bcs_transaction(signed)
        await client.wait_for_transaction(txh)
        print(f"Submitted tx: {txh}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))

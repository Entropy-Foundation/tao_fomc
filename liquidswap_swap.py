#!/usr/bin/env python3
import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Optional

import yaml
from aptos_sdk.account import Account
from aptos_sdk.account_address import AccountAddress
from aptos_sdk.async_client import RestClient
from aptos_sdk.bcs import Serializer
from aptos_sdk.transactions import (
    EntryFunction,
    TransactionArgument,
    TransactionPayload,
)
from aptos_sdk.type_tag import StructTag, TypeTag


# Defaults from your instructions
LIQUIDSWAP_V1_ADDR = "0xc9ccc585c8e1455a5c0ae4e068897a47e7c16cf16f14e0655e3573c2bbc76d48"
ENTRY_MODULE = f"{LIQUIDSWAP_V1_ADDR}::entry"
BINSTEP_X5 = f"{LIQUIDSWAP_V1_ADDR}::bin_steps::X5"
APT_TYPE = "0x1::aptos_coin::AptosCoin"
USDT_TYPE = "0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9::coins::USDT"


@dataclass
class Context:
    account: Account
    rest: RestClient
    addr: AccountAddress


async def load_context(profile_env: str = "APTOS_PROFILE", rest_env: str = "APTOS_REST_URL") -> Context:
    with open(".aptos/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    profile_name = os.environ.get(profile_env, "default")
    prof = cfg["profiles"][profile_name]
    # Use AIP-80 compliant key string directly
    priv = prof["private_key"]
    account = Account.load_key(priv)
    rest_url = os.environ.get(rest_env, prof["rest_url"]).rstrip("/")
    if not rest_url.endswith("/v1"):
        rest_url = rest_url + "/v1"
    rest = RestClient(rest_url)
    print(f"Using profile: {profile_name}")
    print(f"Connected to: {rest_url}")
    print(f"Sender: {account.address()}")
    return Context(account=account, rest=rest, addr=account.address())


async def register_coin_store(ctx: Context, coin_type: str) -> str:
    print(f"Registering coin store for: {coin_type}")
    entry = EntryFunction.natural(
        "0x1::coin",
        "register",
        [TypeTag(StructTag.from_str(coin_type))],
        [],
    )
    payload = TransactionPayload(entry)
    signed = await ctx.rest.create_bcs_signed_transaction(ctx.account, payload)
    txh = await ctx.rest.submit_bcs_transaction(signed)
    await ctx.rest.wait_for_transaction(txh)
    print(f"✔ Registered. Tx: {txh}")
    return txh


async def swap_exact_x_for_y(
    ctx: Context,
    x_type: str,
    y_type: str,
    binstep_type: str,
    amount_in_octas: int,
    min_out: int,
) -> str:
    print(
        f"Swapping {amount_in_octas} X (octas) for >= {min_out} Y via {ENTRY_MODULE}::swap_exact_x_for_y"
    )
    entry = EntryFunction.natural(
        ENTRY_MODULE,
        "swap_exact_x_for_y",
        [
            TypeTag(StructTag.from_str(x_type)),
            TypeTag(StructTag.from_str(y_type)),
            TypeTag(StructTag.from_str(binstep_type)),
        ],
        [
            TransactionArgument(amount_in_octas, Serializer.u64),
            TransactionArgument(min_out, Serializer.u64),
        ],
    )
    payload = TransactionPayload(entry)
    signed = await ctx.rest.create_bcs_signed_transaction(ctx.account, payload)
    txh = await ctx.rest.submit_bcs_transaction(signed)
    await ctx.rest.wait_for_transaction(txh)
    print(f"✔ Swapped. Tx: {txh}")
    return txh


async def get_balance(ctx: Context, coin_type: str, owner: Optional[AccountAddress] = None) -> int:
    owner = owner or ctx.addr
    bal = await ctx.rest.account_balance(owner, coin_type=coin_type)
    return int(bal)


async def main():
    # Defaults from your example
    amount_in = int(os.environ.get("AMOUNT_IN_OCTAS", "20000000"))  # 0.20 APT
    min_out = int(os.environ.get("MIN_OUT", "1"))
    x_type = os.environ.get("X_TYPE", APT_TYPE)
    y_type = os.environ.get("Y_TYPE", USDT_TYPE)
    binstep = os.environ.get("BINSTEP_TYPE", BINSTEP_X5)

    ctx = await load_context()
    try:
        # 1) Register Y store (USDT)
        await register_coin_store(ctx, y_type)

        # 2) Pre balances
        apt_before = await get_balance(ctx, APT_TYPE)
        y_before = await get_balance(ctx, y_type)
        print(f"APT before: {apt_before}")
        print(f"USDT before: {y_before}")

        # 3) Swap
        await swap_exact_x_for_y(ctx, x_type, y_type, binstep, amount_in, min_out)

        # 4) Post balances
        apt_after = await get_balance(ctx, APT_TYPE)
        y_after = await get_balance(ctx, y_type)
        print(f"APT after: {apt_after}")
        print(f"USDT after: {y_after}")
        print(f"Delta APT: {apt_after - apt_before}")
        print(f"Delta USDT: {y_after - y_before}")
    finally:
        await ctx.rest.close()


if __name__ == "__main__":
    asyncio.run(main())

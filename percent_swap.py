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


# Constants (override via env if needed)
APT_TYPE = os.environ.get("APT_TYPE", "0x1::aptos_coin::AptosCoin")
USDT_TYPE = os.environ.get(
    "USDT_TYPE",
    "0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9::coins::USDT",
)
LIQUIDSWAP_ADDR = os.environ.get(
    "LIQUIDSWAP_ADDR",
    "0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9",
)
CURVE_TYPE = os.environ.get(
    "CURVE_TYPE", f"{LIQUIDSWAP_ADDR}::curves::Uncorrelated"
)
SCRIPTS_MODULE = f"{LIQUIDSWAP_ADDR}::scripts"


@dataclass
class Ctx:
    rest: RestClient
    account: Account
    address: AccountAddress


async def load_ctx() -> Ctx:
    with open(".aptos/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    prof_name = os.environ.get("APTOS_PROFILE", "default")
    prof = cfg["profiles"][prof_name]
    # Use AIP-80 value directly to avoid SDK warning
    priv = prof["private_key"]
    account = Account.load_key(priv)
    base = os.environ.get("APTOS_REST_URL", prof["rest_url"]).rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"
    rest = RestClient(base)
    # connectivity check and fallback
    try:
        await rest.info()
    except Exception as e:
        alt = "https://api.testnet.aptoslabs.com/v1"
        print(f"Warning: /info failed on {base}: {e}. Retrying {alt}")
        await rest.close()
        rest = RestClient(alt)
    print(f"Using profile: {prof_name}")
    print(f"Connected to: {rest.base_url}")
    print(f"Sender: {account.address()}")
    return Ctx(rest=rest, account=account, address=account.address())


async def coin_balance(ctx: Ctx, coin_type: str) -> int:
    return int(await ctx.rest.account_balance(ctx.address, coin_type=coin_type))


async def coin_decimals(ctx: Ctx, coin_type: str) -> int:
    # Use BCS view to avoid JSON parsing issues
    res = await ctx.rest.view_bcs_payload(
        "0x1::coin",
        "decimals",
        [TypeTag(StructTag.from_str(coin_type))],
        [],
    )
    return int(res[0])


def human(amount: int, decimals: int) -> str:
    if decimals <= 0:
        return str(amount)
    factor = 10 ** decimals
    integer = amount // factor
    frac = amount % factor
    return f"{integer}.{frac:0{decimals}d}"


async def swap_scripts(ctx: Ctx, x_type: str, y_type: str, amount_in: int, min_out: int) -> str:
    print(
        f"Calling {SCRIPTS_MODULE}::swap<{x_type}, {y_type}, {CURVE_TYPE}> with amount_in={amount_in}, min_out={min_out}"
    )
    entry = EntryFunction.natural(
        SCRIPTS_MODULE,
        "swap",
        [
            TypeTag(StructTag.from_str(x_type)),
            TypeTag(StructTag.from_str(y_type)),
            TypeTag(StructTag.from_str(CURVE_TYPE)),
        ],
        [
            TransactionArgument(amount_in, Serializer.u64),
            TransactionArgument(min_out, Serializer.u64),
        ],
    )
    payload = TransactionPayload(entry)

    # Optional simulate to surface errors early
    try:
        raw = await ctx.rest.create_bcs_transaction(ctx.account, payload)
        sim = await ctx.rest.simulate_transaction(raw, ctx.account, estimate_gas_usage=True)
        print(f"Simulation: {sim}")
    except Exception as e:
        print(f"Simulation failed (continuing): {e}")

    signed = await ctx.rest.create_bcs_signed_transaction(ctx.account, payload)
    txh = await ctx.rest.submit_bcs_transaction(signed)
    await ctx.rest.wait_for_transaction(txh)
    print(f"Swap tx: {txh}")
    return txh


def parse_percent(arg: Optional[str]) -> float:
    if not arg:
        return 20.0
    s = arg.strip().replace("%", "")
    return float(s)


async def main():
    # Parse CLI: --percent <float or int>, default 20
    pct = 20.0
    if "--percent" in sys.argv:
        try:
            pct = parse_percent(sys.argv[sys.argv.index("--percent") + 1])
        except Exception:
            print("Invalid --percent value; using default 20")
            pct = 20.0

    ctx = await load_ctx()
    try:
        # Fetch balances and decimals
        apt_dec = await coin_decimals(ctx, APT_TYPE)
        usdt_dec = await coin_decimals(ctx, USDT_TYPE)
        apt_bal = await coin_balance(ctx, APT_TYPE)
        usdt_bal = await coin_balance(ctx, USDT_TYPE)

        print("Balances BEFORE:")
        print(f"  APT:  raw={apt_bal}  human={human(apt_bal, apt_dec)}")
        print(f"  USDT: raw={usdt_bal} human={human(usdt_bal, usdt_dec)}")

        if pct >= 0:
            # Buy USDT with APT
            amount_in = int(apt_bal * (pct / 100.0))
            if amount_in < 1:
                print("Nothing to swap (computed amount_in < 1)")
            else:
                print(f"Action: Buy USDT with {pct}% of APT => {amount_in} octas")
                await swap_scripts(ctx, APT_TYPE, USDT_TYPE, amount_in, 1)
        else:
            # Sell USDT for APT
            spct = abs(pct)
            amount_in = int(usdt_bal * (spct / 100.0))
            if amount_in < 1:
                print("Nothing to swap (computed amount_in < 1)")
            else:
                print(f"Action: Sell USDT {spct}% => {amount_in} base units")
                await swap_scripts(ctx, USDT_TYPE, APT_TYPE, amount_in, 1)

        # Fetch balances again
        apt_bal2 = await coin_balance(ctx, APT_TYPE)
        usdt_bal2 = await coin_balance(ctx, USDT_TYPE)
        print("Balances AFTER:")
        print(f"  APT:  raw={apt_bal2}  human={human(apt_bal2, apt_dec)}  (Δ {apt_bal2 - apt_bal})")
        print(f"  USDT: raw={usdt_bal2} human={human(usdt_bal2, usdt_dec)} (Δ {usdt_bal2 - usdt_bal})")
    finally:
        await ctx.rest.close()


if __name__ == "__main__":
    asyncio.run(main())

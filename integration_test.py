#!/usr/bin/env python3
import asyncio
import os
import sys
from typing import Optional

import yaml
import requests
from aptos_sdk.account import Account
from aptos_sdk.account_address import AccountAddress
from aptos_sdk.async_client import RestClient
from aptos_sdk.bcs import Serializer
from aptos_sdk.transactions import EntryFunction, TransactionArgument, TransactionPayload
from aptos_sdk.type_tag import StructTag, TypeTag

from find_rate_reduction import find_rate_reduction
from contract_utils import resolve_module_address
from chat import (
    warmup,
    extract,
    get_article_text,
    is_ollama_available,
    OllamaUnavailableError,
)
import os

try:
    from py_ecc.bls.ciphersuites import G2ProofOfPossession as bls
except Exception:
    bls = None


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


def _get_bls_keys() -> tuple[int, bytes]:
    _load_dotenv()
    priv_hex = os.environ.get("BLS_PRIVATE_KEY")
    if not priv_hex:
        raise RuntimeError("BLS_PRIVATE_KEY not set; create a .env or export var")
    priv_hex = priv_hex.lower().removeprefix("0x")
    sk = int(priv_hex, 16)
    if bls is None:
        raise RuntimeError("py_ecc not installed; cannot sign BLS messages")
    pk = bls.SkToPk(sk)
    return sk, bytes(pk)


def _bls_message(abs_bps: int, is_increase: bool) -> bytes:
    s = Serializer()
    s.u64(abs_bps)
    s.bool(is_increase)
    return s.output()


# Defaults aligned with your Python examples and Liquidswap Uncorrelated pool
APT_TYPE = os.environ.get("APT_TYPE", "0x1::aptos_coin::AptosCoin")
USDT_TYPE = os.environ.get(
    "USDT_TYPE",
    "0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9::coins::USDT",
)
CURVE_TYPE = os.environ.get(
    "CURVE_TYPE",
    "0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9::curves::Uncorrelated",
)


async def load_ctx(profile_name: str = "default"):
    with open(".aptos/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    prof = cfg["profiles"][profile_name]
    # Use AIP-80 key format directly
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


async def ensure_coin_store(rest: RestClient, account: Account, coin_type: str) -> Optional[str]:
    try:
        entry = EntryFunction.natural(
            "0x1::coin",
            "register",
            [TypeTag(StructTag.from_str(coin_type))],
            [],
        )
        payload = TransactionPayload(entry)
        signed = await rest.create_bcs_signed_transaction(account, payload)
        txh = await rest.submit_bcs_transaction(signed)
        await rest.wait_for_transaction(txh)
        return txh
    except Exception as e:
        # Likely already registered; ignore
        print(f"Note: register({coin_type}) skipped or failed: {e}")
        return None


async def balance(rest: RestClient, addr: AccountAddress, coin_type: str) -> int:
    return int(await rest.account_balance(addr, coin_type=coin_type))


def decision_from_bps(bps: int) -> tuple[str, int, str, str]:
    # Returns: (action_text, pct, from_coin_type, to_coin_type)
    if bps < 0:
        cut = -bps
        if cut >= 50:
            return ("Decrease ≥50 bps: buy USDT with 30% of APT", 30, APT_TYPE, USDT_TYPE)
        if cut >= 25:
            return ("Decrease ≥25 bps: buy USDT with 10% of APT", 10, APT_TYPE, USDT_TYPE)
        # smaller cuts treated same as no-change per spec
        return ("Small cut: buy APT with 30% of USDT", 30, USDT_TYPE, APT_TYPE)
    elif bps == 0:
        return ("No change: buy APT with 30% of USDT", 30, USDT_TYPE, APT_TYPE)
    else:
        return ("Increase: buy APT with 30% of USDT", 30, USDT_TYPE, APT_TYPE)


async def set_bls_public_key(rest: RestClient, account: Account) -> str:
    """Set the BLS public key in the contract before calling the main function."""
    module_addr = resolve_module_address("interest_rate")
    sk, pk = _get_bls_keys()
    
    entry = EntryFunction.natural(
        f"{module_addr}::interest_rate",
        "set_bls_public_key",
        [],
        [
            TransactionArgument(list(pk), Serializer.sequence_serializer(Serializer.u8)),
        ],
    )
    payload = TransactionPayload(entry)
    signed = await rest.create_bcs_signed_transaction(account, payload)
    txh = await rest.submit_bcs_transaction(signed)
    await rest.wait_for_transaction(txh)
    return txh


async def call_move_real_swap(rest: RestClient, account: Account, abs_bps: int, is_increase: bool) -> str:
    module_addr = resolve_module_address("interest_rate")
    # Prepare BLS signed message
    sk, pk = _get_bls_keys()
    msg = _bls_message(abs_bps, is_increase)
    sig = bls.Sign(sk, msg)
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
            TransactionArgument(list(sig), Serializer.sequence_serializer(Serializer.u8)),
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


def extract_rate_change_from_text_llm(text: str) -> Optional[int]:
    """
    Extracts interest rate change from text using LLM approach.
    
    Args:
        text: The text to parse for rate changes.
        
    Returns:
        The rate change in basis points as an integer (negative for reductions,
        positive for increases), or None if not found.
    """
    if not is_ollama_available():
        print("Ollama not available, skipping LLM extraction")
        return None

    try:
        messages = warmup()
        return extract(text, messages)
    except OllamaUnavailableError as e:
        print(f"Ollama unavailable: {e}")
    except Exception as e:
        print(f"Error using LLM approach: {e}")
    return None


async def run_integration(input_text_or_url: str):
    # 1) Extract basis points
    if input_text_or_url.startswith("http://") or input_text_or_url.startswith("https://"):
        # For URLs, we can use either the existing regex approach or LLM approach
        # Let's use LLM approach for consistency
        try:
            article_text = get_article_text(input_text_or_url)
            if article_text and is_ollama_available():
                try:
                    messages = warmup()
                    bps = extract(article_text, messages)
                except OllamaUnavailableError as e:
                    print(f"Ollama unavailable: {e}")
                    bps = find_rate_reduction(input_text_or_url)
            else:
                bps = find_rate_reduction(input_text_or_url)
        except Exception as e:
            print(f"Error with LLM approach, falling back to regex: {e}")
            bps = find_rate_reduction(input_text_or_url)
        source = input_text_or_url
    else:
        bps = extract_rate_change_from_text_llm(input_text_or_url)
        source = "inline-text"
    if bps is None:
        print("❌ Could not detect a rate change from input")
        return 1

    print(f"📈 Detected change: {bps} bps from {source}")
    abs_bps = abs(bps)
    is_increase = bps > 0
    action_text, pct, from_coin, to_coin = decision_from_bps(bps)
    print(f"Plan: {action_text}")

    # 2) Setup chain context
    account, rest = await load_ctx()
    try:
        # 3) Read balances before (registration handled inside Move entry)
        addr = account.address()
        from_before = await balance(rest, addr, from_coin)
        to_before = await balance(rest, addr, to_coin)
        print(f"Before: from={from_before} to={to_before}")

        # 4) Set BLS public key in the contract first
        key_txh = await set_bls_public_key(rest, account)
        print(f"✅ BLS public key set. Tx: {key_txh}")

        # 5) Call Move entry to execute real swap based on policy
        txh = await call_move_real_swap(rest, account, abs_bps, is_increase)
        print(f"✅ On-chain action executed. Tx: {txh}")

        # 6) Read balances after
        from_after = await balance(rest, addr, from_coin)
        to_after = await balance(rest, addr, to_coin)
        print(f"After:  from={from_after} to={to_after}")
        print(f"Δ from: {from_after - from_before}")
        print(f"Δ to:   {to_after - to_before}")
    finally:
        await rest.close()
    return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python integration_test.py <url-or-text>")
        print("Examples:")
        print("  python integration_test.py https://example.com/fed-cuts")
        print('  python integration_test.py "Fed cuts rates by 50 basis points"')
        sys.exit(2)
    arg = " ".join(sys.argv[1:]).strip()
    rc = asyncio.run(run_integration(arg))
    sys.exit(rc)


if __name__ == "__main__":
    main()

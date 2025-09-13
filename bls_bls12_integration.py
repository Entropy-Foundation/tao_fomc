#!/usr/bin/env python3
"""
End-to-end BLS12-381 demo using py_ecc + Aptos Move verifier.

What it does:
- Generates a BLS keypair with py_ecc (G2 Basic ciphersuite).
- Signs an arbitrary message.
- Publishes a simple Move module that verifies normal signatures.
- Submits a transaction calling `verify_entry` with (msg, sig, pk) bytes.

Prereqs:
- `pip install py_ecc aptos-sdk`
- `.aptos/config.yaml` with a `default` profile (aptos CLI logged in)

Usage:
  python bls_bls12_integration.py "hello aptos"
"""
import asyncio
import os
import subprocess
import sys
from typing import List

import yaml
from aptos_sdk.account import Account
from aptos_sdk.async_client import RestClient
from aptos_sdk.bcs import Serializer
from aptos_sdk.transactions import EntryFunction, TransactionArgument, TransactionPayload


def ensure_py_ecc():
    try:
        from py_ecc.bls import G2Basic as _  # noqa: F401
    except Exception:
        print("Installing py_ecc ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "py_ecc>=6.0.0"])  # type: ignore


def run(cmd: List[str], cwd: str | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.check_call(cmd, cwd=cwd)


async def load_ctx(profile_name: str = "default"):
    with open(".aptos/config.yaml", "r") as f:
        cfg = yaml.safe_load(f)
    prof = cfg["profiles"][profile_name]
    account = Account.load_key(prof["private_key"])  # AIP-80 format supported
    base = prof["rest_url"].rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"
    rest = RestClient(base)
    return account, rest


def publish_move():
    # Publish the standalone package under move_bls/ with named address bound to current account
    try:
        run(["aptos", "move", "publish", "--assume-yes", "--named-addresses", "bls_signer=default"], cwd="move_bls")
    except subprocess.CalledProcessError as e:
        print(f"Note: publish may already exist, continuing: {e}")


async def verify_onchain(message: bytes, sig: bytes, pk: bytes) -> str:
    account, rest = await load_ctx()
    try:
        # Module address is the publisher (this account). We can use its hex.
        module_addr = str(account.address())
        entry = EntryFunction.natural(
            f"{module_addr}::bls_verify",
            "verify_entry",
            [],
            [
                TransactionArgument(list(message), Serializer.sequence_serializer(Serializer.u8)),
                TransactionArgument(list(sig), Serializer.sequence_serializer(Serializer.u8)),
                TransactionArgument(list(pk), Serializer.sequence_serializer(Serializer.u8)),
            ],
        )
        payload = TransactionPayload(entry)
        signed = await rest.create_bcs_signed_transaction(account, payload)
        txh = await rest.submit_bcs_transaction(signed)
        await rest.wait_for_transaction(txh)
        return txh
    finally:
        await rest.close()


async def main():
    ensure_py_ecc()
    from py_ecc.bls import G2ProofOfPossession as bls

    if len(sys.argv) > 1:
        msg = " ".join(sys.argv[1:]).encode()
    else:
        msg = b"Hello Aptos BLS!"

    # 1) Generate keypair and sign using IETF BLS12-381 G2 PoP ciphersuite (pk in G1, sig in G2)
    #    py_ecc expects sk as int; use os.urandom(32) mod curve order via KeyGen helper
    sk = bls.KeyGen(os.urandom(32))
    pk = bls.SkToPk(sk)  # 48 bytes (G1 compressed)
    sig = bls.Sign(sk, msg)  # 96 bytes (G2 compressed)

    assert isinstance(pk, (bytes, bytearray)) and len(pk) == 48, "pk must be 48 bytes"
    assert isinstance(sig, (bytes, bytearray)) and len(sig) == 96, "sig must be 96 bytes"

    # 2) Quick local check
    ok = bls.Verify(pk, msg, sig)
    if not ok:
        print("Local py_ecc verification failed; aborting")
        sys.exit(1)
    print("Local verify: OK")

    # 3) Publish Move module (idempotent updates are fine)
    publish_move()

    # 4) Call on-chain verifier
    txh = await verify_onchain(msg, sig, pk)
    print(f"On-chain verify succeeded in tx: {txh}")


if __name__ == "__main__":
    asyncio.run(main())

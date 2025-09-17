#!/usr/bin/env python3
"""
Threshold Signing Integration Demo for Supra Testnet

This script mirrors the Aptos threshold integration test but finalizes the
on-chain interaction by invoking the Supra CLI against the Supra testnet.

Flow:
1. Detect an interest rate movement from text or URL input
2. Load existing threshold BLS key shares for N servers (default 4, threshold 3)
   or optionally generate a fresh set
3. Simulate T participating servers producing partial signatures
4. Combine partial signatures into a threshold signature that verifies against
   the group public key
5. Use the Supra CLI to set the group public key and submit the recorded rate
   movement transaction

Environment variables used (optional):
- SUPRA_CLI_PATH: Path to the Supra CLI binary
- SUPRA_PROFILE: Supra CLI profile to use (default "fomc-testnet-3")
- SUPRA_CONTRACT_ADDRESS: Override the deployed contract address
- SUPRA_FROM_TYPE, SUPRA_TO_TYPE, SUPRA_CURVE_TYPE: Override type arguments
- SUPRA_SKIP_SET_KEY: If truthy, always skip set_bls_public_key
- SUPRA_SET_KEY: If truthy, override defaults and call set_bls_public_key
- SUPRA_KEYS_DIR: Directory containing saved threshold keys (default "keys")
- SUPRA_FRESH_KEYS: If truthy, generate new threshold keys for this run

Requirements:
- py-ecc installed for BLS operations (already required by threshold_signing.py)
- Supra CLI installed (see SUPRA_CLI_GUIDE.md)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from chat import (
    OllamaUnavailableError,
    extract,
    get_article_text,
    is_ollama_available,
    warmup,
)
from find_rate_reduction import find_rate_reduction
from threshold_signing import (
    combine_threshold_signatures,
    create_bcs_message_for_fomc,
    generate_threshold_keys,
    generate_threshold_signatures,
    get_n,
    get_t,
    set_threshold_config,
    verify_signature,
)

DEFAULT_CLI_PATH = os.path.expanduser("~/Documents/foundation-multisig-tools/supra")
DEFAULT_KEYS_DIR = os.environ.get("SUPRA_KEYS_DIR", "keys")
BASE_PROFILE = "fomc-testnet-3"
BASE_CONTRACT_ADDRESS = "0xb993b8afb07eadc713990f90ec5c422e664c13741dc0e932916a98863cd241a9"
BASE_FROM_TYPE = "0x1::supra_coin::SupraCoin"
BASE_TO_TYPE = "0x6d5684c3585eada2673a7ac9efca870f384fe332c53d0efe8d90f94c59feb164::coins::USDT"
BASE_CURVE_TYPE = "0x4496a672452b0bf5eff5e1616ebfaf7695e14b02a12ed211dd4f28ac38a5d54c::curves::Uncorrelated"


def get_cli_profile_default() -> str:
    """Return the Supra CLI profile, considering environment overrides."""
    return os.environ.get("SUPRA_PROFILE", BASE_PROFILE)


def get_contract_address() -> str:
    """Return the deployed contract address, considering environment overrides."""
    return os.environ.get("SUPRA_CONTRACT_ADDRESS", BASE_CONTRACT_ADDRESS)


def get_type_args() -> tuple[str, str, str]:
    """Return the Move type arguments for the Supra contract hooks."""
    return (
        os.environ.get("SUPRA_FROM_TYPE", BASE_FROM_TYPE),
        os.environ.get("SUPRA_TO_TYPE", BASE_TO_TYPE),
        os.environ.get("SUPRA_CURVE_TYPE", BASE_CURVE_TYPE),
    )


def coerce_bps(value: Union[int, float]) -> int:
    """Normalize basis points returned by detection helpers."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite basis point value: {value}")
        return int(round(value))
    raise TypeError(f"Unsupported basis point type: {type(value)!r}")


def load_dotenv(path: str = ".env") -> None:
    """Load environment variables from a .env file if present."""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    except Exception:
        # Best-effort dotenv; ignore parsing errors to match existing scripts
        pass


def decision_from_bps(bps: int) -> tuple[str, int, str, str]:
    """Return human-readable action and direction of swap based on rate move."""
    supra_type, usdt_type, _curve = get_type_args()

    if bps < 0:
        cut = -bps
        if cut >= 50:
            return ("Decrease ≥50 bps: swap 30% of SUPRA into USDT", 30, supra_type, usdt_type)
        if cut >= 25:
            return ("Decrease ≥25 bps: swap 10% of SUPRA into USDT", 10, supra_type, usdt_type)
        return ("Small cut: swap 30% of USDT into SUPRA", 30, usdt_type, supra_type)
    if bps == 0:
        return ("No change: swap 30% of USDT into SUPRA", 30, usdt_type, supra_type)
    return ("Increase: swap 30% of USDT into SUPRA", 30, usdt_type, supra_type)


def extract_rate_change_from_text_llm(text: str) -> Optional[int]:
    """Extract the rate change (in basis points) using the local LLM pipeline."""
    if not is_ollama_available():
        print("Ollama not available, skipping LLM extraction")
        return None

    try:
        messages = warmup()
        return extract(text, messages)
    except OllamaUnavailableError as exc:
        print(f"Ollama unavailable: {exc}")
    except Exception as exc:
        print(f"Error using LLM approach: {exc}")
    return None


def simulate_threshold_signing_servers(
    private_keys: Dict[int, bytes],
    public_keys: Dict[int, bytes],
    bcs_message: bytes,
    participating_servers: Sequence[int],
) -> Dict[int, bytes]:
    """Simulate each participating server producing and verifying a partial signature."""
    print(f"\n=== SIMULATING {len(participating_servers)} FOMC SERVERS ===")

    signing_private_keys = {server_id: private_keys[server_id] for server_id in participating_servers}
    signing_public_keys = {server_id: public_keys[server_id] for server_id in participating_servers}

    print(f"🔗 Coordinating threshold signatures from servers: {list(participating_servers)}")
    threshold_partials = generate_threshold_signatures(
        signing_private_keys,
        bcs_message,
        list(participating_servers),
        signing_public_keys,
    )

    for server_id in participating_servers:
        print(f"✅ Server {server_id}: Contributed partial signature")

    print(f"🔗 All {len(participating_servers)} servers have generated partial signatures")
    return threshold_partials


def bool_env(name: str) -> bool:
    """Return True if an environment variable is set to a truthy value."""
    value = os.environ.get(name)
    return bool(value) and value.lower() in {"1", "true", "yes", "on"}


def load_threshold_keys_from_files(keys_dir: str) -> Tuple[Dict[int, bytes], Dict[int, bytes], bytes, int, int]:
    """Load threshold key material from disk."""
    keys_path = Path(keys_dir)
    priv_path = keys_path / "bls_private_keys.json"
    pub_path = keys_path / "bls_public_keys.json"

    if not priv_path.exists() or not pub_path.exists():
        raise FileNotFoundError(
            f"Threshold key files not found in {keys_path}. Run setup_keys.py or pass --fresh-keys."
        )

    try:
        with priv_path.open("r", encoding="utf-8") as handle:
            priv_data = json.load(handle)
        with pub_path.open("r", encoding="utf-8") as handle:
            pub_data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse key JSON files in {keys_path}: {exc}") from exc

    private_keys: Dict[int, bytes] = {}
    for label, hex_value in priv_data.items():
        try:
            server_id = int(label.split("_")[1])
        except (IndexError, ValueError) as exc:
            raise RuntimeError(f"Invalid server key label '{label}' in {priv_path}") from exc
        private_keys[server_id] = bytes.fromhex(hex_value)

    server_publics = pub_data.get("server_public_keys")
    if not isinstance(server_publics, dict):
        raise RuntimeError(f"Missing server_public_keys in {pub_path}")

    public_keys: Dict[int, bytes] = {}
    for label, hex_value in server_publics.items():
        try:
            server_id = int(label.split("_")[1])
        except (IndexError, ValueError) as exc:
            raise RuntimeError(f"Invalid server public key label '{label}' in {pub_path}") from exc
        public_keys[server_id] = bytes.fromhex(hex_value)

    group_hex = pub_data.get("group_public_key")
    if not isinstance(group_hex, str):
        raise RuntimeError(f"Missing group_public_key in {pub_path}")
    group_public_key = bytes.fromhex(group_hex)

    threshold = int(pub_data.get("threshold", len(public_keys)))
    total_servers = int(pub_data.get("total_servers", len(public_keys)))

    return private_keys, public_keys, group_public_key, total_servers, threshold


def obtain_threshold_keys(
    generate_new: bool,
    keys_dir: str,
    requested_config: Optional[Tuple[int, int]] = None,
) -> Tuple[Dict[int, bytes], Dict[int, bytes], bytes, bool]:
    """Return threshold key material, loading from disk unless forced to generate."""
    if not generate_new:
        try:
            private_keys, public_keys, group_public_key, total_servers, threshold = load_threshold_keys_from_files(keys_dir)
        except FileNotFoundError as exc:
            raise RuntimeError(str(exc)) from exc

        if requested_config and requested_config != (total_servers, threshold):
            req_n, req_t = requested_config
            print(
                f"⚠️ Loaded key set for {total_servers} servers with {threshold}-of-{total_servers} threshold; "
                f"overriding requested {req_t}-of-{req_n} configuration."
            )

        set_threshold_config(total_servers, threshold)
        return private_keys, public_keys, group_public_key, True

    private_keys, public_keys, group_public_key = generate_threshold_keys()
    return private_keys, public_keys, group_public_key, False


def run_cli(cmd: List[str]) -> subprocess.CompletedProcess[str]:
    """Execute a Supra CLI command, surfacing stdout/stderr on success or failure."""
    print("CLI command:\n  " + " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Supra CLI not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        print("=== CLI call failed ===")
        print(exc.stdout)
        print(exc.stderr)
        raise

    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print("Stderr:")
        print(result.stderr.strip())
    return result


def set_bls_public_key_cli(group_public_key: bytes, profile: str, cli_path: str) -> None:
    """Upload the freshly generated group public key to the Supra contract."""
    contract_address = get_contract_address()
    function_id = f"{contract_address}::fomc_interest_rate_dexlyn::set_bls_public_key"
    args = [f"hex:{group_public_key.hex()}"]

    print("\n=== SETTING BLS PUBLIC KEY ONCHAIN (SUPRA) ===")
    cmd = [
        cli_path,
        "move",
        "tool",
        "run",
        "--function-id",
        function_id,
        "--args",
    ] + args + [
        "--profile",
        profile,
        "--max-gas",
        "1000",
        "--gas-unit-price",
        "100",
        "--assume-yes",
    ]

    run_cli(cmd)
    print("✅ BLS public key submitted to Supra testnet")


def submit_interest_rate_transaction(
    abs_bps: int,
    is_increase: bool,
    signature: bytes,
    profile: str,
    cli_path: str,
) -> None:
    """Execute the Supra CLI transaction to record the interest rate movement."""
    contract_address = get_contract_address()
    function_id = f"{contract_address}::fomc_interest_rate_dexlyn::record_interest_rate_movement_dexlyn"
    type_args = list(get_type_args())
    args = [
        f"u64:{abs_bps}",
        f"bool:{str(is_increase).lower()}",
        f"hex:{signature.hex()}",
    ]

    print("\n=== SUBMITTING SUPRA TRANSACTION ===")
    cmd = [
        cli_path,
        "move",
        "tool",
        "run",
        "--function-id",
        function_id,
        "--type-args",
    ] + type_args + [
        "--args",
    ] + args + [
        "--profile",
        profile,
        "--max-gas",
        "1000",
        "--gas-unit-price",
        "100",
        "--assume-yes",
    ]

    run_cli(cmd)
    print("✅ Supra transaction executed")


def detect_basis_points(input_text_or_url: str) -> Optional[int]:
    """Determine the basis point change from either URL or inline text."""
    if input_text_or_url.startswith("http://") or input_text_or_url.startswith("https://"):
        try:
            article_text = get_article_text(input_text_or_url)
            if article_text and is_ollama_available():
                try:
                    messages = warmup()
                    return extract(article_text, messages)
                except OllamaUnavailableError as exc:
                    print(f"Ollama unavailable: {exc}")
            return find_rate_reduction(input_text_or_url)
        except Exception as exc:
            print(f"Error processing URL, falling back to regex: {exc}")
            return find_rate_reduction(input_text_or_url)
    return extract_rate_change_from_text_llm(input_text_or_url)


def run_threshold_integration_supra(
    input_text_or_url: str,
    profile: str,
    cli_path: str,
    servers_override: Optional[List[int]] = None,
    skip_set_key: bool = False,
    keys_dir: str = DEFAULT_KEYS_DIR,
    generate_new_keys: bool = False,
) -> int:
    """Main execution path for Supra threshold signing integration."""
    print("🚀 Starting FOMC Threshold Signing Integration (Supra)")

    requested_config = (get_n(), get_t())
    try:
        private_keys, public_keys, group_public_key, loaded_from_disk = obtain_threshold_keys(
            generate_new_keys,
            keys_dir,
            requested_config,
        )
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1

    n, t = get_n(), get_t()
    print(f"📊 Configuration: {n} servers, {t}-of-{n} threshold")

    if loaded_from_disk:
        print(f"🔑 Loaded threshold key set from {Path(keys_dir).resolve()}")
    else:
        print("🆕 Generated a fresh threshold key set for this run")

    # 1) Generate threshold keys
    print("\n=== THRESHOLD KEY MATERIAL ===")
    print(f"✅ Ready with key material for {n} servers")
    print(f"🔑 Group public key: {group_public_key.hex()[:32]}...")

    # 2) Extract rate change information
    print("\n=== RATE CHANGE DETECTION ===")
    bps = detect_basis_points(input_text_or_url)
    if bps is None:
        print("❌ Could not detect a rate change from input")
        return 1
    bps = coerce_bps(bps)

    source = "URL" if input_text_or_url.startswith(("http://", "https://")) else "inline-text"
    print(f"📈 Detected change: {bps} bps from {source}")
    abs_bps = abs(bps)
    is_increase = bps > 0
    action_text, pct, from_coin, to_coin = decision_from_bps(bps)
    print(f"📋 Plan: {action_text}")
    print(f"🔄 Swap direction: {from_coin} -> {to_coin} ({pct}% portfolio slice)")

    # 3) Prepare message for signing
    print("\n=== BCS MESSAGE PREPARATION ===")
    bcs_message = create_bcs_message_for_fomc(abs_bps, is_increase)
    print(f"📝 BCS message: {bcs_message.hex()}")

    # 4) Generate partial signatures
    print("\n=== THRESHOLD SIGNING ===")
    available_servers = sorted(private_keys.keys())
    if len(available_servers) < t:
        print(
            f"❌ Only found keys for {len(available_servers)} server(s); need at least {t} for signing"
        )
        return 1
    if servers_override:
        participating_servers = servers_override
    else:
        participating_servers = available_servers[:t]

    missing_servers = [sid for sid in participating_servers if sid not in private_keys]
    if missing_servers:
        print(f"❌ Missing private keys for servers: {missing_servers}")
        return 1
    print(f"🖥️  Participating servers: {participating_servers}")

    partial_signatures = simulate_threshold_signing_servers(
        private_keys,
        public_keys,
        bcs_message,
        participating_servers,
    )

    # 5) Combine partial signatures
    print("\n=== THRESHOLD SIGNATURE COMBINATION ===")
    threshold_signature = combine_threshold_signatures(partial_signatures)
    print(f"🔐 Threshold signature: {threshold_signature.hex()[:32]}...")

    # 6) Optional local verification
    print("\n=== LOCAL VERIFICATION (OPTIONAL) ===")
    if verify_signature(group_public_key, bcs_message, threshold_signature):
        print("✅ Threshold signature verified against group public key")
    else:
        print("⚠️ Threshold signature failed local verification (contract will verify)")

    # 7) Execute Supra CLI calls
    print("\n=== SUPRA CLI EXECUTION ===")
    if skip_set_key:
        print("Skipping set_bls_public_key (pass --set-key or SUPRA_SET_KEY=1 to enable)")
    else:
        set_bls_public_key_cli(group_public_key, profile, cli_path)

    submit_interest_rate_transaction(abs_bps, is_increase, threshold_signature, profile, cli_path)
    print("\n🎉 Supra threshold integration completed successfully")
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Command-line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Run the Supra threshold signing integration test",
    )
    parser.add_argument(
        "input",
        nargs=argparse.REMAINDER,
        help="URL or inline text describing the rate change",
    )
    parser.add_argument(
        "--n",
        type=int,
        help="Total number of servers (overrides default configuration)",
    )
    parser.add_argument(
        "--t",
        type=int,
        help="Threshold number of servers required to sign",
    )
    profile_default = get_cli_profile_default()
    parser.add_argument(
        "--profile",
        default=profile_default,
        help=f"Supra CLI profile to use (default: {profile_default})",
    )
    parser.add_argument(
        "--cli-path",
        default=os.environ.get("SUPRA_CLI_PATH", DEFAULT_CLI_PATH),
        help="Path to the Supra CLI binary",
    )
    parser.add_argument(
        "--servers",
        nargs="+",
        type=int,
        help="Explicit list of server IDs to use for signing",
    )
    parser.add_argument(
        "--set-key",
        action="store_true",
        help="Also call set_bls_public_key before submitting the transaction",
    )
    parser.add_argument(
        "--fresh-keys",
        action="store_true",
        help="Generate a new threshold key set for this run (does not persist)",
    )
    keys_default = os.environ.get("SUPRA_KEYS_DIR", DEFAULT_KEYS_DIR)
    parser.add_argument(
        "--keys-dir",
        default=keys_default,
        help=f"Directory containing saved threshold keys (default: {keys_default})",
    )

    args = parser.parse_args(argv)

    if not args.input:
        parser.print_help()
        sys.exit(2)

    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    load_dotenv()
    args = parse_args(argv)

    if args.n is not None or args.t is not None:
        current_n, current_t = get_n(), get_t()
        n = args.n if args.n is not None else current_n
        t = args.t if args.t is not None else current_t
        set_threshold_config(n, t)

    env_force_set = bool_env("SUPRA_SET_KEY")
    env_skip_set = bool_env("SUPRA_SKIP_SET_KEY")

    if args.set_key or env_force_set:
        skip_set_key = False
    elif env_skip_set:
        skip_set_key = True
    else:
        skip_set_key = True
    fresh_keys = args.fresh_keys or bool_env("SUPRA_FRESH_KEYS")
    cli_path = os.path.expanduser(args.cli_path)
    keys_dir = os.path.expanduser(args.keys_dir)

    input_text_or_url = " ".join(args.input).strip()
    servers_override = args.servers if args.servers else None

    try:
        return run_threshold_integration_supra(
            input_text_or_url,
            args.profile,
            cli_path,
            servers_override,
            skip_set_key,
            keys_dir,
            fresh_keys,
        )
    except subprocess.CalledProcessError:
        return 1
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

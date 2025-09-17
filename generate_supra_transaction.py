#!/usr/bin/env python3
"""
Generate inputs and send transaction for record_interest_rate_movement_dexlyn function.

This script:
1. Creates a BLS signature for the interest rate movement
2. Calls the Supra CLI to execute the transaction onchain
3. Uses a rate decrease of 50 basis points to trigger USDT purchase with SUPRA tokens
"""

import os
import subprocess
import sys
from aptos_sdk.bcs import Serializer

def load_dotenv(path: str = ".env") -> None:
    """Load environment variables from .env file."""
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

def get_bls_keys() -> tuple[int, bytes]:
    """Get BLS private and public keys from environment."""
    load_dotenv()
    priv_hex = os.environ.get("BLS_PRIVATE_KEY")
    if not priv_hex:
        raise RuntimeError("BLS_PRIVATE_KEY not set; create a .env or export var")
    priv_hex = priv_hex.lower().removeprefix("0x")
    sk = int(priv_hex, 16)
    
    try:
        from py_ecc.bls.ciphersuites import G2ProofOfPossession as bls
    except ImportError:
        raise RuntimeError("py_ecc not installed; run: pip install py_ecc")
    
    pk = bls.SkToPk(sk)
    return sk, bytes(pk)

def create_bls_message(basis_points: int, is_increase: bool) -> bytes:
    """Create BCS-serialized message for signing."""
    s = Serializer()
    s.u64(basis_points)
    s.bool(is_increase)
    return s.output()

def sign_message(basis_points: int, is_increase: bool) -> bytes:
    """Create BLS signature for the interest rate movement."""
    sk, pk = get_bls_keys()
    msg = create_bls_message(basis_points, is_increase)
    
    try:
        from py_ecc.bls.ciphersuites import G2ProofOfPossession as bls
        sig = bls.Sign(sk, msg)
        return bytes(sig)
    except ImportError:
        raise RuntimeError("py_ecc not installed; run: pip install py_ecc")

def set_bls_public_key_onchain(profile: str = "fomc-testnet-3"):
    """Set the BLS public key onchain before calling the main function."""
    sk, pk = get_bls_keys()
    
    # Contract details
    contract_address = "0xb993b8afb07eadc713990f90ec5c422e664c13741dc0e932916a98863cd241a9"
    function_id = f"{contract_address}::fomc_interest_rate_dexlyn::set_bls_public_key"
    
    # Function arguments - public key as hex
    args = [f"hex:{pk.hex()}"]
    
    # Build the CLI command
    supra_cli = os.path.expanduser("~/Documents/foundation-multisig-tools/supra")
    cmd = [
        supra_cli,
        "move", "tool", "run",
        "--function-id", function_id,
        "--args"] + args + [
        "--profile", profile,
        "--max-gas", "1000",
        "--gas-unit-price", "100",
        "--assume-yes"
    ]
    
    print("=== SETTING BLS PUBLIC KEY ONCHAIN ===")
    print(" ".join(cmd))
    print()
    
    # Execute the command
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("=== BLS PUBLIC KEY SET SUCCESS ===")
        print(result.stdout)
        if result.stderr:
            print("Stderr:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print("=== BLS PUBLIC KEY SET FAILED ===")
        print("Return code:", e.returncode)
        print("Stdout:", e.stdout)
        print("Stderr:", e.stderr)
        return False
    except FileNotFoundError:
        print(f"Error: Supra CLI not found at {supra_cli}")
        print("Please check the path in SUPRA_CLI_GUIDE.md")
        return False

def call_supra_cli(basis_points: int, is_increase: bool, signature_hex: str, profile: str = "fomc-testnet-3"):
    """Call the Supra CLI to execute the transaction."""
    
    # Contract details from Move.toml and SUPRA_CLI_GUIDE.md
    contract_address = "0xb993b8afb07eadc713990f90ec5c422e664c13741dc0e932916a98863cd241a9"
    function_id = f"{contract_address}::fomc_interest_rate_dexlyn::record_interest_rate_movement_dexlyn"
    
    # Type arguments for SUPRA -> USDT swap (correct coin types)
    type_args = [
        "0x1::supra_coin::SupraCoin",  # SUPRA coin type
        "0x6d5684c3585eada2673a7ac9efca870f384fe332c53d0efe8d90f94c59feb164::coins::USDT",  # USDT coin type
        "0x4496a672452b0bf5eff5e1616ebfaf7695e14b02a12ed211dd4f28ac38a5d54c::curves::Uncorrelated"  # Curve type
    ]
    
    # Function arguments
    args = [
        f"u64:{basis_points}",
        f"bool:{str(is_increase).lower()}",
        f"hex:{signature_hex}"
    ]
    
    # Build the CLI command
    supra_cli = os.path.expanduser("~/Documents/foundation-multisig-tools/supra")
    cmd = [
        supra_cli,
        "move", "tool", "run",
        "--function-id", function_id,
        "--type-args"] + type_args + [
        "--args"] + args + [
        "--profile", profile,
        "--max-gas", "1000",
        "--gas-unit-price", "100",
        "--assume-yes"
    ]
    
    print("=== SUPRA CLI COMMAND ===")
    print(" ".join(cmd))
    print()
    
    # Execute the command
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("=== TRANSACTION SUCCESS ===")
        print(result.stdout)
        if result.stderr:
            print("Stderr:", result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print("=== TRANSACTION FAILED ===")
        print("Return code:", e.returncode)
        print("Stdout:", e.stdout)
        print("Stderr:", e.stderr)
        return False
    except FileNotFoundError:
        print(f"Error: Supra CLI not found at {supra_cli}")
        print("Please check the path in SUPRA_CLI_GUIDE.md")
        return False

def main():
    """Main function to generate inputs and send transaction."""
    print("=== FOMC INTEREST RATE MOVEMENT - SUPRA DEXLYN ===")
    print()
    
    # Use a 50 basis point decrease to trigger USDT purchase (30% of SUPRA)
    # Based on the contract logic: if (!is_increase && basis_points >= 50)
    basis_points = 50
    is_increase = False
    
    print(f"Interest Rate Movement: {basis_points} basis points {'increase' if is_increase else 'decrease'}")
    print("Expected Action: Buy USDT with 30% of SUPRA tokens")
    print()
    
    try:
        # Generate BLS signature
        print("=== GENERATING BLS SIGNATURE ===")
        signature = sign_message(basis_points, is_increase)
        signature_hex = signature.hex()
        
        print(f"Basis Points: {basis_points}")
        print(f"Is Increase: {is_increase}")
        print(f"BCS Message: {create_bls_message(basis_points, is_increase).hex()}")
        print(f"BLS Signature: {signature_hex}")
        print()
        
        # First, set the BLS public key onchain
        print("=== SETTING BLS PUBLIC KEY ONCHAIN ===")
        key_success = set_bls_public_key_onchain()
        
        if not key_success:
            print("❌ Failed to set BLS public key onchain!")
            return 1
        
        print("✅ BLS public key set successfully!")
        print()
        
        # Send transaction via Supra CLI
        print("=== SENDING TRANSACTION ===")
        success = call_supra_cli(basis_points, is_increase, signature_hex)
        
        if success:
            print("✅ Transaction sent successfully!")
            print("The contract should now swap 30% of SUPRA tokens for USDT via DexLyn")
        else:
            print("❌ Transaction failed!")
            return 1
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
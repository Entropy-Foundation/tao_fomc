#!/usr/bin/env python3
"""
Threshold Signing with BLS12-381 for FOMC servers.

This module implements configurable threshold signatures where any T out of N servers
can create a valid signature that verifies against a group public key.

Supported configurations include (4,3), (7,5), (10,7) and any valid (N,T) where T <= N.

Based on the threshold-ai-oracle implementation, this uses:
1. Shamir's Secret Sharing to distribute private key shares
2. Lagrange interpolation for threshold signature generation
3. BLS12-381 curve with py-ecc library
4. Aptos-compatible BCS message serialization

Usage:
    # Use default configuration (4,3)
    python threshold_signing.py
    
    # Use custom configuration
    python threshold_signing.py 7 5
    
    # Programmatic usage
    from threshold_signing import set_threshold_config, main
    set_threshold_config(10, 7)
    main()
"""

import os
import secrets
import hashlib
import base64
from typing import List, Tuple, Dict, Optional
from py_ecc.optimized_bls12_381.optimized_curve import (
    G1, G2, add, multiply, curve_order, normalize,
)
from py_ecc.optimized_bls12_381.optimized_pairing import pairing
from py_ecc.bls.hash_to_curve import hash_to_G2
from py_ecc.bls.g2_primitives import G1_to_pubkey, G2_to_signature
from aptos_sdk.bcs import Serializer

# FOMC threshold configuration - now configurable
# Examples: (4,3), (7,5), (10,7) - but supports any N and T <= N
DEFAULT_N = 4  # Default total number of servers
DEFAULT_T = 3  # Default threshold (need at least 3 servers to sign)

class ThresholdConfig:
    """Configuration class for threshold signing parameters."""
    
    def __init__(self, n: int = DEFAULT_N, t: int = DEFAULT_T):
        """
        Initialize threshold configuration.
        
        Args:
            n: Total number of servers (must be >= 1)
            t: Threshold (minimum number of servers needed to sign, must be 1 <= t <= n)
        
        Raises:
            ValueError: If the configuration parameters are invalid
        """
        if n < 1:
            raise ValueError(f"Number of servers {n} must be at least 1")
        
        if t < 1:
            raise ValueError(f"Threshold {t} must be at least 1")
            
        if t > n:
            raise ValueError(f"Threshold {t} cannot be greater than total servers {n}")
            
        self.n = n
        self.t = t
        
    def __str__(self) -> str:
        return f"{self.n} servers, {self.t}-of-{self.n} threshold"
    
    @classmethod
    def create_config(cls, n: int, t: int) -> 'ThresholdConfig':
        """Create a threshold configuration with validation."""
        return cls(n, t)

# Global configuration instance - can be modified at runtime
_config = ThresholdConfig()

def set_threshold_config(n: int, t: int) -> None:
    """Set the global threshold configuration."""
    global _config
    _config = ThresholdConfig.create_config(n, t)

def get_threshold_config() -> ThresholdConfig:
    """Get the current threshold configuration."""
    return _config

# Convenience functions for backward compatibility
def get_n() -> int:
    """Get the current number of servers."""
    return _config.n

def get_t() -> int:
    """Get the current threshold."""
    return _config.t

# Domain Separation Tag for BLS signatures (Aptos compatible)
DST = b"BLS_SIG_BLS12381G2_XMD:SHA-256_SSWU_RO_NUL_"

def mod_inv(x: int) -> int:
    """Compute modular inverse of x modulo curve_order."""
    return pow(x, -1, curve_order)

def lagrange_coefficient(i: int, ids: List[int]) -> int:
    """Compute Lagrange coefficient for server i given list of server IDs."""
    num = den = 1
    for j in ids:
        if j == i:
            continue
        num = (num * j) % curve_order
        den = (den * (j - i)) % curve_order
    return (num * mod_inv(den)) % curve_order

def generate_polynomial(degree: int, secret: int) -> List[int]:
    """Generate a random polynomial of given degree with constant term as secret."""
    poly = [secret]  # Constant term is the secret
    # Generate random coefficients
    for _ in range(degree):
        coef = secrets.randbelow(curve_order)
        poly.append(coef)
    return poly

def evaluate_polynomial(poly: List[int], x: int) -> int:
    """Evaluate polynomial at point x using curve_order modular arithmetic."""
    result = 0
    for i, coef in enumerate(poly):
        # Compute coef * x^i mod curve_order
        term = (coef * pow(x, i, curve_order)) % curve_order
        result = (result + term) % curve_order
    return result

def generate_threshold_keys() -> Tuple[Dict[int, bytes], Dict[int, bytes], bytes]:
    """
    Generate threshold keys for configurable FOMC servers.
    
    This creates a master secret and distributes shares to N servers such that
    any T servers can reconstruct the master secret using Lagrange interpolation.
    
    Returns:
        private_keys: Dict mapping server ID to private key bytes (secret shares)
        public_keys: Dict mapping server ID to public key bytes
        group_public_key: The group public key bytes derived from master secret
    """
    config = get_threshold_config()
    n, t = config.n, config.t
    
    print("\n=== FOMC THRESHOLD KEY GENERATION ===")
    print(f"Generating keys for {n} servers with threshold {t}")
    
    # Generate master secret
    master_secret = secrets.randbelow(curve_order)
    print(f"Generated master secret: {master_secret % 1000000}")  # Show last 6 digits
    
    # Generate polynomial of degree t-1 with master secret as constant term
    polynomial = generate_polynomial(t-1, master_secret)
    print(f"Polynomial coefficients (mod 1000000): {[c % 1000000 for c in polynomial]}")
    
    # Generate secret shares for each server using polynomial evaluation
    private_keys = {}
    public_keys = {}
    
    for server_id in range(1, n+1):
        # Evaluate polynomial at point server_id to get secret share
        secret_share = evaluate_polynomial(polynomial, server_id)
        
        # Convert to bytes for private key (32 bytes, big-endian)
        private_key_bytes = secret_share.to_bytes(32, 'big')
        private_keys[server_id] = private_key_bytes
        
        # Generate public key (secret * G1_generator) - Min-PK scheme
        public_key_point = multiply(G1, secret_share)
        public_key_bytes = G1_to_pubkey(public_key_point)  # 48 bytes compressed
        public_keys[server_id] = public_key_bytes
        
        print(f"Server {server_id} secret share: {secret_share % 1000000}")
    
    # Generate group public key from master secret
    group_public_key_point = multiply(G1, master_secret)
    group_public_key = G1_to_pubkey(group_public_key_point)  # 48 bytes compressed
    
    print(f"Group public key derived from master secret")
    
    # Verify that secret shares can reconstruct master secret
    print(f"\nVerifying Shamir's Secret Sharing reconstruction...")
    test_indices = list(range(1, t+1))  # Use first t servers
    reconstructed = 0
    
    for i in test_indices:
        coeff = lagrange_coefficient(i, test_indices)
        share_value = int.from_bytes(private_keys[i], 'big')
        term = (coeff * share_value) % curve_order
        reconstructed = (reconstructed + term) % curve_order
    
    reconstruction_success = reconstructed == master_secret
    print(f"Secret reconstruction: {'SUCCESS' if reconstruction_success else 'FAILED'}")
    print(f"Original: {master_secret % 1000000}, Reconstructed: {reconstructed % 1000000}")
    
    return private_keys, public_keys, group_public_key

def create_bcs_message_for_fomc(abs_bps: int, is_increase: bool) -> bytes:
    """
    Create BCS-serialized message for FOMC rate change signing.
    
    Args:
        abs_bps: Absolute value of basis points change
        is_increase: True if rate increase, False if decrease
    
    Returns:
        BCS-serialized bytes ready for signing
    """
    serializer = Serializer()
    
    # Serialize u64 abs_bps
    Serializer.u64(serializer, abs_bps)
    
    # Serialize bool is_increase
    Serializer.bool(serializer, is_increase)
    
    # Get the final BCS bytes
    bcs_bytes = serializer.output()
    
    return bcs_bytes

def sign_bcs_message(private_key_bytes: bytes, bcs_message: bytes) -> bytes:
    """Sign BCS-serialized message bytes using a private key - Aptos compatible."""
    try:
        # Use the same BLS import as the original integration test (ignore Pylance error)
        from py_ecc.bls.ciphersuites import G2ProofOfPossession as bls
        
        # Convert private key bytes to integer
        private_key_scalar = int.from_bytes(private_key_bytes, 'big')
        
        # Use the same signing method as the original integration test
        signature_bytes = bls.Sign(private_key_scalar, bcs_message)  # type: ignore
        
        return bytes(signature_bytes)
        
    except Exception as e:
        print(f"BLS signing error: {e}")
        # Fallback to manual implementation
        H = hash_to_G2(bcs_message, DST, hashlib.sha256)  # type: ignore
        private_key_scalar = int.from_bytes(private_key_bytes, 'big')
        signature_point = multiply(H, private_key_scalar)
        signature_bytes = G2_to_signature(signature_point)
        return signature_bytes

def verify_signature(public_key_bytes: bytes, bcs_message: bytes, signature_bytes: bytes) -> bool:
    """Verify a signature against a public key and BCS message bytes."""
    try:
        # Use the same BLS import as the original integration test (ignore Pylance error)
        from py_ecc.bls.ciphersuites import G2ProofOfPossession as bls
        
        # FIXED: Pass bytes directly to bls.Verify - it handles the conversion internally
        # Don't convert to points manually, let py_ecc do it
        return bls.Verify(public_key_bytes, bcs_message, signature_bytes)  # type: ignore
        
    except Exception as e:
        print(f"BLS verification error: {e}")
        return False

def generate_threshold_signatures(private_keys: Dict[int, bytes], bcs_message: bytes,
                                 indices: List[int], public_keys: Dict[int, bytes]) -> Dict[int, bytes]:
    """
    Generate partial signatures by signing the message with individual private keys directly.
    
    Each signer creates a partial signature using their secret share without any scaling.
    The Lagrange interpolation will be applied later during signature combination.
    Each partial signature is verified against its corresponding public key before returning.
    
    Args:
        private_keys: Dict mapping server ID to private key bytes (secret shares)
        bcs_message: The BCS-serialized message to sign
        indices: List of server IDs that will participate in signing
        public_keys: Dict mapping server ID to public key bytes for verification
    
    Returns:
        Dict mapping server ID to partial signature bytes
    """
    config = get_threshold_config()
    t = config.t
    
    print(f"\n=== FOMC PARTIAL SIGNATURE GENERATION ===")
    print(f"Generating partial signatures from servers: {indices[:t]}")
    
    if len(indices) < t:
        raise ValueError(f"Need at least {t} signers, got {len(indices)}")
    
    # Use only the first t signers
    signing_indices = indices[:t]
    
    # Each signer signs the message with their individual private key (no scaling)
    partial_signatures = {}
    
    for server_id in signing_indices:
        # Sign BCS message directly with the private key share
        partial_sig = sign_bcs_message(private_keys[server_id], bcs_message)
        
        # Verify the partial signature using the corresponding public key
        print(f"Server {server_id}: verifying partial signature...")
        is_valid = verify_signature(public_keys[server_id], bcs_message, partial_sig)
        
        if not is_valid:
            raise ValueError(f"Partial signature verification failed for server {server_id}")
        
        partial_signatures[server_id] = partial_sig
        
        # Get private key scalar for logging
        private_key_scalar = int.from_bytes(private_keys[server_id], 'big')
        print(f"Server {server_id}: ✅ partial signature verified (scalar={private_key_scalar % 1000000})")
    
    print(f"Partial signature generation and verification complete!")
    return partial_signatures

def combine_threshold_signatures(partial_signatures: Dict[int, bytes]) -> bytes:
    """
    Combine partial signatures by applying Lagrange interpolation to the signatures.
    
    Each partial signature is scaled by its corresponding Lagrange coefficient
    and then aggregated to produce the final threshold signature.
    
    Args:
        partial_signatures: Dict mapping server ID to partial signature bytes
    
    Returns:
        Combined threshold signature bytes
    """
    config = get_threshold_config()
    t = config.t
    
    print(f"\n=== FOMC THRESHOLD SIGNATURE COMBINATION ===")
    print(f"Combining {len(partial_signatures)} partial signatures")
    
    if len(partial_signatures) < t:
        raise ValueError(f"Need at least {t} partial signatures, got {len(partial_signatures)}")
    
    # Get the server IDs that participated in signing
    signing_indices = list(partial_signatures.keys())
    
    # Compute Lagrange coefficients for reconstruction at x=0
    lagrange_coeffs = {}
    for server_id in signing_indices:
        coeff = lagrange_coefficient(server_id, signing_indices)
        lagrange_coeffs[server_id] = coeff
        print(f"Server {server_id}: Lagrange coefficient = {coeff % 1000}")
    
    # Import at the top of the function to avoid repeated imports
    from py_ecc.bls.g2_primitives import signature_to_G2
    
    # Scale each partial signature by its Lagrange coefficient and aggregate
    combined_point = None
    
    for server_id, sig_bytes in partial_signatures.items():
        # Convert signature bytes to G2 point
        sig_point = signature_to_G2(sig_bytes)  # type: ignore
        
        # Scale by Lagrange coefficient
        scaled_sig_point = multiply(sig_point, lagrange_coeffs[server_id])
        
        # Add to combined signature
        if combined_point is None:
            combined_point = scaled_sig_point
        else:
            combined_point = add(combined_point, scaled_sig_point)
        
        print(f"Server {server_id}: scaled signature by coefficient {lagrange_coeffs[server_id] % 1000}")
    
    # Convert back to bytes - ensure combined_point is not None
    if combined_point is None:
        raise ValueError("No signatures to combine")
    combined_sig = G2_to_signature(combined_point)
    
    print(f"Threshold signature combination complete!")
    return combined_sig

# PEM utility functions for BLS12-381 keys
def encode_bls_private_key_pem(private_key_bytes: bytes) -> str:
    """Encode BLS12-381 private key bytes to PEM format."""
    b64_data = base64.b64encode(private_key_bytes).decode('ascii')
    # Split into 64-character lines
    lines = [b64_data[i:i+64] for i in range(0, len(b64_data), 64)]
    pem_content = '\n'.join(lines)
    return f"-----BEGIN BLS12381 PRIVATE KEY-----\n{pem_content}\n-----END BLS12381 PRIVATE KEY-----\n"

def decode_bls_private_key_pem(pem_data: str) -> bytes:
    """Decode BLS12-381 private key from PEM format to bytes."""
    # Remove PEM headers and whitespace
    lines = pem_data.strip().split('\n')
    b64_lines = []
    in_key = False
    
    for line in lines:
        line = line.strip()
        if line == "-----BEGIN BLS12381 PRIVATE KEY-----":
            in_key = True
            continue
        elif line == "-----END BLS12381 PRIVATE KEY-----":
            break
        elif in_key:
            b64_lines.append(line)
    
    b64_data = ''.join(b64_lines)
    return base64.b64decode(b64_data)

def encode_bls_public_key_pem(public_key_bytes: bytes) -> str:
    """Encode BLS12-381 public key bytes to PEM format."""
    b64_data = base64.b64encode(public_key_bytes).decode('ascii')
    # Split into 64-character lines
    lines = [b64_data[i:i+64] for i in range(0, len(b64_data), 64)]
    pem_content = '\n'.join(lines)
    return f"-----BEGIN BLS12381 PUBLIC KEY-----\n{pem_content}\n-----END BLS12381 PUBLIC KEY-----\n"

def main(n: int = DEFAULT_N, t: int = DEFAULT_T) -> None:
    """
    Main function demonstrating FOMC threshold signing.
    
    Args:
        n: Number of servers (default: 4)
        t: Threshold (default: 3)
    """
    # Set the threshold configuration
    set_threshold_config(n, t)
    config = get_threshold_config()
    
    print(f"Using configuration: {config}")
    
    # Generate threshold keys
    print("Generating FOMC threshold keys...")
    private_keys, public_keys, group_public_key = generate_threshold_keys()
    
    # Print keys
    print("\nServer Private and Public Keys:")
    for i in range(1, config.n+1):
        print(f"Server {i}:")
        print(f"  Private Key: {private_keys[i].hex()}")
        print(f"  Public Key: {public_keys[i].hex()}")
    
    print(f"\nGroup Public Key: {group_public_key.hex()}")
    
    # Example FOMC rate change to sign (25 basis points increase)
    abs_bps = 25
    is_increase = True
    bcs_message = create_bcs_message_for_fomc(abs_bps, is_increase)
    print(f"\nBCS message to sign: {abs_bps} bps {'increase' if is_increase else 'decrease'}")
    print(f"BCS bytes: {bcs_message.hex()}")
    
    # Test threshold signing with t out of n servers
    signing_servers = list(range(1, config.t + 1))  # Use first t servers
    print(f"\nTesting threshold signing with servers: {signing_servers}")
    
    # Generate partial signatures (each signer signs with their private key directly)
    partial_sigs = generate_threshold_signatures(private_keys, bcs_message, signing_servers, public_keys)
    
    # Combine partial signatures (apply Lagrange scaling to signatures)
    combined_threshold_sig = combine_threshold_signatures(partial_sigs)
    
    print(f"Combined Threshold Signature: {combined_threshold_sig.hex()}")
    
    # Verify the threshold signature against the group public key
    print(f"\n=== FOMC THRESHOLD SIGNATURE VERIFICATION ===")
    print(f"Verifying threshold signature against group public key...")
    
    threshold_valid = verify_signature(group_public_key, bcs_message, combined_threshold_sig)
    print(f"Threshold signature verification: {'SUCCESS!' if threshold_valid else 'FAILED'}")
    
    if threshold_valid:
        print(f"\n✅ FOMC THRESHOLD SIGNATURE WORKING CORRECTLY!")
        print(f"✅ Any {config.t} out of {config.n} servers can create a valid signature")
        print(f"✅ Signature verifies against the group public key")
        print(f"✅ No private key reconstruction needed for signature combination")
    else:
        print(f"\n❌ Threshold signature verification failed")

if __name__ == "__main__":
    import sys
    
    # Allow command line arguments to set N and T
    if len(sys.argv) == 3:
        try:
            n = int(sys.argv[1])
            t = int(sys.argv[2])
            main(n, t)
        except ValueError as e:
            print(f"Error: {e}")
            print("Usage: python threshold_signing.py [N] [T]")
            print("Example: python threshold_signing.py 7 5")
            print("Requirements: N >= 1, T >= 1, T <= N")
            sys.exit(1)
    else:
        # Use default configuration
        main()
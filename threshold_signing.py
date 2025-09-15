#!/usr/bin/env python3
"""
Threshold Signing with BLS12-381 for FOMC servers.

This module implements threshold signatures where any 3 out of 4 servers
can create a valid signature that verifies against a group public key.

Based on the threshold-ai-oracle implementation, this uses:
1. Shamir's Secret Sharing to distribute private key shares
2. Lagrange interpolation for threshold signature generation
3. BLS12-381 curve with py-ecc library
4. Aptos-compatible BCS message serialization
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

# FOMC threshold configuration: 4 servers, threshold = 3
N = 4  # Total number of servers
T = 3  # Threshold (need at least 3 servers to sign)

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
    Generate threshold keys for 4 FOMC servers with threshold = 3.
    
    This creates a master secret and distributes shares to 4 servers such that
    any 3 servers can reconstruct the master secret using Lagrange interpolation.
    
    Returns:
        private_keys: Dict mapping server ID to private key bytes (secret shares)
        public_keys: Dict mapping server ID to public key bytes
        group_public_key: The group public key bytes derived from master secret
    """
    print("\n=== FOMC THRESHOLD KEY GENERATION ===")
    print(f"Generating keys for {N} servers with threshold {T}")
    
    # Generate master secret
    master_secret = secrets.randbelow(curve_order)
    print(f"Generated master secret: {master_secret % 1000000}")  # Show last 6 digits
    
    # Generate polynomial of degree T-1 with master secret as constant term
    polynomial = generate_polynomial(T-1, master_secret)
    print(f"Polynomial coefficients (mod 1000000): {[c % 1000000 for c in polynomial]}")
    
    # Generate secret shares for each server using polynomial evaluation
    private_keys = {}
    public_keys = {}
    
    for server_id in range(1, N+1):
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
    test_indices = list(range(1, T+1))  # Use first T servers
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
    """Sign BCS-serialized message bytes using a private key."""
    # Hash BCS message to G2 point
    H = hash_to_G2(bcs_message, DST, hashlib.sha256)  # type: ignore
    
    # Convert private key to scalar
    private_key_scalar = int.from_bytes(private_key_bytes, 'big')
    
    # Sign: signature = private_key * H(bcs_message)
    signature_point = multiply(H, private_key_scalar)
    
    # Convert to compressed bytes (96 bytes)
    signature_bytes = G2_to_signature(signature_point)
    
    return signature_bytes

def verify_signature(public_key_bytes: bytes, bcs_message: bytes, signature_bytes: bytes) -> bool:
    """Verify a signature against a public key and BCS message bytes."""
    try:
        # Hash BCS message to G2 point
        H = hash_to_G2(bcs_message, DST, hashlib.sha256)  # type: ignore
        
        # Reconstruct public key point from bytes
        from py_ecc.bls.g2_primitives import pubkey_to_G1, signature_to_G2
        
        # Convert bytes to proper types
        public_key_point = pubkey_to_G1(public_key_bytes)  # type: ignore
        signature_point = signature_to_G2(signature_bytes)  # type: ignore
        
        # Verify: e(H(bcs_message), public_key) == e(signature, G1)
        return pairing(H, public_key_point) == pairing(signature_point, G1)
        
    except Exception as e:
        print(f"BCS verification error: {e}")
        return False

def generate_threshold_signatures(private_keys: Dict[int, bytes], bcs_message: bytes,
                                 indices: List[int]) -> Dict[int, bytes]:
    """
    Generate threshold signatures where each signer multiplies their secret share by λᵢ and signs once.
    
    This approach eliminates the need for private key knowledge during signature combination.
    Each signer computes their Lagrange coefficient and scales their secret accordingly.
    
    Args:
        private_keys: Dict mapping server ID to private key bytes (secret shares)
        bcs_message: The BCS-serialized message to sign
        indices: List of server IDs that will participate in signing
    
    Returns:
        Dict mapping server ID to threshold signature bytes
    """
    print(f"\n=== FOMC THRESHOLD SIGNATURE GENERATION ===")
    print(f"Generating threshold signatures from servers: {indices[:T]}")
    
    if len(indices) < T:
        raise ValueError(f"Need at least {T} signers, got {len(indices)}")
    
    # Use only the first T signers
    signing_indices = indices[:T]
    
    # Compute Lagrange coefficients for reconstruction at x=0
    lagrange_coeffs = []
    for server_id in signing_indices:
        coeff = lagrange_coefficient(server_id, signing_indices)
        lagrange_coeffs.append(coeff)
        print(f"Server {server_id}: Lagrange coefficient = {coeff % 1000}")
    
    # Each signer multiplies their secret share by λᵢ and signs
    threshold_signatures = {}
    
    for i, server_id in enumerate(signing_indices):
        # Get the private key scalar value
        private_key_scalar = int.from_bytes(private_keys[server_id], 'big')
        
        # Scale by Lagrange coefficient
        scaled_scalar = (lagrange_coeffs[i] * private_key_scalar) % curve_order
        
        # Create scaled private key and sign BCS message
        scaled_private_key_bytes = scaled_scalar.to_bytes(32, 'big')
        threshold_sig = sign_bcs_message(scaled_private_key_bytes, bcs_message)
        
        threshold_signatures[server_id] = threshold_sig
        print(f"Server {server_id}: scaled_scalar={scaled_scalar % 1000000}")
    
    print(f"Threshold signature generation complete!")
    return threshold_signatures

def combine_threshold_signatures(threshold_signatures: Dict[int, bytes]) -> bytes:
    """
    Combine threshold signatures by simple aggregation.
    
    Since each signature was already scaled by the appropriate Lagrange coefficient,
    we can simply aggregate them without needing access to private keys.
    
    Args:
        threshold_signatures: Dict mapping server ID to threshold signature bytes
    
    Returns:
        Combined threshold signature bytes
    """
    print(f"\n=== FOMC THRESHOLD SIGNATURE COMBINATION ===")
    print(f"Combining {len(threshold_signatures)} threshold signatures")
    
    if len(threshold_signatures) < T:
        raise ValueError(f"Need at least {T} threshold signatures, got {len(threshold_signatures)}")
    
    # Convert signatures to G2 points and aggregate
    combined_point = None
    
    # Import at the top of the function to avoid repeated imports
    from py_ecc.bls.g2_primitives import signature_to_G2
    
    for sig_bytes in threshold_signatures.values():
        # Convert signature bytes to G2 point
        sig_point = signature_to_G2(sig_bytes)  # type: ignore
        
        # Add to combined signature
        if combined_point is None:
            combined_point = sig_point
        else:
            combined_point = add(combined_point, sig_point)
    
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

def main() -> None:
    """Main function demonstrating FOMC threshold signing."""
    # Generate threshold keys
    print("Generating FOMC threshold keys...")
    private_keys, public_keys, group_public_key = generate_threshold_keys()
    
    # Print keys
    print("\nServer Private and Public Keys:")
    for i in range(1, N+1):
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
    
    # Test threshold signing with 3 out of 4 servers
    signing_servers = [1, 2, 3]  # Any 3 servers
    print(f"\nTesting threshold signing with servers: {signing_servers}")
    
    # Generate threshold signatures (each signer scales by Lagrange coefficient)
    threshold_sigs = generate_threshold_signatures(private_keys, bcs_message, signing_servers)
    
    # Combine threshold signatures (simple aggregation, no private keys needed)
    combined_threshold_sig = combine_threshold_signatures(threshold_sigs)
    
    print(f"Combined Threshold Signature: {combined_threshold_sig.hex()}")
    
    # Verify the threshold signature against the group public key
    print(f"\n=== FOMC THRESHOLD SIGNATURE VERIFICATION ===")
    print(f"Verifying threshold signature against group public key...")
    
    threshold_valid = verify_signature(group_public_key, bcs_message, combined_threshold_sig)
    print(f"Threshold signature verification: {'SUCCESS!' if threshold_valid else 'FAILED'}")
    
    if threshold_valid:
        print(f"\n✅ FOMC THRESHOLD SIGNATURE WORKING CORRECTLY!")
        print(f"✅ Any {T} out of {N} servers can create a valid signature")
        print(f"✅ Signature verifies against the group public key")
        print(f"✅ No private key reconstruction needed for signature combination")
    else:
        print(f"\n❌ Threshold signature verification failed")

if __name__ == "__main__":
    main()
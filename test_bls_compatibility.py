#!/usr/bin/env python3
"""
Test BLS compatibility between our threshold signing and the original integration test approach.
"""

from py_ecc.bls.ciphersuites import G2ProofOfPossession as bls
from threshold_signing import create_bcs_message_for_fomc, sign_bcs_message, verify_signature
import secrets

def test_single_signature_compatibility():
    """Test that our BLS signing is compatible with py_ecc BLS."""
    print("=== Testing BLS Signature Compatibility ===")
    
    # Generate a test private key (must be in valid BLS range)
    from py_ecc.optimized_bls12_381.optimized_curve import curve_order
    private_key_scalar = secrets.randbelow(curve_order)
    private_key_bytes = private_key_scalar.to_bytes(32, 'big')
    
    # Generate public key using py_ecc
    public_key_point = bls.SkToPk(private_key_scalar)
    public_key_bytes = bytes(public_key_point)
    
    # Create test message
    abs_bps = 25
    is_increase = True
    bcs_message = create_bcs_message_for_fomc(abs_bps, is_increase)
    
    print(f"Private key: {private_key_bytes.hex()[:32]}...")
    print(f"Public key: {public_key_bytes.hex()[:32]}...")
    print(f"BCS message: {bcs_message.hex()}")
    
    # Sign using our implementation
    our_signature = sign_bcs_message(private_key_bytes, bcs_message)
    print(f"Our signature: {our_signature.hex()[:32]}...")
    
    # Sign using py_ecc directly
    py_ecc_signature = bls.Sign(private_key_scalar, bcs_message)
    py_ecc_signature_bytes = bytes(py_ecc_signature)
    print(f"py_ecc signature: {py_ecc_signature_bytes.hex()[:32]}...")
    
    # Verify our signature using our verification
    our_verify_result = verify_signature(public_key_bytes, bcs_message, our_signature)
    print(f"Our signature verified by our function: {our_verify_result}")
    
    # Verify py_ecc signature using our verification
    py_ecc_verify_result = verify_signature(public_key_bytes, bcs_message, py_ecc_signature_bytes)
    print(f"py_ecc signature verified by our function: {py_ecc_verify_result}")
    
    # Test direct py_ecc verification for comparison
    print(f"\n=== DIRECT PY_ECC VERIFICATION TEST ===")
    try:
        # Direct verification using py_ecc with public key point and signature point
        direct_verify_result = bls.Verify(public_key_point, bcs_message, py_ecc_signature)
        print(f"Direct py_ecc verification (pubkey_point, message, sig_point): {direct_verify_result}")
        
        # Also test with bytes directly (should fail but let's see the error)
        try:
            direct_verify_bytes = bls.Verify(public_key_bytes, bcs_message, py_ecc_signature_bytes)
            print(f"Direct py_ecc verification (pubkey_bytes, message, sig_bytes): {direct_verify_bytes}")
        except Exception as e2:
            print(f"Direct py_ecc verification with bytes failed (expected): {e2}")
        
    except Exception as e:
        print(f"Direct py_ecc verification error: {e}")
    
    # Check if signatures are identical
    signatures_match = our_signature == py_ecc_signature_bytes
    print(f"Signatures match: {signatures_match}")
    
    return our_verify_result and py_ecc_verify_result

if __name__ == "__main__":
    success = test_single_signature_compatibility()
    if success:
        print("\n✅ BLS compatibility test PASSED")
    else:
        print("\n❌ BLS compatibility test FAILED")
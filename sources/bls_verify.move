module fomc_rates::bls_verify {
    use aptos_std::bls12381;

    /// Error codes
    const EINVALID_SIGNATURE: u64 = 1;

    /// Verifies the BLS12-381 signature. Returns true for convenience in view calls.
    public fun verify(message: vector<u8>, signature: vector<u8>, public_key: vector<u8>): bool {
        bls12381::verify(message, signature, public_key)
    }

    /// Entry function that aborts if verification fails. Succeeds otherwise.
    public entry fun verify_entry(_account: &signer, message: vector<u8>, signature: vector<u8>, public_key: vector<u8>) {
        let ok = bls12381::verify(message, signature, public_key);
        assert!(ok, EINVALID_SIGNATURE);
    }
}


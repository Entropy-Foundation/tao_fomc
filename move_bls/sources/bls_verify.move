module bls_signer::bls_verify {
    use aptos_std::bls12381;
    use std::option;

    const EINVALID_PUBKEY: u64 = 1;
    const EVERIFY_FAILED: u64 = 2;

    /// View helper: verify a normal BLS signature (G2-proof-of-possession ciphersuite).
    public fun verify(message: vector<u8>, signature: vector<u8>, public_key: vector<u8>): bool {
        let pk_opt = bls12381::public_key_from_bytes(public_key);
        if (option::is_some(&pk_opt)) {
            let pk = option::extract(&mut pk_opt);
            let sig = bls12381::signature_from_bytes(signature);
            bls12381::verify_normal_signature(&sig, &pk, message)
        } else {
            false
        }
    }

    /// Entry: aborts if verification fails.
    public entry fun verify_entry(_account: &signer, message: vector<u8>, signature: vector<u8>, public_key: vector<u8>) {
        let pk_opt = bls12381::public_key_from_bytes(public_key);
        assert!(option::is_some(&pk_opt), EINVALID_PUBKEY);
        let pk = option::extract(&mut pk_opt);
        let sig = bls12381::signature_from_bytes(signature);
        let ok = bls12381::verify_normal_signature(&sig, &pk, message);
        assert!(ok, EVERIFY_FAILED);
    }
}


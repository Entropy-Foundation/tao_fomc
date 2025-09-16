#[test_only]
module fomc_rates::test_interest_rate {
    use std::signer;
    use std::vector;
    use aptos_framework::timestamp;
    use fomc_rates::interest_rate;

    #[test(
        aptos_framework = @0x1,
        // Set the package named address and provide matching signer for admin
        fomc_rates = @0x42,
        admin = @0x42
    )]
    fun test_admin_can_set_bls_key(aptos_framework: &signer, admin: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);

        let k = vector::empty<u8>();
        vector::push_back(&mut k, 0u8);
        vector::push_back(&mut k, 0u8);
        vector::push_back(&mut k, 0u8);
        interest_rate::set_bls_public_key(admin, k);

        assert!(interest_rate::has_bls_public_key(), 100);
        assert!(interest_rate::bls_public_key_len() == 3, 101);
    }

    #[test(
        aptos_framework = @0x1,
        fomc_rates = @0x42,
        user = @0xB0B
    )]
    #[expected_failure(abort_code = 2001, location = fomc_rates::interest_rate)]
    fun test_non_admin_cannot_set_bls_key(aptos_framework: &signer, user: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);
        let k = vector::empty<u8>();
        vector::push_back(&mut k, 0u8);
        vector::push_back(&mut k, 0u8);
        // Should abort with ENOT_ADMIN (2001)
        interest_rate::set_bls_public_key(user, k);
    }

    #[test(
        aptos_framework = @0x1,
        fomc_rates = @0x42,
        admin = @0x42
    )]
    fun test_admin_can_update_bls_key(aptos_framework: &signer, admin: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);
        let k1 = vector::empty<u8>();
        vector::push_back(&mut k1, 0u8);
        vector::push_back(&mut k1, 0u8);
        interest_rate::set_bls_public_key(admin, k1);
        assert!(interest_rate::bls_public_key_len() == 2, 102);

        let k2 = vector::empty<u8>();
        vector::push_back(&mut k2, 0u8);
        vector::push_back(&mut k2, 0u8);
        vector::push_back(&mut k2, 0u8);
        vector::push_back(&mut k2, 0u8);
        vector::push_back(&mut k2, 0u8);
        interest_rate::set_bls_public_key(admin, k2);
        assert!(interest_rate::bls_public_key_len() == 5, 103);
    }
}

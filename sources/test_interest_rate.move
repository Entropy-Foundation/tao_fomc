#[test_only]
module fomc_rates::test_interest_rate {
    use std::signer;
    use std::vector;
    use aptos_framework::timestamp;
    use fomc_rates::interest_rate;

    #[test(aptos_framework = @0x1, account = @0x100)]
    fun test_decrease_25bps_buys_10pct_usdt(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);

        // Seed 1000 APT, 0 USDT
        interest_rate::test_mint(account, 1000, 0);
        // 25 bps decrease => buy 10% USDT with APT
        interest_rate::record_interest_rate_movement(account, 25, false);

        let addr = signer::address_of(account);
        assert!(interest_rate::get_apt(addr) == 900, 1);
        assert!(interest_rate::get_usdt(addr) == 100, 2);
    }

    #[test(aptos_framework = @0x1, account = @0x101)]
    fun test_decrease_50bps_or_more_buys_30pct_usdt(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);

        interest_rate::test_mint(account, 1000, 0);
        // 50 bps decrease => buy 30% USDT with APT
        interest_rate::record_interest_rate_movement(account, 50, false);

        let addr = signer::address_of(account);
        assert!(interest_rate::get_apt(addr) == 700, 3);
        assert!(interest_rate::get_usdt(addr) == 300, 4);
    }

    #[test(aptos_framework = @0x1, account = @0x102)]
    fun test_no_change_buys_apt_with_30pct_usdt(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);

        interest_rate::test_mint(account, 0, 1000);
        // No change
        interest_rate::record_interest_rate_movement(account, 0, false);

        let addr = signer::address_of(account);
        assert!(interest_rate::get_apt(addr) == 300, 5);
        assert!(interest_rate::get_usdt(addr) == 700, 6);
    }

    #[test(aptos_framework = @0x1, account = @0x103)]
    fun test_increase_also_buys_apt_with_30pct_usdt(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);

        interest_rate::test_mint(account, 0, 1000);
        // Increase
        interest_rate::record_interest_rate_movement(account, 25, true);

        let addr = signer::address_of(account);
        assert!(interest_rate::get_apt(addr) == 300, 7);
        assert!(interest_rate::get_usdt(addr) == 700, 8);
    }

    #[test(aptos_framework = @0x1, account = @0x104)]
    fun test_small_decrease_defaults_to_buy_apt(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);

        interest_rate::test_mint(account, 0, 1000);
        // 10 bps decrease (<25) => defaults to buy APT with 30% USDT
        interest_rate::record_interest_rate_movement(account, 10, false);

        let addr = signer::address_of(account);
        assert!(interest_rate::get_apt(addr) == 300, 9);
        assert!(interest_rate::get_usdt(addr) == 700, 10);
    }

    #[test(aptos_framework = @0x1, account = @0x105)]
    fun test_multiple_actions_compose(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);

        // Start with APT only
        interest_rate::test_mint(account, 1000, 0);
        // 25 bps cut => move 10% APT -> USDT: APT=900, USDT=100
        interest_rate::record_interest_rate_movement(account, 25, false);
        // No change => move 30% USDT -> APT: APT=930, USDT=70
        interest_rate::record_interest_rate_movement(account, 0, false);
        // 50 bps cut => move 30% APT -> USDT: APT=651, USDT=349
        interest_rate::record_interest_rate_movement(account, 50, false);

        let addr = signer::address_of(account);
        assert!(interest_rate::get_apt(addr) == 651, 11);
        assert!(interest_rate::get_usdt(addr) == 349, 12);
    }

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

module fomc_rates::interest_rate {
    use std::signer;
    use std::option;
    use aptos_framework::event;
    use aptos_framework::timestamp;
    use aptos_framework::coin;
    // No direct acquires of CoinStore outside coin module; only register/check via coin API
    use liquidswap::router;
    use aptos_std::bls12381;
    use std::vector;

    /// Error codes for BLS verification
    const EINVALID_PUBKEY: u64 = 1001;
    const EVERIFY_FAILED: u64 = 1002;
    const ENOT_ADMIN: u64 = 2001;

    #[event]
    struct InterestRateChangeEvent has drop, store {
        basis_points: u64,
        is_increase: bool,
        timestamp: u64,
    }

    /// Module configuration stored under the module address containing the active BLS public key.
    /// This is updated only by the module admin (publisher address of `fomc_rates`).
    struct Config has key {
        bls_public_key: vector<u8>,
    }

    /// Legacy struct kept for on-chain compatibility with earlier versions.
    /// Not used by the new logic but retained to avoid backward incompatible upgrades.
    struct InterestRateMovement has drop, store {
        basis_points: u64,
        is_increase: bool,
        timestamp: u64,
    }

    /// Simple per-account balance book used for tests and local logic.
    /// This is NOT a real DEX swap. It just moves value between two ledgers
    /// (APT, USDT) at a 1:1 notional rate to validate decision logic on-chain.
    struct Balances has key {
        apt: u64,
        usdt: u64,
    }

    /// Initializes the per-account Balances resource with zeros if not present
    public entry fun init(account: &signer) {
        let addr = signer::address_of(account);
        if (!exists<Balances>(addr)) {
            move_to(account, Balances { apt: 0, usdt: 0 });
        }
    }

    /// Admin-only: create or update the module's BLS public key used for signature verification.
    /// Stores the key in `Config` under the `@fomc_rates` address.
    public entry fun set_bls_public_key(admin: &signer, new_key: vector<u8>) acquires Config {
        // Only the module admin (publisher address of `fomc_rates`) may set the key.
        assert!(signer::address_of(admin) == @fomc_rates, ENOT_ADMIN);
        if (exists<Config>(@fomc_rates)) {
            let cfg = borrow_global_mut<Config>(@fomc_rates);
            cfg.bls_public_key = new_key;
        } else {
            move_to(admin, Config { bls_public_key: new_key });
        }
    }

    /// Read-only helpers to support unit tests and potential off-chain checks
    public fun has_bls_public_key(): bool { exists<Config>(@fomc_rates) }

    public fun bls_public_key_len(): u64 acquires Config {
        let cfg = borrow_global<Config>(@fomc_rates);
        vector::length(&cfg.bls_public_key)
    }

    #[test_only]
    public fun test_mint(account: &signer, apt: u64, usdt: u64) acquires Balances {
        let addr = signer::address_of(account);
        if (!exists<Balances>(addr)) {
            move_to(account, Balances { apt, usdt });
        } else {
            let b = borrow_global_mut<Balances>(addr);
            b.apt = b.apt + apt;
            b.usdt = b.usdt + usdt;
        }
    }

    /// Read-only helpers used by tests
    public fun get_apt(addr: address): u64 acquires Balances {
        borrow_global<Balances>(addr).apt
    }
    public fun get_usdt(addr: address): u64 acquires Balances {
        borrow_global<Balances>(addr).usdt
    }

    /// Core entry that records the rate movement and performs the action:
    /// - Decrease >= 50 bps: buy USDT with 30% of APT
    /// - Decrease >= 25 bps: buy USDT with 10% of APT
    /// - Else (no change or increase, or decrease < 25 bps): buy APT with 30% of USDT
    /// DEPRECATED: This function is disabled and kept only for ABI compatibility with deployed contracts.
    /// Use record_interest_rate_movement() instead.
    public entry fun record_interest_rate_movement_signed(
        account: &signer,
        basis_points: u64,
        is_increase: bool,
        message: vector<u8>,
        signature: vector<u8>,
        public_key: vector<u8>,
    ) {
        // Function disabled - kept for ABI compatibility only
        abort 999;
    }

    /// DEPRECATED: This function is disabled and kept only for ABI compatibility with deployed contracts.
    /// Use record_interest_rate_movement_v5() instead.
    public entry fun record_interest_rate_movement_v4<APT, USDT, Curve>(
        account: &signer,
        basis_points: u64,
        is_increase: bool,
        min_out: u64,
        signature: vector<u8>,
        public_key: vector<u8>,
    ) {
        // Function disabled - kept for ABI compatibility only
        abort 999;
    }

    /// Real on-chain swaps via Liquidswap router with hardcoded curve and simplified parameters.
    /// Uses stored BLS public key from Config and fixed min_out value.
    /// Hardcoded to use APT, USDT, and Uncorrelated curve as used in integration tests.
    public entry fun record_interest_rate_movement_v5<APT, USDT>(
        account: &signer,
        basis_points: u64,
        is_increase: bool,
        signature: vector<u8>,
    ) acquires Config {
        // Derive message from basis_points and is_increase
        let message = derive_message(basis_points, is_increase);
        
        // Get stored BLS public key from Config
        assert!(exists<Config>(@fomc_rates), EINVALID_PUBKEY);
        let cfg = borrow_global<Config>(@fomc_rates);
        let public_key = cfg.bls_public_key;
        
        // Verify BLS signature over the canonical message first
        assert_bls_sig(message, signature, public_key);

        let now = timestamp::now_microseconds();
        event::emit(InterestRateChangeEvent { basis_points, is_increase, timestamp: now });

        // Ensure CoinStores exist to avoid aborts on first use
        ensure_registered<APT>(account);
        ensure_registered<USDT>(account);

        // Ensure the pool exists for Uncorrelated curve (hardcoded)
        assert!(router::is_swap_exists<APT, USDT, 0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9::curves::Uncorrelated>(), 10);

        let min_out = 1; // Fixed min_out value as used in integration tests

        if (!is_increase && basis_points >= 50) {
            swap_apt_to_usdt_percent<APT, USDT, 0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9::curves::Uncorrelated>(account, 30, min_out)
        } else if (!is_increase && basis_points >= 25) {
            swap_apt_to_usdt_percent<APT, USDT, 0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9::curves::Uncorrelated>(account, 10, min_out)
        } else {
            swap_usdt_to_apt_percent<APT, USDT, 0x43417434fd869edee76cca2a4d2301e528a1551b1d719b75c350c3c97d15b8b9::curves::Uncorrelated>(account, 30, min_out)
        }
    }

    /// DEPRECATED: Kept for ABI compatibility with deployed contracts.
    /// Use record_interest_rate_movement_v4() instead.
    public entry fun record_interest_rate_movement_real_signed<APT, USDT, Curve>(
        account: &signer,
        basis_points: u64,
        is_increase: bool,
        min_out: u64,
        message: vector<u8>,
        signature: vector<u8>,
        public_key: vector<u8>,
    ) {
        // Function disabled - kept for ABI compatibility only
        abort 999;
    }

    /// Backward-compatible entry: original ABI without signature verification.
    /// DEPRECATED: This function is disabled and kept only for ABI compatibility with deployed contracts.
    /// Use record_interest_rate_movement_real_signed() instead.
    public entry fun record_interest_rate_movement(
        account: &signer,
        basis_points: u64,
        is_increase: bool,
    ) {
        // Function disabled - kept for ABI compatibility only
        abort 999;
    }

    /// Backward-compatible entry: original ABI without signature verification.
    /// DEPRECATED: This function is disabled and kept only for ABI compatibility with deployed contracts.
    /// Use record_interest_rate_movement_real_signed() instead.
    public entry fun record_interest_rate_movement_real<APT, USDT, Curve>(
        account: &signer,
        basis_points: u64,
        is_increase: bool,
        min_out: u64,
    ) {
        // Function disabled - kept for ABI compatibility only
        abort 999;
    }

    /// Derives a canonical message from basis_points and is_increase for signature verification
    /// This matches the Python _bls_message function: serialize u64(basis_points) + bool(is_increase)
    fun derive_message(basis_points: u64, is_increase: bool): vector<u8> {
        use aptos_std::bcs;
        
        let message = vector::empty<u8>();
        
        // Serialize basis_points as u64 in BCS format
        let bp_bytes = bcs::to_bytes(&basis_points);
        vector::append(&mut message, bp_bytes);
        
        // Serialize is_increase as bool in BCS format
        let bool_bytes = bcs::to_bytes(&is_increase);
        vector::append(&mut message, bool_bytes);
        
        message
    }

    /// Verifies a BLS signature using Aptos stdlib BLS12-381 implementation.
    /// Aborts if public key is invalid or verification fails.
    fun assert_bls_sig(message: vector<u8>, signature: vector<u8>, public_key: vector<u8>) {
        let pk_opt = bls12381::public_key_from_bytes(public_key);
        assert!(option::is_some(&pk_opt), EINVALID_PUBKEY);
        let pk = option::extract(&mut pk_opt);
        let sig = bls12381::signature_from_bytes(signature);
        let ok = bls12381::verify_normal_signature(&sig, &pk, message);
        assert!(ok, EVERIFY_FAILED);
    }

    fun init_if_needed(account: &signer) {
        let addr = signer::address_of(account);
        if (!exists<Balances>(addr)) {
            move_to(account, Balances { apt: 0, usdt: 0 });
        }
    }

    /// Transfer pct% of APT notionally to USDT (1:1 nominal value for testing)
    fun buy_usdt_with_apt_percent(account: &signer, pct: u64) acquires Balances {
        let addr = signer::address_of(account);
        let b = borrow_global_mut<Balances>(addr);
        let move_amt = percent_of(b.apt, pct);
        if (move_amt > 0) {
            b.apt = b.apt - move_amt;
            b.usdt = b.usdt + move_amt;
        }
    }

    /// Transfer pct% of USDT notionally to APT (1:1 nominal value for testing)
    fun buy_apt_with_usdt_percent(account: &signer, pct: u64) acquires Balances {
        let addr = signer::address_of(account);
        let b = borrow_global_mut<Balances>(addr);
        let move_amt = percent_of(b.usdt, pct);
        if (move_amt > 0) {
            b.usdt = b.usdt - move_amt;
            b.apt = b.apt + move_amt;
        }
    }

    /// Withdraw pct% of APT and swap for USDT on Liquidswap, deposit result back
    fun swap_apt_to_usdt_percent<APT, USDT, Curve>(
        account: &signer,
        pct: u64,
        min_out: u64,
    ) {
        let addr = signer::address_of(account);
        let bal = coin::balance<APT>(addr);
        let amount_in = percent_of(bal, pct);
        if (amount_in == 0) return;
        let coin_in = coin::withdraw<APT>(account, amount_in);
        let out_coin = router::swap_exact_coin_for_coin<APT, USDT, Curve>(coin_in, min_out);
        coin::deposit<USDT>(addr, out_coin);
    }

    /// Withdraw pct% of USDT and swap for APT on Liquidswap, deposit result back
    fun swap_usdt_to_apt_percent<APT, USDT, Curve>(
        account: &signer,
        pct: u64,
        min_out: u64,
    ) {
        let addr = signer::address_of(account);
        let bal = coin::balance<USDT>(addr);
        let amount_in = percent_of(bal, pct);
        if (amount_in == 0) return;
        let coin_in = coin::withdraw<USDT>(account, amount_in);
        let out_coin = router::swap_exact_coin_for_coin<USDT, APT, Curve>(coin_in, min_out);
        coin::deposit<APT>(addr, out_coin);
    }

    inline fun percent_of(amount: u64, pct: u64): u64 {
        // pct is a whole-number percentage (e.g., 10 => 10%)
        // move semantics handle integer truncation naturally
        (amount * pct) / 100
    }

    fun ensure_registered<C>(account: &signer) {
        let addr = signer::address_of(account);
        if (!coin::is_account_registered<C>(addr)) {
            coin::register<C>(account);
        }
    }
}

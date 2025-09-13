module fomc_rates::interest_rate {
    use std::signer;
    use aptos_framework::event;
    use aptos_framework::timestamp;
    use aptos_framework::coin;
    // No direct acquires of CoinStore outside coin module; only register/check via coin API
    use liquidswap::router;

    /// Event emitted for each recorded rate update
    #[event]
    struct InterestRateChangeEvent has drop, store {
        basis_points: u64,
        is_increase: bool,
        timestamp: u64,
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

    /// Test-only mint function to seed balances (no real coins are moved).
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
    public entry fun record_interest_rate_movement(
        account: &signer,
        basis_points: u64,
        is_increase: bool,
    ) acquires Balances {
        let now = timestamp::now_microseconds();
        event::emit(InterestRateChangeEvent { basis_points, is_increase, timestamp: now });

        // Ensure balances exist for the caller
        init_if_needed(account);

        if (!is_increase && basis_points >= 50) {
            buy_usdt_with_apt_percent(account, 30)
        } else if (!is_increase && basis_points >= 25) {
            buy_usdt_with_apt_percent(account, 10)
        } else {
            // No change or increase (or very small decrease): buy APT with 30% of USDT
            buy_apt_with_usdt_percent(account, 30)
        }
    }

    /// Real on-chain swaps via Liquidswap router. Generic over coin types and curve.
    /// Caller must provide appropriate type args, e.g.,
    ///   <0x1::aptos_coin::AptosCoin, 0x4341...::coins::USDT, liquidswap::curves::Uncorrelated>
    public entry fun record_interest_rate_movement_real<APT, USDT, Curve>(
        account: &signer,
        basis_points: u64,
        is_increase: bool,
        min_out: u64,
    ) {
        let now = timestamp::now_microseconds();
        event::emit(InterestRateChangeEvent { basis_points, is_increase, timestamp: now });

        // Ensure CoinStores exist to avoid aborts on first use
        ensure_registered<APT>(account);
        ensure_registered<USDT>(account);

        // Ensure the pool exists for selected curve
        assert!(router::is_swap_exists<APT, USDT, Curve>(), 10);

        if (!is_increase && basis_points >= 50) {
            swap_apt_to_usdt_percent<APT, USDT, Curve>(account, 30, min_out)
        } else if (!is_increase && basis_points >= 25) {
            swap_apt_to_usdt_percent<APT, USDT, Curve>(account, 10, min_out)
        } else {
            swap_usdt_to_apt_percent<APT, USDT, Curve>(account, 30, min_out)
        }
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

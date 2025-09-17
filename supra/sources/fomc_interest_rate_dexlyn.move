module fin_triggers::fomc_interest_rate_dexlyn {
    use std::signer;
    use std::option;
    use std::vector;
    use aptos_std::bcs;
    use aptos_std::bls12381;
    use dexlyn_swap::router;
    use supra_framework::coin;
    use supra_framework::event;
    use supra_framework::supra_account;
    use supra_framework::timestamp;

    /// Error codes for BLS verification and admin gating
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
    struct Config has key {
        bls_public_key: vector<u8>,
    }

    /// Initializes the per-account Balances resource with zeros if not present.
    /// This mirrors the legacy helper in the Liquidswap implementation and is useful for tests.
    struct Balances has key {
        apt: u64,
        usdt: u64,
    }

    /// Initializes the Balances resource for local accounting tests.
    public entry fun init(account: &signer) {
        let addr = signer::address_of(account);
        if (!exists<Balances>(addr)) {
            move_to(account, Balances { apt: 0, usdt: 0 });
        }
    }

    /// Admin-only: create or update the module's BLS public key used for signature verification.
    /// Stores the key in `Config` under the module address (`@fin_triggers`).
    public entry fun set_bls_public_key(admin: &signer, new_key: vector<u8>) acquires Config {
        assert!(signer::address_of(admin) == @fin_triggers, ENOT_ADMIN);
        if (exists<Config>(@fin_triggers)) {
            let cfg = borrow_global_mut<Config>(@fin_triggers);
            cfg.bls_public_key = new_key;
        } else {
            move_to(admin, Config { bls_public_key: new_key });
        }
    }

    /// Read-only helpers to support unit tests and potential off-chain checks.
    public fun has_bls_public_key(): bool { exists<Config>(@fin_triggers) }

    public fun bls_public_key_len(): u64 acquires Config {
        let cfg = borrow_global<Config>(@fin_triggers);
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

    /// Read-only helpers used by tests.
    public fun get_apt(addr: address): u64 acquires Balances {
        borrow_global<Balances>(addr).apt
    }

    public fun get_usdt(addr: address): u64 acquires Balances {
        borrow_global<Balances>(addr).usdt
    }

    /// Main entry point that records the rate movement and performs trades on DexLyn.
    /// The decision tree matches the Liquidswap implementation but routes swaps through DexLyn's router.
    public entry fun record_interest_rate_movement_dexlyn<APT, USDT, Curve>(
        account: &signer,
        basis_points: u64,
        is_increase: bool,
        signature: vector<u8>,
    ) acquires Config {
        let message = derive_message(basis_points, is_increase);

        assert!(exists<Config>(@fin_triggers), EINVALID_PUBKEY);
        let cfg = borrow_global<Config>(@fin_triggers);
        let public_key = cfg.bls_public_key;

        assert_bls_sig(message, signature, public_key);

        let now = timestamp::now_microseconds();
        event::emit(InterestRateChangeEvent { basis_points, is_increase, timestamp: now });

        ensure_registered<APT>(account);
        ensure_registered<USDT>(account);

        assert!(router::is_swap_exists<APT, USDT, Curve>(), 10);

        let min_out = 1;

        if (!is_increase && basis_points >= 50) {
            swap_apt_to_usdt_percent<APT, USDT, Curve>(account, 30, min_out)
        } else if (!is_increase && basis_points >= 25) {
            swap_apt_to_usdt_percent<APT, USDT, Curve>(account, 10, min_out)
        } else {
            swap_usdt_to_apt_percent<APT, USDT, Curve>(account, 30, min_out)
        }
    }

    /// Derives a canonical message from `basis_points` and `is_increase` for signature verification.
    fun derive_message(basis_points: u64, is_increase: bool): vector<u8> {
        let message = vector::empty<u8>();

        let bp_bytes = bcs::to_bytes(&basis_points);
        vector::append(&mut message, bp_bytes);

        let bool_bytes = bcs::to_bytes(&is_increase);
        vector::append(&mut message, bool_bytes);

        message
    }

    /// Verifies a BLS signature using Aptos stdlib BLS12-381 implementation.
    fun assert_bls_sig(message: vector<u8>, signature: vector<u8>, public_key: vector<u8>) {
        let pk_opt = bls12381::public_key_from_bytes(public_key);
        assert!(option::is_some(&pk_opt), EINVALID_PUBKEY);
        let pk = option::extract(&mut pk_opt);
        let sig = bls12381::signature_from_bytes(signature);
        let ok = bls12381::verify_normal_signature(&sig, &pk, message);
        assert!(ok, EVERIFY_FAILED);
    }

    /// Withdraw `pct` percent of APT balance and swap for USDT on DexLyn, depositing the result back.
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
        supra_account::deposit_coins<USDT>(addr, out_coin);
    }

    /// Withdraw `pct` percent of USDT balance and swap for APT on DexLyn, depositing the result back.
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
        supra_account::deposit_coins<APT>(addr, out_coin);
    }

    inline fun percent_of(amount: u64, pct: u64): u64 {
        (amount * pct) / 100
    }

    fun ensure_registered<C>(account: &signer) {
        let addr = signer::address_of(account);
        if (!coin::is_account_registered<C>(addr)) {
            coin::register<C>(account);
        }
    }
}

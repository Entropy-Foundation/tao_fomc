module fomc_rates::interest_rate {
    use aptos_framework::event;

    struct InterestRateMovement has drop, store {
        basis_points: u64,
        is_increase: bool,
        timestamp: u64,
    }

    #[event]
    struct InterestRateChangeEvent has drop, store {
        basis_points: u64,
        is_increase: bool,
        timestamp: u64,
    }

    public entry fun record_interest_rate_movement(
        _account: &signer,
        basis_points: u64,
        is_increase: bool
    ) {
        let timestamp = aptos_framework::timestamp::now_microseconds();
        
        event::emit(InterestRateChangeEvent {
            basis_points,
            is_increase,
            timestamp,
        });
    }
}
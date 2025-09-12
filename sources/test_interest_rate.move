#[test_only]
module fomc_rates::test_interest_rate {
    use fomc_rates::interest_rate;
    use aptos_framework::timestamp;

    #[test(aptos_framework = @0x1, account = @0x100)]
    fun test_interest_rate_increase(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);
        
        // Test that the function executes without error for rate increase
        interest_rate::record_interest_rate_movement(account, 25, true);
    }

    #[test(aptos_framework = @0x1, account = @0x100)]
    fun test_interest_rate_decrease(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);
        
        // Test that the function executes without error for rate decrease
        interest_rate::record_interest_rate_movement(account, 50, false);
    }

    #[test(aptos_framework = @0x1, account = @0x100)]
    fun test_zero_basis_points_increase(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);
        
        // Test that the function handles zero basis points for increase
        interest_rate::record_interest_rate_movement(account, 0, true);
    }

    #[test(aptos_framework = @0x1, account = @0x100)]
    fun test_zero_basis_points_decrease(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);
        
        // Test that the function handles zero basis points for decrease
        interest_rate::record_interest_rate_movement(account, 0, false);
    }

    #[test(aptos_framework = @0x1, account = @0x100)]
    fun test_large_basis_points_change(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);
        
        // Test that the function handles large basis point changes
        interest_rate::record_interest_rate_movement(account, 1000, false);
    }

    #[test(aptos_framework = @0x1, account = @0x100)]
    fun test_multiple_rate_changes(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);
        
        // Test that multiple calls work correctly
        interest_rate::record_interest_rate_movement(account, 25, true);
        interest_rate::record_interest_rate_movement(account, 50, false);
        interest_rate::record_interest_rate_movement(account, 75, true);
    }

    #[test(aptos_framework = @0x1, account = @0x100)]
    fun test_typical_fomc_scenarios(aptos_framework: &signer, account: &signer) {
        timestamp::set_time_has_started_for_testing(aptos_framework);
        
        // Test typical FOMC rate changes
        interest_rate::record_interest_rate_movement(account, 25, false);  // 0.25% cut
        interest_rate::record_interest_rate_movement(account, 50, false);  // 0.50% cut  
        interest_rate::record_interest_rate_movement(account, 75, true);   // 0.75% hike
    }
}
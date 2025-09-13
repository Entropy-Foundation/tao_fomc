TAO FOMC Submission Tools

This project uses the Aptos Python SDK to submit detected FOMC interest rate changes to a deployed Move module.

Quick Start

- Install dependencies only (no package install):
  - `poetry install --no-root`
  - Run directly:
    - `poetry run python aptos_rate_submitter.py "Fed cuts rates by 1 basis points"`
    - `poetry run python verify_tx.py <TX_HASH>`

- Install the project (registers console scripts):
  - `poetry install`
  - Submit: `poetry run fomc-submit "Fed cuts rates by 1 basis points"`
  - Verify: `poetry run fomc-verify <TX_HASH>`

The submitter reads `.aptos/config.yaml` for your key and `rest_url`, and resolves the deployed module address from `deploy_logs/compile.log` or `Move.toml`.

Integration Test (Real Swaps)

- Ensure Liquidswap pool exists for APT/USDT Uncorrelated on testnet and your account has balances.
- Run end-to-end integration that:
  - Parses text or URL for rate change
  - Calls `record_interest_rate_movement_real` to execute on-chain swap per policy
  - Prints pre/post balances and deltas

Commands:
- `poetry run python integration_test.py "Fed cuts rates by 50 basis points"`
- `poetry run python integration_test.py https://news.example/fed-cuts` 

Env overrides:
- `APTOS_REST_URL`, `APT_TYPE`, `USDT_TYPE`, `CURVE_TYPE`

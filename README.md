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

Environment

- Copy `env.template` to `.env` and fill in values (at minimum `BLS_PRIVATE_KEY`; optional overrides like `APTOS_REST_URL`, `APT_TYPE`, `USDT_TYPE`, `CURVE_TYPE`). `.env` is already git-ignored.

Automatic Trading

- **Policy:** Executes swaps based on the reported rate change.
  - Decrease ≥ 50 bps: buy USDT with 30% of APT.
  - Decrease ≥ 25 bps: buy USDT with 10% of APT.
  - Otherwise (no change, increase, or small cut): buy APT with 30% of USDT.
- **Real swaps:** `record_interest_rate_movement_real_signed<APT, USDT, Curve>` routes through Liquidswap; pools must exist and accounts must be registered for both coins.
- **Test mode:** `record_interest_rate_movement_signed` uses an internal ledger for validation (no DEX swap).

BLS Verification

- **Signed calls:** The Python submitter uses `record_interest_rate_movement_signed` / `record_interest_rate_movement_real_signed` by default.
- **Canonical message:** BCS-encoded `(u64 basis_points_abs, bool is_increase)` is signed with `py_ecc` (BLS12-381 G2 PoP).
- **On-chain check:** The Move module verifies `message`, `signature`, and `public_key` using Aptos `aptos_std::bls12381::verify_normal_signature` before emitting events or executing swaps.

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

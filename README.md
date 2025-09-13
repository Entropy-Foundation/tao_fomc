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


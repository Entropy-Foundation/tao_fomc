import os
import re


def _read_file(path: str) -> str:
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return ""


def resolve_module_address(module_name: str = "interest_rate") -> str:
    """
    Resolve the on-chain module address for the deployed Move module.

    Strategy:
    - Prefer `deploy_logs/compile.log` which contains a fully qualified module id.
    - Fallback to `Move.toml` [addresses] mapping for `fomc_rates`.

    Returns a hex address string with `0x` prefix, e.g., `0x<addr>`.
    Raises ValueError if not found.
    """
    # 1) Try deploy logs
    compile_log_path = os.path.join("deploy_logs", "compile.log")
    content = _read_file(compile_log_path)
    if content:
        # Look for a pattern like: "<hex>::interest_rate"
        pattern = rf"\"([0-9a-fA-F]{{32,64}})::{module_name}\""
        m = re.search(pattern, content)
        if m:
            addr = m.group(1)
            if not addr.startswith("0x"):
                addr = "0x" + addr
            return addr

    # 2) Fallback to Move.toml addresses
    move_toml = _read_file("Move.toml")
    if move_toml:
        # naive parse of: fomc_rates = "<hex>"
        m = re.search(r"^fomc_rates\s*=\s*\"([0-9a-fA-F]{32,64})\"\s*$", move_toml, re.MULTILINE)
        if m:
            addr = m.group(1)
            if not addr.startswith("0x"):
                addr = "0x" + addr
            return addr

    raise ValueError("Unable to resolve deployed module address for interest_rate")


def get_function_id(function_name: str = "record_interest_rate_movement", module_name: str = "interest_rate") -> str:
    """
    Build a fully qualified function id for the deployed module.
    Example: 0x<addr>::interest_rate::record_interest_rate_movement
    """
    addr = resolve_module_address(module_name)
    return f"{addr}::{module_name}::{function_name}"


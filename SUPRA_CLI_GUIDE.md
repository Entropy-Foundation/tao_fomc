# Supra CLI Usage Guide

This guide covers how to use the Supra CLI for deploying and interacting with Move contracts on the Supra blockchain.

## Prerequisites

- Supra CLI installed and accessible (in our case at `~/Documents/foundation-multisig-tools/supra`)
- Basic understanding of Move programming language
- Access to Supra Testnet or Mainnet

## CLI Location

The Supra CLI is located at:
```bash
~/Documents/foundation-multisig-tools/supra
```

## Basic Commands

### 1. Check CLI Version and Help

```bash
~/Documents/foundation-multisig-tools/supra --help
~/Documents/foundation-multisig-tools/supra --version
```

### 2. Profile Management

#### Create a New Profile

```bash
# Create a testnet profile
~/Documents/foundation-multisig-tools/supra profile new <profile-name> --network testnet

# Example:
~/Documents/foundation-multisig-tools/supra profile new fomc-testnet --network testnet
```

#### List All Profiles

```bash
~/Documents/foundation-multisig-tools/supra profile list
```

#### Activate a Profile

```bash
~/Documents/foundation-multisig-tools/supra profile activate <profile-name>
```

### 3. Account Management

#### Fund Account with Faucet (Testnet Only)

```bash
~/Documents/foundation-multisig-tools/supra move account fund-with-faucet --profile <profile-name>

# Example:
~/Documents/foundation-multisig-tools/supra move account fund-with-faucet --profile fomc-testnet
```

#### Check Account Balance

```bash
~/Documents/foundation-multisig-tools/supra move account balance --profile <profile-name>

# Example:
~/Documents/foundation-multisig-tools/supra move account balance --profile fomc-testnet
```

### 4. Move Contract Operations

#### Compile a Move Package

```bash
~/Documents/foundation-multisig-tools/supra move tool compile --package-dir <path-to-package>

# Example:
~/Documents/foundation-multisig-tools/supra move tool compile --package-dir ./supra
```

#### Deploy/Publish a Move Package

```bash
~/Documents/foundation-multisig-tools/supra move tool publish --package-dir <path-to-package> --profile <profile-name>

# With automatic confirmation:
~/Documents/foundation-multisig-tools/supra move tool publish --package-dir ./supra --profile fomc-testnet --assume-yes
```

#### Run a Move Function

```bash
~/Documents/foundation-multisig-tools/supra move tool run \
  --function-id <address>::<module>::<function> \
  --type-args <type1> <type2> ... \
  --args <arg1> <arg2> ... \
  --profile <profile-name>
```

**Example:**
```bash
~/Documents/foundation-multisig-tools/supra move tool run \
  --function-id 0xb993b8afb07eadc713990f90ec5c422e664c13741dc0e932916a98863cd241a9::fomc_interest_rate_dexlyn::record_interest_rate_movement_dexlyn \
  --type-args "0x1::supra_coin::SupraCoin" "0x1::supra_coin::SupraCoin" "0x4496a672452b0bf5eff5e1616ebfaf7695e14b02a12ed211dd4f28ac38a5d54c::curves::Uncorrelated" \
  --args "u64:50" "bool:false" "hex:0x00" \
  --profile fomc-testnet-3
```

#### View Function (Read-only)

```bash
~/Documents/foundation-multisig-tools/supra move tool view \
  --function-id <address>::<module>::<function> \
  --type-args <type1> <type2> ... \
  --args <arg1> <arg2> ... \
  --profile <profile-name>
```

## Move.toml Configuration

Your Move.toml file should be structured like this:

```toml
[package]
name = 'your-package-name'
version = '0.1.0'

[dependencies.SupraFramework]
git = 'https://github.com/Entropy-Foundation/aptos-core.git'
subdir = 'aptos-move/framework/supra-framework'
rev = 'dev'

[dependencies.dexlyn_swap]
git = 'https://github.com/DexlynLabs/dexlyn_swap_interface.git'
rev = 'testnet'  # or 'mainnet' for mainnet

[dependencies.core]
git = "https://github.com/Entropy-Foundation/dora-interface"
subdir = "supra/testnet/core"  # or "supra/mainnet/core" for mainnet
rev = "master"

[addresses]
your_module = "0x<your-account-address>"
```

## Argument Types

When calling functions, you can use these argument types:

- `u8:123` - 8-bit unsigned integer
- `u16:123` - 16-bit unsigned integer  
- `u32:123` - 32-bit unsigned integer
- `u64:123` - 64-bit unsigned integer
- `u128:123` - 128-bit unsigned integer
- `u256:123` - 256-bit unsigned integer
- `bool:true` or `bool:false` - Boolean
- `address:0x1234...` - Address
- `hex:0x1234...` - Hex-encoded bytes
- `string:"hello"` - String
- `"[1,2,3]"` - Vector (JSON array syntax)

## Network Configuration

### Testnet
- **RPC URL**: `https://rpc-testnet.supra.com/`
- **Chain ID**: 6
- **Faucet**: Available through CLI

### Mainnet
- **RPC URL**: `https://rpc-mainnet.supra.com/`
- **Chain ID**: 8
- **Faucet**: Not available

## Common Workflows

### 1. Deploy a New Contract

```bash
# 1. Create profile
~/Documents/foundation-multisig-tools/supra profile new my-project --network testnet

# 2. Fund account
~/Documents/foundation-multisig-tools/supra move account fund-with-faucet --profile my-project

# 3. Update Move.toml with your account address
# Edit Move.toml: your_module = "0x<your-address>"

# 4. Deploy contract
~/Documents/foundation-multisig-tools/supra move tool publish --package-dir ./my-contract --profile my-project
```

### 2. Interact with Deployed Contract

```bash
# Call a function
~/Documents/foundation-multisig-tools/supra move tool run \
  --function-id 0x<address>::<module>::<function> \
  --args "u64:100" "bool:true" \
  --profile my-project

# View read-only function
~/Documents/foundation-multisig-tools/supra move tool view \
  --function-id 0x<address>::<module>::<view_function> \
  --profile my-project
```

## Troubleshooting

### Common Errors

1. **`EINVALID_PUBKEY`**: BLS public key not set - call `set_bls_public_key` first
2. **`MODULE_ADDRESS_DOES_NOT_MATCH_SENDER`**: Address in Move.toml doesn't match deployer address
3. **`EPACKAGE_DEP_MISSING`**: Dependency not found - check Move.toml dependencies
4. **Compilation errors**: Check Move syntax and imports

### Tips

- Always use `--assume-yes` for automated deployments
- Check account balance before deploying (deployment costs gas)
- Use testnet for development and testing
- Keep your private keys secure
- Use meaningful profile names for organization

## Example: FOMC Interest Rate Contract

Our deployed contract can be called like this:

```bash
# Set BLS public key (admin only)
~/Documents/foundation-multisig-tools/supra move tool run \
  --function-id 0xb993b8afb07eadc713990f90ec5c422e664c13741dc0e932916a98863cd241a9::fomc_interest_rate_dexlyn::set_bls_public_key \
  --args "hex:0x1234567890abcdef..." \
  --profile fomc-testnet-3

# Record interest rate movement (triggers swap)
~/Documents/foundation-multisig-tools/supra move tool run \
  --function-id 0xb993b8afb07eadc713990f90ec5c422e664c13741dc0e932916a98863cd241a9::fomc_interest_rate_dexlyn::record_interest_rate_movement_dexlyn \
  --type-args "0x1::supra_coin::SupraCoin" "0x1::supra_coin::SupraCoin" "0x4496a672452b0bf5eff5e1616ebfaf7695e14b02a12ed211dd4f28ac38a5d54c::curves::Uncorrelated" \
  --args "u64:50" "bool:false" "hex:0x<signature>" \
  --profile fomc-testnet-3
```

This guide should help you get started with the Supra CLI for Move development and deployment!
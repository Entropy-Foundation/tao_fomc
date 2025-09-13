import asyncio
import yaml
from typing import Any, Dict, Union
from aptos_sdk.account import Account
from aptos_sdk.async_client import RestClient
from aptos_sdk.transactions import EntryFunction, TransactionPayload, TransactionArgument
from aptos_sdk.bcs import Serializer
from find_rate_reduction import find_rate_reduction, extract_rate_change_from_text
from contract_utils import resolve_module_address, get_function_id


class AptosRateSubmitter:
    """
    Class to submit interest rate changes to the Aptos blockchain smart contract.
    """
    
    def __init__(self, config_path=".aptos/config.yaml"):
        """
        Initialize with Aptos configuration.
        
        Args:
            config_path: Path to the Aptos config file
        """
        self.config_path = config_path
        self.account = None
        self.rest_client = None
        self.module_address = None
        self.function_id = None
        self._load_config()
    
    def _load_config(self):
        """Load Aptos configuration from config file."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            profile = config['profiles']['default']
            # Use AIP-80 key string directly to avoid SDK warning
            private_key_value = profile['private_key']
            self.account = Account.load_key(private_key_value)
            self.rest_url = profile['rest_url']
            # Normalize REST URL to include /v1 suffix expected by Aptos nodes
            if not self.rest_url.rstrip("/").endswith("/v1"):
                self.rest_url = self.rest_url.rstrip("/") + "/v1"
            self.rest_client = RestClient(self.rest_url)
            # Resolve deployed module address and function id
            self.module_address = resolve_module_address("interest_rate")
            self.function_id = get_function_id("record_interest_rate_movement", "interest_rate")
            
            print(f"Loaded account: {self.account.address()}")
            print(f"Connected to: {self.rest_url}")
            print(f"Target module: {self.module_address}::interest_rate")
            
        except Exception as e:
            raise Exception(f"Failed to load Aptos config: {e}")
    
    async def submit_rate_change(self, basis_points: int, url: str = None):
        """
        Submit interest rate change to the smart contract.
        
        Args:
            basis_points: The rate change in basis points (negative for cuts, positive for hikes)
            url: Optional URL source for logging purposes
            
        Returns:
            Transaction hash if successful, None otherwise
        """
        try:
            # Convert basis points to absolute value and direction flag
            abs_basis_points = abs(basis_points)
            is_increase = basis_points > 0
            
            print(f"Submitting rate change: {basis_points} basis points")
            print(f"Contract call: {self.function_id}({abs_basis_points}, {is_increase})")

            # BCS encode arguments using serializer instances
            s1 = Serializer()
            s1.u64(abs_basis_points)
            arg1 = s1.output()

            s2 = Serializer()
            s2.bool(is_increase)
            arg2 = s2.output()

            # Build entry function and payload for the deployed module
            entry_fn = EntryFunction.natural(
                f"{self.module_address}::interest_rate",
                "record_interest_rate_movement",
                [],
                [
                    TransactionArgument(abs_basis_points, Serializer.u64),
                    TransactionArgument(is_increase, Serializer.bool),
                ],
            )
            payload = TransactionPayload(entry_fn)

            # Quick connectivity check and fallback
            try:
                await self.rest_client.info()
            except Exception as e:
                print(f"Warning: /info failed on {self.rest_url}: {e}")
                # Try known alternative endpoint
                alt = "https://api.testnet.aptoslabs.com/v1"
                if self.rest_url != alt:
                    print(f"Retrying against alternative endpoint: {alt}")
                    await self.rest_client.close()
                    self.rest_client = RestClient(alt)
                    self.rest_url = alt

            # Create and submit BCS signed transaction via the Aptos SDK
            signed_txn = await self.rest_client.create_bcs_signed_transaction(self.account, payload)
            submit_result: Union[str, Dict[str, Any]] = await self.rest_client.submit_bcs_transaction(signed_txn)

            # Normalize hash from result variations
            if isinstance(submit_result, str):
                txn_hash = submit_result
            elif isinstance(submit_result, dict) and "hash" in submit_result:
                txn_hash = submit_result["hash"]
            else:
                # Fallback: try to extract from any known keys
                txn_hash = submit_result.get("transaction_hash") if isinstance(submit_result, dict) else None

            if not txn_hash:
                print(f"❌ Transaction submission returned unexpected result: {submit_result}")
                return None

            # Wait for confirmation
            await self.rest_client.wait_for_transaction(txn_hash)

            print(f"✅ Transaction successful! Hash: {txn_hash}")
            if url:
                print(f"Source: {url}")
            
            return txn_hash
            
        except Exception as e:
            print(f"❌ Failed to submit transaction: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def process_url_and_submit(self, url: str):
        """
        Process a URL to extract rate change and submit to blockchain.
        
        Args:
            url: URL of the news article to analyze
            
        Returns:
            Transaction hash if successful, None otherwise
        """
        print(f"Processing URL: {url}")
        
        # Extract rate change from URL
        basis_points = find_rate_reduction(url)
        
        if basis_points is None:
            print("❌ No interest rate change found in the article")
            return None
        
        print(f"📈 Detected rate change: {basis_points} basis points")
        
        # Submit to blockchain
        return await self.submit_rate_change(basis_points, url)
    
    async def process_text_and_submit(self, text: str, source: str = "text input"):
        """
        Process text to extract rate change and submit to blockchain.
        
        Args:
            text: Text to analyze for rate changes
            source: Description of the text source for logging
            
        Returns:
            Transaction hash if successful, None otherwise
        """
        print(f"Processing text from: {source}")
        
        # Extract rate change from text
        basis_points = extract_rate_change_from_text(text)
        
        if basis_points is None:
            print("❌ No interest rate change found in the text")
            return None
        
        print(f"📈 Detected rate change: {basis_points} basis points")
        
        # Submit to blockchain
        return await self.submit_rate_change(basis_points)
    
    async def close(self):
        """Close the REST client connection."""
        if self.rest_client:
            await self.rest_client.close()


async def main():
    """
    Example usage of the AptosRateSubmitter.
    """
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python aptos_rate_submitter.py <url_or_text>")
        print("Examples:")
        print("  python aptos_rate_submitter.py https://example.com/fed-cuts-rates")
        print('  python aptos_rate_submitter.py "Fed cuts rates by 50 basis points"')
        return
    
    input_arg = sys.argv[1]
    
    submitter = AptosRateSubmitter()
    
    try:
        # Check if input is a URL or text
        if input_arg.startswith('http'):
            # Process as URL
            result = await submitter.process_url_and_submit(input_arg)
        else:
            # Process as text
            result = await submitter.process_text_and_submit(input_arg, "command line")
        
        if result:
            print(f"\n🎉 Successfully recorded rate change on Aptos blockchain!")
            print(f"Transaction: {result}")
        else:
            print(f"\n❌ Failed to record rate change")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await submitter.close()


if __name__ == "__main__":
    asyncio.run(main())

# For Poetry console script entry
def cli():
    asyncio.run(main())

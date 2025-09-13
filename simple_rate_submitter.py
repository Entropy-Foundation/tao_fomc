#!/usr/bin/env python3
import asyncio
import sys
from find_rate_reduction import find_rate_reduction, extract_rate_change_from_text
from aptos_rate_submitter import AptosRateSubmitter


def submit_via_sdk(basis_points: int, url: str | None = None) -> bool:
    """
    Submit interest rate change using Aptos Python SDK.
    Returns True if a transaction hash is returned.
    """
    submitter = AptosRateSubmitter()
    try:
        txn_hash = asyncio.run(submitter.submit_rate_change(basis_points, url))
        return txn_hash is not None
    finally:
        asyncio.run(submitter.close())


def process_url_and_submit(url: str):
    """
    Process a URL to extract rate change and submit to blockchain.
    
    Args:
        url: URL of the news article to analyze
        
    Returns:
        True if successful, False otherwise
    """
    print(f"Processing URL: {url}")
    
    # Extract rate change from URL
    basis_points = find_rate_reduction(url)
    
    if basis_points is None:
        print("❌ No interest rate change found in the article")
        return False
    
    print(f"📈 Detected rate change: {basis_points} basis points")
    
    # Submit to blockchain via SDK
    return submit_via_sdk(basis_points, url)


def process_text_and_submit(text: str):
    """
    Process text to extract rate change and submit to blockchain.
    
    Args:
        text: Text to analyze for rate changes
        
    Returns:
        True if successful, False otherwise
    """
    print(f"Processing text: {text}")
    
    # Extract rate change from text
    basis_points = extract_rate_change_from_text(text)
    
    if basis_points is None:
        print("❌ No interest rate change found in the text")
        return False
    
    print(f"📈 Detected rate change: {basis_points} basis points")
    
    # Submit to blockchain via SDK
    return submit_via_sdk(basis_points)


def main():
    """
    Main function to handle command line arguments.
    """
    if len(sys.argv) < 2:
        print("Usage: python simple_rate_submitter.py <url_or_text>")
        print("Examples:")
        print("  python simple_rate_submitter.py https://example.com/fed-cuts-rates")
        print('  python simple_rate_submitter.py "Fed cuts rates by 50 basis points"')
        return
    
    input_arg = sys.argv[1]
    
    # Check if input is a URL or text
    if input_arg.startswith('http'):
        # Process as URL
        success = process_url_and_submit(input_arg)
    else:
        # Process as text
        success = process_text_and_submit(input_arg)
    
    if success:
        print(f"\n🎉 Successfully recorded rate change on Aptos blockchain!")
    else:
        print(f"\n❌ Failed to record rate change")


if __name__ == "__main__":
    main()

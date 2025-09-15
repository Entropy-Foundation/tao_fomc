#!/usr/bin/env python3
"""
Test script for the web API.
"""

import requests
import json

def test_api():
    """Test the web API with sample text."""
    
    # Test data
    test_cases = [
        {
            "name": "Rate cut example",
            "text": "The Federal Reserve announced today that it is cutting interest rates by 50 basis points to support economic growth."
        },
        {
            "name": "Rate increase example", 
            "text": "The Fed decided to raise interest rates by 25 basis points to combat inflation."
        },
        {
            "name": "No rate change",
            "text": "The Federal Reserve decided to maintain current interest rates at their existing levels."
        }
    ]
    
    base_url = "http://localhost:8000"
    
    # Test health endpoint
    try:
        response = requests.get(f"{base_url}/health")
        print(f"Health check: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")
        return
    
    # Test extract endpoint
    for test_case in test_cases:
        print(f"\nTesting: {test_case['name']}")
        print(f"Text: {test_case['text']}")
        
        try:
            response = requests.post(
                f"{base_url}/extract",
                json={"text": test_case["text"]},
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Success: Rate change = {result['rate_change']} bps")
                print(f"   BLS signature: {result['bls_signature'][:20]}...")
            else:
                print(f"❌ Error {response.status_code}: {response.text}")
                
        except Exception as e:
            print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    test_api()
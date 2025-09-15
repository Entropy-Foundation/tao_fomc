#!/usr/bin/env python3
"""
Web API for extracting interest rate movements from text and signing with BLS.

This API provides an endpoint that:
1. Takes text as input
2. Extracts interest rate movement (in basis points) using LLM approach
3. Signs the movement using BLS private key
4. Returns both the rate change and BLS signature
"""

import os
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from aptos_sdk.bcs import Serializer

# Import existing functionality
from chat import warmup, extract, get_article_text

# BLS imports
try:
    from py_ecc.bls import G2ProofOfPossession as bls
except Exception:
    bls = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="FOMC Interest Rate API",
    description="Extract interest rate movements from text and sign with BLS",
    version="1.0.0"
)

class TextInput(BaseModel):
    text: str

class RateResponse(BaseModel):
    rate_change: int
    bls_signature: str

def _load_dotenv(path: str = ".env") -> None:
    """Load environment variables from .env file."""
    if not os.path.exists(path):
        return
    try:
        with open(path, "r") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass

def _get_bls_keys() -> tuple[int, bytes]:
    """Get BLS private key and derive public key."""
    _load_dotenv()
    priv_hex = os.environ.get("BLS_PRIVATE_KEY")
    if not priv_hex:
        raise RuntimeError("BLS_PRIVATE_KEY not set; create a .env or export var")
    priv_hex = priv_hex.lower().removeprefix("0x")
    sk = int(priv_hex, 16)
    if bls is None:
        raise RuntimeError("py_ecc not installed; cannot sign BLS messages")
    pk = bls.SkToPk(sk)
    return sk, bytes(pk)

def _bls_message(abs_bps: int, is_increase: bool) -> bytes:
    """Create BLS message from rate change data."""
    s = Serializer()
    s.u64(abs_bps)
    s.bool(is_increase)
    return s.output()

def extract_rate_change_from_text_llm(text: str) -> Optional[int]:
    """
    Extracts interest rate change from text using LLM approach.
    
    Args:
        text: The text to parse for rate changes.
        
    Returns:
        The rate change in basis points as an integer (negative for reductions,
        positive for increases), or None if not found.
    """
    try:
        # Warm up the LLM
        messages = warmup()
        # Extract rate change using LLM
        return extract(text, messages)
    except Exception as e:
        logger.error(f"Error using LLM approach: {e}")
        return None

def sign_rate_change(rate_change: int) -> str:
    """
    Sign the rate change using BLS.
    
    Args:
        rate_change: Rate change in basis points (can be positive or negative)
        
    Returns:
        Hex-encoded BLS signature
    """
    abs_bps = abs(rate_change)
    is_increase = rate_change > 0
    
    # Get BLS keys
    sk, pk = _get_bls_keys()
    
    # Create message
    msg = _bls_message(abs_bps, is_increase)
    
    # Sign message
    sig = bls.Sign(sk, msg)
    
    # Return hex-encoded signature
    return bytes(sig).hex()

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "FOMC Interest Rate API",
        "version": "1.0.0",
        "endpoints": {
            "/extract": "POST - Extract rate change from text and sign with BLS"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Check if BLS is available
        if bls is None:
            return {"status": "unhealthy", "error": "BLS library not available"}
        
        # Check if BLS key is configured
        _get_bls_keys()
        
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.post("/extract", response_model=RateResponse)
async def extract_rate_and_sign(input_data: TextInput) -> RateResponse:
    """
    Extract interest rate movement from text and sign with BLS.
    
    Args:
        input_data: JSON object containing the text to analyze
        
    Returns:
        JSON object with rate_change (int) and bls_signature (hex string)
        
    Raises:
        HTTPException: If rate extraction fails or BLS signing fails
    """
    try:
        text = input_data.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Text input cannot be empty")
        
        logger.info(f"Processing text input: {text[:100]}...")
        
        # Check if input looks like a URL
        if text.startswith("http://") or text.startswith("https://"):
            try:
                # Try to extract article text from URL
                article_text = get_article_text(text)
                if article_text:
                    text = article_text
                    logger.info("Successfully extracted article text from URL")
                else:
                    logger.warning("Could not extract article text, using URL as-is")
            except Exception as e:
                logger.warning(f"Failed to extract article from URL: {e}")
        
        # Extract rate change using LLM approach
        rate_change = extract_rate_change_from_text_llm(text)
        
        if rate_change is None:
            raise HTTPException(
                status_code=404, 
                detail="Could not detect interest rate change in the provided text"
            )
        
        logger.info(f"Detected rate change: {rate_change} basis points")
        
        # Sign the rate change
        try:
            bls_signature = sign_rate_change(rate_change)
            logger.info("Successfully signed rate change with BLS")
        except Exception as e:
            logger.error(f"BLS signing failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to sign rate change: {str(e)}"
            )
        
        return RateResponse(
            rate_change=rate_change,
            bls_signature=bls_signature
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    
    # Check environment
    try:
        _get_bls_keys()
        logger.info("BLS keys loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load BLS keys: {e}")
        logger.error("Make sure BLS_PRIVATE_KEY is set in .env file")
    
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=8000)
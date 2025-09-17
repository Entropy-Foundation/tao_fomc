#!/usr/bin/env python3
"""
Multi-server Web API for extracting interest rate movements from text and threshold signing with BLS.

This API provides an endpoint that:
1. Takes text as input
2. Extracts interest rate movement (in basis points) using LLM approach
3. Signs the movement using server's threshold BLS private key share
4. Returns both the rate change and BLS threshold signature

Each server instance runs independently with its own BLS threshold key share.
Any 3 out of 4 servers can collaborate to create valid threshold signatures.
"""

import os
import sys
import logging
import argparse
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from aptos_sdk.bcs import Serializer

# Import existing functionality
from chat import (
    warmup,
    extract,
    get_article_text,
    is_ollama_available,
    OllamaUnavailableError,
)
from network_config import NetworkConfig
from threshold_signing import (
    sign_bcs_message,
    create_bcs_message_for_fomc,
    verify_signature
)

# BLS imports - not needed for threshold signing, but kept for compatibility
bls = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TextInput(BaseModel):
    text: str

class RateResponse(BaseModel):
    rate_change: int
    bls_threshold_signature: str
    server_id: int
    abs_bps: int
    is_increase: bool

class FOMCServer:
    """FOMC server instance with its own BLS threshold key share and configuration."""
    
    def __init__(self, server_id: int):
        self.server_id = server_id
        self.network_config = NetworkConfig()
        self.server_config = self.network_config.get_server_config(server_id)
        
        # Initialize FastAPI app
        self.app = FastAPI(
            title=f"FOMC Interest Rate API - Server {server_id}",
            description=f"Extract interest rate movements from text and threshold sign with BLS (Server {server_id})",
            version="1.0.0"
        )
        
        # Load server-specific BLS threshold key share
        self._load_server_env()
        
        # Load group public key for verification
        self._load_group_public_key()
        
        # Register routes
        self._register_routes()
        
        logger.info(f"FOMC Server {server_id} initialized with threshold signing on {self.server_config['host']}:{self.server_config['port']}")
    
    def _load_server_env(self):
        """Load server-specific environment variables."""
        env_file = f"keys/server_{self.server_id}.env"
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            logger.info(f"Loaded environment for server {self.server_id} from {env_file}")
        else:
            logger.warning(f"Environment file not found: {env_file}")
    
    def _load_group_public_key(self):
        """Load group public key for threshold signature verification."""
        try:
            import json
            with open("keys/bls_public_keys.json", 'r') as f:
                config = json.load(f)
            self.group_public_key = bytes.fromhex(config["group_public_key"])
            logger.info(f"Server {self.server_id} loaded group public key")
        except Exception as e:
            logger.warning(f"Server {self.server_id} failed to load group public key: {e}")
            self.group_public_key = None

    def _get_bls_threshold_key(self) -> bytes:
        """Get BLS threshold private key share."""
        priv_hex = os.environ.get("BLS_PRIVATE_KEY")
        if not priv_hex:
            raise RuntimeError(f"BLS_PRIVATE_KEY not set for server {self.server_id}")
        priv_hex = priv_hex.lower().removeprefix("0x")
        # Convert hex to bytes (32 bytes for BLS12-381)
        private_key_bytes = bytes.fromhex(priv_hex)
        return private_key_bytes
    
    def _create_fomc_bcs_message(self, abs_bps: int, is_increase: bool) -> bytes:
        """Create BCS message for FOMC rate change data."""
        return create_bcs_message_for_fomc(abs_bps, is_increase)
    
    def extract_rate_change_from_text_llm(self, text: str) -> Optional[int]:
        """
        Extracts interest rate change from text using LLM approach.
        
        Args:
            text: The text to parse for rate changes.
            
        Returns:
            The rate change in basis points as an integer (negative for reductions,
            positive for increases), or None if not found.
        """
        if not is_ollama_available():
            logger.warning(
                "Server %s - Ollama unavailable, skipping LLM extraction", self.server_id
            )
            return None

        try:
            messages = warmup()
            return extract(text, messages)
        except OllamaUnavailableError as e:
            logger.error(f"Server {self.server_id} - Ollama unavailable: {e}")
        except Exception as e:
            logger.error(f"Server {self.server_id} - Error using LLM approach: {e}")
        return None
    
    def sign_rate_change(self, rate_change: int) -> str:
        """
        Sign the rate change using BLS threshold signing.
        
        Args:
            rate_change: Rate change in basis points (can be positive or negative)
            
        Returns:
            Hex-encoded BLS threshold signature
        """
        abs_bps = abs(rate_change)
        is_increase = rate_change > 0
        
        # Get BLS threshold private key share
        private_key_bytes = self._get_bls_threshold_key()
        
        # Create BCS message
        bcs_message = self._create_fomc_bcs_message(abs_bps, is_increase)
        
        # Sign BCS message with threshold key share
        signature_bytes = sign_bcs_message(private_key_bytes, bcs_message)
        
        # Return hex-encoded signature
        return signature_bytes.hex()
    
    def _register_routes(self):
        """Register all FastAPI routes."""
        
        @self.app.get("/")
        async def root():
            """Root endpoint with API information."""
            return {
                "message": f"FOMC Interest Rate API - Server {self.server_id}",
                "version": "1.0.0",
                "server_id": self.server_id,
                "endpoints": {
                    "/extract": "POST - Extract rate change from text and threshold sign with BLS"
                },
                "threshold_info": {
                    "threshold": 3,
                    "total_servers": 4,
                    "description": "Any 3 servers can create valid threshold signatures"
                }
            }
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            try:
                # Check if BLS threshold key is configured
                self._get_bls_threshold_key()
                
                # Check if group public key is available
                if self.group_public_key is None:
                    return {
                        "status": "unhealthy",
                        "error": "Group public key not available",
                        "server_id": self.server_id
                    }
                
                return {
                    "status": "healthy",
                    "server_id": self.server_id,
                    "threshold_signing": True,
                    "threshold": 3,
                    "total_servers": 4
                }
            except Exception as e:
                return {"status": "unhealthy", "error": str(e), "server_id": self.server_id}
        
        @self.app.post("/extract", response_model=RateResponse)
        async def extract_rate_and_sign(input_data: TextInput) -> RateResponse:
            """
            Extract interest rate movement from text and threshold sign with BLS.
            
            Args:
                input_data: JSON object containing the text to analyze
                
            Returns:
                JSON object with rate_change (int), bls_threshold_signature (hex string),
                server_id, abs_bps, and is_increase
                
            Raises:
                HTTPException: If rate extraction fails or BLS threshold signing fails
            """
            try:
                text = input_data.text.strip()
                if not text:
                    raise HTTPException(status_code=400, detail="Text input cannot be empty")
                
                logger.info(f"Server {self.server_id} - Processing text input: {text[:100]}...")
                
                # Check if input looks like a URL
                if text.startswith("http://") or text.startswith("https://"):
                    try:
                        # Try to extract article text from URL
                        article_text = get_article_text(text)
                        if article_text:
                            text = article_text
                            logger.info(f"Server {self.server_id} - Successfully extracted article text from URL")
                        else:
                            logger.warning(f"Server {self.server_id} - Could not extract article text, using URL as-is")
                    except Exception as e:
                        logger.warning(f"Server {self.server_id} - Failed to extract article from URL: {e}")
                
                # Extract rate change using LLM approach
                rate_change = self.extract_rate_change_from_text_llm(text)
                
                if rate_change is None:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"Server {self.server_id} - Could not detect interest rate change in the provided text"
                    )
                
                logger.info(f"Server {self.server_id} - Detected rate change: {rate_change} basis points")
                
                # Sign the rate change with threshold signing
                try:
                    bls_threshold_signature = self.sign_rate_change(rate_change)
                    logger.info(f"Server {self.server_id} - Successfully threshold signed rate change with BLS")
                    
                    # Calculate abs_bps and is_increase for response
                    abs_bps = abs(rate_change)
                    is_increase = rate_change > 0
                    
                except Exception as e:
                    logger.error(f"Server {self.server_id} - BLS threshold signing failed: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Server {self.server_id} - Failed to threshold sign rate change: {str(e)}"
                    )
                
                return RateResponse(
                    rate_change=rate_change,
                    bls_threshold_signature=bls_threshold_signature,
                    server_id=self.server_id,
                    abs_bps=abs_bps,
                    is_increase=is_increase
                )
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Server {self.server_id} - Unexpected error: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Server {self.server_id} - Internal server error: {str(e)}"
                )

def main():
    """Main function to run a single server instance."""
    parser = argparse.ArgumentParser(description="Run FOMC server instance")
    parser.add_argument("server_id", type=int, help="Server ID (1-4)")
    args = parser.parse_args()
    
    if args.server_id < 1 or args.server_id > 4:
        print("Error: Server ID must be between 1 and 4")
        sys.exit(1)
    
    # Create server instance
    server = FOMCServer(args.server_id)
    
    # Check environment
    try:
        server._get_bls_threshold_key()
        logger.info(f"Server {args.server_id} - BLS threshold key loaded successfully")
    except Exception as e:
        logger.error(f"Server {args.server_id} - Failed to load BLS threshold key: {e}")
        logger.error(f"Make sure BLS_PRIVATE_KEY is set in keys/server_{args.server_id}.env file")
        sys.exit(1)
    
    # Run the server
    import uvicorn
    config = server.server_config
    uvicorn.run(server.app, host=config["host"], port=config["port"])

if __name__ == "__main__":
    main()

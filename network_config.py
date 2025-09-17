"""Network configuration for the FOMC multi-server system."""

import os
import json
from typing import Dict, List, Optional

class NetworkConfig:
    """Configuration for network nodes and communication."""
    
    def __init__(self, config_file: Optional[str] = None, servers_override: Optional[List[Dict]] = None):
        """Initialize network configuration.
        
        Args:
            config_file: Path to JSON config file
            servers_override: Optional list of server configs to override all other sources
        """
        self.config_file = config_file or os.environ.get('NETWORK_CONFIG_FILE', 'network_config.json')
        self.servers_override = servers_override
        self.config = self._load_config()
        # Apply environment variable overrides after loading config
        self._apply_env_overrides()
        
    def _load_config(self) -> Dict:
        """Load network configuration from file, environment, or defaults."""
        # If servers are explicitly provided, use them
        if self.servers_override:
            config = {"servers": self.servers_override}
            print(f"Using provided server configuration with {len(self.servers_override)} servers")
            return config
        
        # Try to load from environment variables first
        env_config = self._load_from_environment()
        if env_config:
            return env_config
        
        # Try to load from file
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                print(f"Loaded network config from {self.config_file}")
                return config
            except Exception as e:
                print(f"Failed to load config from {self.config_file}: {e}")
        
        # Fallback to default configuration for 4 servers
        # Use environment variable FOMC_PORT if available, otherwise default ports
        base_port = int(os.environ.get('FOMC_PORT', '9001'))
        config = {
            "servers": [
                {"id": 1, "host": "0.0.0.0", "port": base_port},
                {"id": 2, "host": "0.0.0.0", "port": base_port + 1},
                {"id": 3, "host": "0.0.0.0", "port": base_port + 2},
                {"id": 4, "host": "0.0.0.0", "port": base_port + 3}
            ]
        }
        
        print(f"Using default network config with 4 servers")
        return config
    
    def _load_from_environment(self) -> Optional[Dict]:
        """Load server configuration from environment variables.
        
        Supports two formats:
        1. FOMC_SERVERS_JSON: JSON string with full server config
        2. FOMC_SERVER_URLS: Comma-separated list of URLs (http://host:port)
        """
        # Format 1: Full JSON configuration
        servers_json = os.environ.get('FOMC_SERVERS_JSON')
        if servers_json:
            try:
                config = json.loads(servers_json)
                print(f"Loaded network config from FOMC_SERVERS_JSON environment variable")
                return config
            except Exception as e:
                print(f"Failed to parse FOMC_SERVERS_JSON: {e}")
        
        # Format 2: Simple URL list
        server_urls = os.environ.get('FOMC_SERVER_URLS')
        if server_urls:
            try:
                urls = [url.strip() for url in server_urls.split(',') if url.strip()]
                servers = []
                for i, url in enumerate(urls, 1):
                    # Parse URL format: http://host:port or host:port
                    if url.startswith('http://'):
                        url = url[7:]  # Remove http://
                    elif url.startswith('https://'):
                        url = url[8:]  # Remove https://
                    
                    if ':' in url:
                        host, port_str = url.rsplit(':', 1)
                        port = int(port_str)
                    else:
                        raise ValueError(f"Invalid URL format: {url} (expected host:port)")
                    
                    servers.append({"id": i, "host": host, "port": port})
                
                config = {"servers": servers}
                print(f"Loaded network config from FOMC_SERVER_URLS environment variable ({len(servers)} servers)")
                return config
            except Exception as e:
                print(f"Failed to parse FOMC_SERVER_URLS: {e}")
        
        return None
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides to the loaded configuration."""
        # Check if FOMC_PORT is set and override server ports
        fomc_port = os.environ.get('FOMC_PORT')
        if fomc_port:
            try:
                base_port = int(fomc_port)
                print(f"Overriding server ports with FOMC_PORT={base_port}")
                for i, server in enumerate(self.config["servers"]):
                    if server["id"] == 1:
                        server["port"] = base_port
                    else:
                        # For multi-server setups, use the same port for all servers
                        # since each server runs on a different machine
                        server["port"] = base_port
            except ValueError:
                print(f"Invalid FOMC_PORT value: {fomc_port}")
        
        # Check if we should override host binding for servers
        fomc_host = os.environ.get('FOMC_HOST')
        if fomc_host:
            print(f"Overriding server host binding with FOMC_HOST={fomc_host}")
            for server in self.config["servers"]:
                server["host"] = fomc_host
    
    def get_servers_config(self) -> List[Dict]:
        """Get all servers configuration."""
        return self.config["servers"]
    
    def get_server_config(self, server_id: int) -> Dict:
        """Get configuration for a specific server."""
        for server in self.config["servers"]:
            if server["id"] == server_id:
                return server
        raise ValueError(f"Server {server_id} not found in configuration")
    
    def get_num_servers(self) -> int:
        """Get the number of configured servers."""
        return len(self.config["servers"])
    
    def save_config(self):
        """Save current configuration to file."""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
        print(f"Saved network config to {self.config_file}")
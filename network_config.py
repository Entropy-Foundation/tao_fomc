"""Network configuration for the FOMC multi-server system."""

import os
import json
from typing import Dict, List, Optional

class NetworkConfig:
    """Configuration for network nodes and communication."""
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize network configuration."""
        self.config_file = config_file or os.environ.get('NETWORK_CONFIG_FILE', 'network_config.json')
        self.config = self._load_config()
        
    def _load_config(self) -> Dict:
        """Load network configuration from file or environment."""
        # Try to load from file first
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                print(f"Loaded network config from {self.config_file}")
                return config
            except Exception as e:
                print(f"Failed to load config from {self.config_file}: {e}")
        
        # Fallback to default configuration for 4 servers
        config = {
            "servers": [
                {"id": 1, "host": "127.0.0.1", "port": 8001},
                {"id": 2, "host": "127.0.0.1", "port": 8002},
                {"id": 3, "host": "127.0.0.1", "port": 8003},
                {"id": 4, "host": "127.0.0.1", "port": 8004}
            ]
        }
        
        print(f"Using default network config with 4 servers")
        return config
    
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
#!/usr/bin/env python3
"""
Server orchestration script to run 4 FOMC servers simultaneously.

This script starts 4 independent FOMC servers, each with its own:
- BLS private key
- Port number
- Process
"""

import os
import sys
import time
import signal
import subprocess
import threading
from typing import List, Dict
from network_config import NetworkConfig

class MultiServerOrchestrator:
    """Orchestrator for running multiple FOMC servers."""
    
    def __init__(self):
        self.network_config = NetworkConfig()
        self.servers = self.network_config.get_servers_config()
        self.processes: List[subprocess.Popen] = []
        self.running = False
        
    def check_prerequisites(self) -> bool:
        """Check if all required files and keys exist."""
        print("🔍 Checking prerequisites...")
        
        # Check if multi_web_api.py exists
        if not os.path.exists("multi_web_api.py"):
            print("❌ multi_web_api.py not found")
            return False
        
        # Check if keys directory exists
        if not os.path.exists("keys"):
            print("❌ keys directory not found. Run setup_keys.py first.")
            return False
        
        # Check if each server has its environment file
        for server in self.servers:
            env_file = f"keys/server_{server['id']}.env"
            if not os.path.exists(env_file):
                print(f"❌ Environment file not found: {env_file}")
                return False
        
        print("✅ All prerequisites met")
        return True
    
    def start_server(self, server_config: Dict) -> subprocess.Popen:
        """Start a single server process."""
        server_id = server_config['id']
        port = server_config['port']
        
        print(f"🚀 Starting server {server_id} on port {port}...")
        
        # Start the server process
        cmd = [sys.executable, "multi_web_api.py", str(server_id)]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Start a thread to handle output
        def handle_output():
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    if line:
                        print(f"[Server {server_id}] {line.rstrip()}")
        
        output_thread = threading.Thread(target=handle_output, daemon=True)
        output_thread.start()
        
        return process
    
    def start_all_servers(self):
        """Start all servers."""
        if not self.check_prerequisites():
            print("❌ Prerequisites not met. Exiting.")
            return False
        
        print("🚀 Starting all FOMC servers...")
        print("=" * 60)
        
        for server_config in self.servers:
            try:
                process = self.start_server(server_config)
                self.processes.append(process)
                time.sleep(2)  # Give each server time to start
            except Exception as e:
                print(f"❌ Failed to start server {server_config['id']}: {e}")
                self.stop_all_servers()
                return False
        
        self.running = True
        print("=" * 60)
        print("✅ All servers started successfully!")
        print("\n📋 Server Status:")
        for server in self.servers:
            print(f"  • Server {server['id']}: http://{server['host']}:{server['port']}")
        
        print("\n🌐 API Endpoints:")
        for server in self.servers:
            print(f"  • Server {server['id']} Extract: http://{server['host']}:{server['port']}/extract")
            print(f"  • Server {server['id']} Health: http://{server['host']}:{server['port']}/health")
        
        return True
    
    def stop_all_servers(self):
        """Stop all running servers."""
        if not self.processes:
            return
        
        print("\n🛑 Stopping all servers...")
        
        for i, process in enumerate(self.processes):
            if process and process.poll() is None:
                print(f"Stopping server {i+1}...")
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"Force killing server {i+1}...")
                    process.kill()
                except Exception as e:
                    print(f"Error stopping server {i+1}: {e}")
        
        self.processes.clear()
        self.running = False
        print("✅ All servers stopped")
    
    def wait_for_servers(self):
        """Wait for all servers to finish or handle interruption."""
        try:
            print("\n⏳ Servers running. Press Ctrl+C to stop all servers.")
            while self.running and any(p.poll() is None for p in self.processes):
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Received interrupt signal...")
        finally:
            self.stop_all_servers()
    
    def health_check(self):
        """Perform health check on all servers."""
        print("🔍 Performing health check...")
        
        import requests
        
        for server in self.servers:
            url = f"http://{server['host']}:{server['port']}/health"
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status', 'unknown')
                    print(f"✅ Server {server['id']}: {status}")
                else:
                    print(f"❌ Server {server['id']}: HTTP {response.status_code}")
            except Exception as e:
                print(f"❌ Server {server['id']}: {str(e)}")

def signal_handler(sig, frame):
    """Handle interrupt signals."""
    print("\n🛑 Received signal to stop...")
    sys.exit(0)

def main():
    """Main function."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("=" * 60)
    print("🏗️  FOMC MULTI-SERVER ORCHESTRATOR")
    print("=" * 60)
    
    orchestrator = MultiServerOrchestrator()
    
    if len(sys.argv) > 1 and sys.argv[1] == "health":
        orchestrator.health_check()
        return
    
    # Start all servers
    if orchestrator.start_all_servers():
        # Wait for servers or interruption
        orchestrator.wait_for_servers()
    else:
        print("❌ Failed to start servers")
        sys.exit(1)

if __name__ == "__main__":
    main()